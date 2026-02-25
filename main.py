"""IPO Research Tool — 메인 파이프라인

사용법:
    python main.py 리브스메드
    python main.py 리브스메드 --skip-filing    # 증권신고서 파싱 건너뛰기
    python main.py 리브스메드 --skip-analysis   # AI 분석 건너뛰기
"""

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from collectors.dart_api import (
    download_document,
    get_company_info,
    get_equity_registration,
    get_financials_multi_year,
    search_corp_code,
    search_filings,
)
from collectors.crawler_38 import search_by_name as search_38
from parsers.financial import build_financial_summary, calc_growth_rates
from parsers.offering import merge_offering_data, parse_equity_registration
from parsers.llm_parser import parse_full_filing
from analysis.analyst import generate_analysis
from output.report_writer import save_report
from output.excel_writer import generate_excel


def run_pipeline(company_name: str, skip_filing: bool = False, skip_analysis: bool = False):
    """IPO 리서치 전체 파이프라인을 실행한다."""
    print(f"\n{'='*60}")
    print(f"  IPO 리서치: {company_name}")
    print(f"{'='*60}\n")

    collected: dict = {}

    # ==================================================================
    # Step 1: 기업 식별
    # ==================================================================
    print("[Step 1] 기업 식별...")
    corp = search_corp_code(company_name)
    if not corp:
        print(f"❌ '{company_name}' DART에서 찾을 수 없습니다.")
        return
    corp_code = corp["corp_code"]
    print(f"  → {corp['corp_name']} (corp_code={corp_code}, stock_code={corp.get('stock_code', '')})")

    # ==================================================================
    # Step 2: DART 정형 데이터 수집
    # ==================================================================
    print("\n[Step 2] DART API 데이터 수집...")

    # 기업개황
    company_info = get_company_info(corp_code)
    if company_info:
        collected["company_info"] = company_info
        print(f"  기업개황: {company_info.get('corp_name')} / {company_info.get('ceo_nm')} / {company_info.get('est_dt')}")

    # 증권신고서 검색 — 기재정정본 > 원본 순으로 선택 (발행실적/투자설명서 제외)
    filings = search_filings(corp_code, last_reprt_at="N")  # 정정본 포함
    rcept_no = None
    if filings:
        # 우선순위: [기재정정]증권신고서 > 증권신고서 > 기타
        candidates = []
        for f in filings:
            name = f.get("report_nm", "")
            if "증권신고서" in name and "발행실적" not in name and "발행조건확정" not in name:
                priority = 0 if "기재정정" in name else 1
                candidates.append((priority, f))
        candidates.sort(key=lambda x: x[0])

        if candidates:
            _, chosen = candidates[0]
            rcept_no = chosen["rcept_no"]
            print(f"  증권신고서: {chosen['report_nm']} ({chosen['rcept_dt']}) → rcept_no={rcept_no}")

        # 투자설명서도 별도 저장 (사업내용이 더 자세할 수 있음)
        invest_doc = None
        for f in filings:
            name = f.get("report_nm", "")
            if "투자설명서" in name and "첨부" not in name:
                invest_doc = f["rcept_no"]
                print(f"  투자설명서: {name} ({f['rcept_dt']}) → rcept_no={invest_doc}")
                break
        collected["_invest_doc_rcept_no"] = invest_doc

        # 못 찾으면 최신 공시로 fallback
        if not rcept_no:
            rcept_no = filings[0]["rcept_no"]
            print(f"  최신 공시: {filings[0]['report_nm']} ({filings[0]['rcept_dt']}) → rcept_no={rcept_no}")

    # 지분증권 API (공모사항)
    equity_data = get_equity_registration(corp_code)
    if equity_data:
        offering = parse_equity_registration(equity_data)
        collected["offering"] = offering
        # 공모가 출력
        securities = offering.get("securities", [])
        if securities:
            sec = securities[0]
            print(f"  공모가: {sec.get('offering_price'):,}원 / 공모주식수: {sec.get('count'):,}주" if sec.get('offering_price') else "  공모가 정보 없음")

    # 재무제표
    print("  재무제표 수집 중...")
    fin_raw = get_financials_multi_year(corp_code)
    if fin_raw:
        fin_summary = build_financial_summary(fin_raw)
        fin_summary = calc_growth_rates(fin_summary)
        collected["financials"] = fin_summary
        for row in fin_summary:
            rev = row.get("revenue")
            rev_str = f"{rev/100_000_000:,.0f}억" if rev else "N/A"
            yoy = row.get("revenue_yoy")
            yoy_str = f" (YoY {yoy:+.1%})" if yoy else ""
            print(f"  {row['year']}년 매출: {rev_str}{yoy_str}")

    # ==================================================================
    # Step 3: 38.co.kr 크롤링
    # ==================================================================
    print("\n[Step 3] 38.co.kr 수요예측 데이터 수집...")
    try:
        crawler_data = search_38(company_name)
    except Exception as e:
        print(f"  ⚠️ 38.co.kr 크롤링 실패: {e}")
        crawler_data = None
    if crawler_data:
        collected["crawler_data"] = crawler_data
        print(f"  기관경쟁률: {crawler_data.get('institutional_competition', 'N/A')}")
        print(f"  의무보유확약: {crawler_data.get('lockup_commitment', 'N/A')}")
        print(f"  확정공모가: {crawler_data.get('confirmed_price', 'N/A')}")

        # DART + crawler 데이터 통합
        if "offering" in collected:
            collected["offering"] = merge_offering_data(collected["offering"], crawler_data)
    else:
        print("  → 38.co.kr에서 데이터를 찾지 못했습니다 (이미 상장했거나 아직 미등록)")

    # ==================================================================
    # Step 4: 증권신고서 원본 → LLM 파싱
    # ==================================================================
    has_financials = bool(collected.get("financials"))
    if not skip_filing and rcept_no:
        print(f"\n[Step 4] 증권신고서 원본 다운로드 & LLM 파싱...")
        if not has_financials:
            print("  (DART API 재무제표 없음 → 증권신고서에서 추출 시도)")
        filing_dir = download_document(rcept_no)
        if filing_dir:
            parsed = parse_full_filing(filing_dir, need_financials=not has_financials)
            collected.update(parsed)

            # LLM 추출 재무제표를 financials에 통합
            if not has_financials and "filing_financials" in collected:
                fin_from_filing = collected["filing_financials"]
                # LLM 추출 결과를 기존 financials 형식에 맞게 변환
                fin_summary = _convert_filing_financials(fin_from_filing)
                if fin_summary:
                    collected["financials"] = fin_summary
                    print("  재무제표 (증권신고서 추출):")
                    for row in fin_summary:
                        rev = row.get("revenue")
                        rev_str = f"{rev/100_000_000:,.0f}억" if rev else "N/A"
                        print(f"    {row['year']}년 매출: {rev_str}")
        else:
            print("  → 증권신고서 다운로드 실패")
    elif skip_filing:
        print("\n[Step 4] 증권신고서 파싱 건너뛰기 (--skip-filing)")
    else:
        print("\n[Step 4] 증권신고서가 없어 건너뛰기")

    # ==================================================================
    # Step 5: AI 종합 분석
    # ==================================================================
    if not skip_analysis:
        print(f"\n[Step 5] AI 종합 분석...")
        analysis_report = generate_analysis(collected, company_name)
        collected["analysis_report"] = analysis_report
    else:
        print(f"\n[Step 5] AI 분석 건너뛰기 (--skip-analysis)")
        analysis_report = ""

    # ==================================================================
    # Step 6: 출력
    # ==================================================================
    print(f"\n[Step 6] 리포트 생성...")

    # 마크다운 리포트
    if analysis_report:
        md_path = save_report(company_name, analysis_report, collected)

    # 엑셀 시트
    xlsx_path = generate_excel(collected, company_name)

    # 수집 데이터 JSON 저장
    json_path = save_raw_data(collected, company_name)

    # ==================================================================
    # 완료
    # ==================================================================
    print(f"\n{'='*60}")
    print(f"  ✅ {company_name} IPO 리서치 완료!")
    print(f"{'='*60}")
    if analysis_report:
        print(f"  📄 리포트: {md_path}")
    print(f"  📊 엑셀: {xlsx_path}")
    print(f"  💾 원본 데이터: {json_path}")

    # 분석 리포트 콘솔 출력
    if analysis_report:
        print(f"\n{'─'*60}")
        print(analysis_report)

    return collected


def _convert_filing_financials(filing_fin: list[dict]) -> list[dict]:
    """LLM이 증권신고서에서 추출한 재무제표를 기존 financials 형식으로 변환한다."""
    from parsers.financial import calc_growth_rates

    result = []
    for item in filing_fin:
        # 연간 데이터만 사용 (반기/분기 제외)
        period = item.get("period_type", "annual")
        if period not in ("annual", "yearly"):
            # 반기도 참고용으로 포함하되 표시
            pass

        year = str(item.get("year", ""))
        # "2024.1Q" 같은 형식에서 연도만 추출
        if "." in year:
            year_part = year.split(".")[0]
        else:
            year_part = year[:4] if len(year) >= 4 else year

        row = {
            "year": year_part,
            "revenue": item.get("revenue"),
            "operating_income": item.get("operating_income"),
            "net_income": item.get("net_income"),
            "total_assets": item.get("total_assets"),
            "total_liabilities": item.get("total_liabilities"),
            "total_equity": item.get("total_equity"),
            "operating_cashflow": item.get("operating_cashflow"),
            "source": "증권신고서",
        }
        result.append(row)

    # 연도순 정렬 & 중복 제거 (같은 연도면 첫 번째 우선)
    seen = set()
    unique = []
    result.sort(key=lambda x: x["year"])
    for r in result:
        if r["year"] not in seen:
            seen.add(r["year"])
            unique.append(r)

    return calc_growth_rates(unique) if unique else []


def save_raw_data(data: dict, company_name: str) -> Path:
    """수집된 원본 데이터를 JSON으로 저장한다."""
    from datetime import datetime
    from config.settings import REPORTS_DIR

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    filepath = REPORTS_DIR / f"{today}_{company_name}_data.json"

    # analysis_report는 별도 파일이므로 제외
    save_data = {k: v for k, v in data.items() if k != "analysis_report"}

    filepath.write_text(
        json.dumps(save_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[데이터] 저장 완료: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="IPO 공모주 리서치 자동화 도구")
    parser.add_argument("company", help="분석할 회사명")
    parser.add_argument("--skip-filing", action="store_true", help="증권신고서 파싱 건너뛰기")
    parser.add_argument("--skip-analysis", action="store_true", help="AI 분석 건너뛰기")

    args = parser.parse_args()
    run_pipeline(args.company, skip_filing=args.skip_filing, skip_analysis=args.skip_analysis)


if __name__ == "__main__":
    main()
