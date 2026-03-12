"""AI 블라인드 판단 모듈

수요예측 이전 시점에서 알 수 있는 데이터만으로 IPO 투자 판단을 내린다.
DART 전체 파이프라인(기업개황 + 재무제표 + 증권신고서 LLM 파싱)을 실행하여
충분한 데이터를 수집한 뒤, 수요예측 결과는 제외하고 판단한다.

수요예측 결과(기관경쟁률, 의무보유확약, 확정공모가, 시초가)는
캘리브레이션 검증용으로만 사용된다.
"""

import json
import re
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ANTHROPIC_API_KEY, LLM_MODEL, DATA_DIR
from collectors.dart_api import (
    search_corp_code,
    get_company_info,
    get_equity_registration,
    get_financials_multi_year,
    search_filings,
    download_document,
)
from parsers.financial import build_financial_summary, calc_growth_rates
from parsers.offering import parse_equity_registration
from parsers.llm_parser import parse_full_filing

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CALIBRATION_DIR = DATA_DIR / "calibration"
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# 블라인드 판단 프롬프트
# 수요예측 이전 시점의 정보만 주어진다는 점을 명시
# ──────────────────────────────────────────────────────────────

BLIND_JUDGE_SYSTEM = """너는 기관투자자의 IPO 리서치 애널리스트다.
수요예측 참여 여부를 판단해야 한다.

⚠️ 중요: 너에게 주어진 데이터는 수요예측 이전 시점의 정보다.
기관경쟁률, 의무보유확약, 확정공모가, 시초가 — 이런 정보는 아직 알 수 없다.
순수하게 기업 분석과 공모가 밴드만으로 판단해야 한다.

판단 기준:
1. 사업 내용과 시장 내 경쟁력
2. 재무제표 — 매출 성장성, 수익성, 재무 건전성
3. 공모가 밴드의 밸류에이션 적정성 (PER, PSR 등)
4. 유통가능물량과 오버행 리스크
5. 주관사 신뢰도

밸류에이션 유의사항:
- 증권신고서의 밸류에이션 방법론(PER, PSR 등)을 기본 프레임으로 따르되, 가정을 보수적으로 조정하라
- Peer 선정의 적정성, 미래 실적 추정의 공격성, 할인율 충분성을 비판적으로 검토
- 일회성 매출(라이선스, 기술이전)은 반복 매출과 구분하여 평가하라
- 적정가는 현재 매출이 아닌 증권신고서 추정 실적을 보수적으로 조정한 값을 기준으로 산출하라

출력은 반드시 아래 JSON 형식으로만 응답:
{
  "verdict": "BUY" | "CONDITIONAL" | "AVOID",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "fair_price_estimate": {"low": 숫자, "high": 숫자},
  "reasons": ["이유1", "이유2", "이유3"],
  "risk_note": "주요 리스크 한 줄"
}"""


def _normalize_company_name(name: str) -> list[str]:
    """38.co.kr 종목명을 DART 검색용 이름 후보로 변환한다.

    예: '케이뱅크(유가)' → ['케이뱅크']
        '더핑크퐁컴퍼니(구.스마트스터디)' → ['더핑크퐁컴퍼니', '스마트스터디']
        '테라뷰홀딩스' → ['테라뷰홀딩스', '테라뷰']
    """
    candidates = []
    # (유가), (코스닥) 등 시장 표시 제거
    cleaned = re.sub(r"\(유가\)|\(코스닥\)", "", name).strip()
    # (구.XXX) 패턴에서 구 회사명 추출
    old_name_match = re.search(r"\(구[.\s]*(.+?)\)", cleaned)
    if old_name_match:
        old_name = old_name_match.group(1).strip()
        cleaned = re.sub(r"\(구[.\s]*.+?\)", "", cleaned).strip()
        candidates.append(cleaned)
        candidates.append(old_name)
    else:
        candidates.append(cleaned)
    # '홀딩스' 제거 버전도 시도
    if "홀딩스" in cleaned:
        candidates.append(cleaned.replace("홀딩스", "").strip())
    return candidates


def collect_dart_data(company_name: str) -> dict | None:
    """DART 전체 파이프라인으로 수요예측 이전 데이터를 수집한다.

    38.co.kr 크롤러는 호출하지 않는다 (수요예측 결과 데이터이므로).

    Returns:
        수집된 데이터 dict 또는 실패 시 None
    """
    collected: dict = {}

    # 기업 식별 (이름 정규화 + 여러 후보 시도)
    name_candidates = _normalize_company_name(company_name)
    corp = None
    for candidate in name_candidates:
        corp = search_corp_code(candidate)
        if corp:
            break
    if not corp:
        print(f"  [DART] '{company_name}' 찾을 수 없음 (시도: {name_candidates})")
        return None
    corp_code = corp["corp_code"]
    print(f"  [DART] {corp['corp_name']} (corp_code={corp_code})")

    # 기업개황
    company_info = get_company_info(corp_code)
    if company_info:
        collected["company_info"] = company_info

    # 증권신고서 검색
    filings = search_filings(corp_code, last_reprt_at="N")
    rcept_no = None
    if filings:
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

    # 지분증권 (공모사항)
    equity_data = get_equity_registration(corp_code)
    if equity_data:
        offering = parse_equity_registration(equity_data)
        collected["offering"] = offering

    # 재무제표
    has_financials = False
    try:
        fin_raw = get_financials_multi_year(corp_code)
        if fin_raw:
            fin_summary = build_financial_summary(fin_raw)
            fin_summary = calc_growth_rates(fin_summary)
            collected["financials"] = fin_summary
            has_financials = True
    except Exception as e:
        print(f"  [DART] 재무제표 수집 실패 (무시): {e}")

    # 증권신고서 LLM 파싱 (사업내용, 밸류에이션, 보호예수 등)
    if rcept_no:
        try:
            filing_dir = download_document(rcept_no)
            if filing_dir:
                parsed = parse_full_filing(filing_dir, need_financials=not has_financials)
                collected.update(parsed)

                # LLM 추출 재무제표 통합
                if not has_financials and "filing_financials" in collected:
                    fin_from_filing = collected["filing_financials"]
                    fin_summary = _convert_filing_financials(fin_from_filing)
                    if fin_summary:
                        collected["financials"] = fin_summary
        except Exception as e:
            print(f"  [DART] 증권신고서 파싱 실패 (무시): {e}")

    return collected if collected else None


def _convert_filing_financials(filing_fin: list[dict]) -> list[dict]:
    """LLM이 증권신고서에서 추출한 재무제표를 기존 financials 형식으로 변환."""
    result = []
    for item in filing_fin:
        year = str(item.get("year", ""))
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

    seen = set()
    unique = []
    result.sort(key=lambda x: x["year"])
    for r in result:
        if r["year"] not in seen:
            seen.add(r["year"])
            unique.append(r)

    return calc_growth_rates(unique) if unique else []


def _format_blind_data(data: dict, ipo_basic: dict) -> str:
    """수요예측 이전 시점의 데이터만 프롬프트용으로 포맷한다.

    제외되는 데이터:
    - 기관경쟁률 (competition_ratio)
    - 의무보유확약 (commitment_pct)
    - 확정공모가 (confirmed_price)
    - 시초가 (first_price)
    """
    sections = []

    # 기업 개황
    if "company_info" in data:
        ci = data["company_info"]
        sections.append(f"""## 기업 개황
- 회사명: {ci.get('corp_name', '')}
- 대표: {ci.get('ceo_nm', '')}
- 설립일: {ci.get('est_dt', '')}
- 업종: {ci.get('induty_code', '')}""")

    # 공모사항 (DART 지분증권 데이터 — 수요예측 전 정보)
    if "offering" in data:
        offering_clean = {}
        for k, v in data["offering"].items():
            # 38.co.kr 크롤러에서 온 필드 제거
            if k.startswith("crawler_"):
                continue
            if k in ("institutional_competition", "lockup_commitment",
                     "confirmed_price", "first_price"):
                continue
            offering_clean[k] = v
        sections.append(
            f"## 공모사항\n```json\n"
            f"{json.dumps(offering_clean, ensure_ascii=False, indent=2, default=str)}\n```"
        )

    # 공모가 밴드 (38.co.kr 기본 정보 — 수요예측 전 공개)
    band_low = ipo_basic.get("band_low")
    band_high = ipo_basic.get("band_high")
    underwriter = ipo_basic.get("underwriter", "")
    if band_low and band_high:
        sections.append(
            f"## 공모가 밴드\n"
            f"- 하한: {band_low:,}원\n"
            f"- 상한: {band_high:,}원\n"
            f"- 주관사: {underwriter}"
        )

    # 재무제표
    if "financials" in data:
        sections.append(
            f"## 재무제표\n```json\n"
            f"{json.dumps(data['financials'], ensure_ascii=False, indent=2, default=str)}\n```"
        )

    # 사업내용 (증권신고서 LLM 파싱 결과)
    if "business" in data:
        sections.append(
            f"## 사업내용\n```json\n"
            f"{json.dumps(data['business'], ensure_ascii=False, indent=2, default=str)}\n```"
        )

    # 밸류에이션 (증권신고서 LLM 파싱 결과)
    if "valuation" in data:
        sections.append(
            f"## 밸류에이션 (Peer 비교)\n```json\n"
            f"{json.dumps(data['valuation'], ensure_ascii=False, indent=2, default=str)}\n```"
        )

    # 유통가능주식수 / 보호예수
    if "lockup_schedule" in data:
        sections.append(
            f"## 유통가능주식수 (보호예수)\n```json\n"
            f"{json.dumps(data['lockup_schedule'], ensure_ascii=False, indent=2, default=str)}\n```"
        )

    return "\n\n".join(sections)


def blind_judge(data: dict, ipo_basic: dict) -> dict | None:
    """수요예측 이전 데이터만으로 AI 투자 판단을 수행한다.

    Args:
        data: DART 파이프라인에서 수집한 데이터
        ipo_basic: calibration.py의 IPO 기본 정보

    Returns:
        AI 판단 결과 dict 또는 실패 시 None
    """
    formatted = _format_blind_data(data, ipo_basic)
    company_name = ipo_basic.get("name", "알 수 없음")

    user_prompt = (
        f"아래는 '{company_name}'의 IPO 관련 데이터입니다.\n"
        f"수요예측 참여 여부를 판단해주세요.\n\n"
        f"{formatted}\n\n"
        f"반드시 JSON 형식으로만 응답하세요."
    )

    try:
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1000,
            system=BLIND_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = resp.content[0].text.strip()

        # JSON 추출 (마크다운 코드블록 대응)
        if "```" in text:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        return json.loads(text)
    except (json.JSONDecodeError, Exception) as e:
        print(f"  [blind_judge] {company_name} 판단 실패: {e}")
        return None


def run_calibration_for_one(ipo_basic: dict) -> dict:
    """단일 IPO에 대해 DART 데이터 수집 + 블라인드 판단을 수행한다."""
    name = ipo_basic.get("name", "?")
    print(f"\n{'─'*40}")
    print(f"  분석: {name}")
    print(f"{'─'*40}")

    dart_data = collect_dart_data(name)

    if dart_data:
        result = blind_judge(dart_data, ipo_basic)
        if result:
            ipo_basic["ai_verdict"] = result.get("verdict", "UNKNOWN")
            ipo_basic["ai_confidence"] = result.get("confidence", "LOW")
            ipo_basic["ai_fair_price"] = result.get("fair_price_estimate", {})
            ipo_basic["ai_reasons"] = result.get("reasons", [])
            ipo_basic["ai_risk_note"] = result.get("risk_note", "")
            ipo_basic["ai_data_source"] = "DART_FULL"
            print(f"  → 판단: {ipo_basic['ai_verdict']} ({ipo_basic['ai_confidence']})")
        else:
            ipo_basic["ai_verdict"] = "ERROR"
            ipo_basic["ai_data_source"] = "DART_FULL"
    else:
        print(f"  [DART] 데이터 수집 실패")
        ipo_basic["ai_verdict"] = "NO_DATA"
        ipo_basic["ai_data_source"] = "NONE"

    return ipo_basic


def batch_calibration(ipos: list[dict], skip_existing: bool = True,
                      save_fn=None, save_interval: int = 5) -> list[dict]:
    """여러 IPO에 대해 일괄 블라인드 판단을 수행한다.

    Args:
        save_fn: 중간 저장 콜백 (ipos 리스트를 받음)
        save_interval: 몇 건마다 중간 저장할지
    """
    total = len(ipos)
    judged = 0

    for i, ipo in enumerate(ipos):
        if skip_existing and ipo.get("ai_verdict") and ipo["ai_verdict"] not in ("ERROR", "NO_DATA"):
            print(f"[{i+1}/{total}] {ipo.get('name', '?')} — 이미 판단됨, 건너뜀")
            continue

        print(f"\n[{i+1}/{total}] {ipo.get('name', '?')} 분석 중...")
        try:
            run_calibration_for_one(ipo)
        except Exception as e:
            print(f"  [ERROR] {ipo.get('name', '?')} 처리 실패: {e}")
            ipo["ai_verdict"] = "ERROR"
            ipo["ai_data_source"] = "CRASH"
        judged += 1

        # 중간 저장
        if save_fn and judged % save_interval == 0:
            save_fn(ipos)
            print(f"  [자동저장] {judged}건 완료 시점 저장")

        # API 부하 방지
        if i < total - 1:
            time.sleep(1)

    print(f"\n[블라인드 판단] {judged}/{total}건 완료")
    return ipos


if __name__ == "__main__":
    from analysis.calibration import (
        collect_recent_ipos,
        filter_recent_months,
        save_history,
    )

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=12, help="최근 N개월 (기본: 12)")
    parser.add_argument("--pages", type=int, default=15, help="크롤링 페이지 수 (기본: 15)")
    args = parser.parse_args()

    print(f"=== IPO 블라인드 판단 (캘리브레이션, 최근 {args.months}개월) ===")
    all_ipos = collect_recent_ipos(pages=args.pages)
    recent = filter_recent_months(all_ipos, months=args.months)
    print(f"대상: {len(recent)}건\n")

    recent = batch_calibration(recent, save_fn=save_history)
    save_history(recent)

    print("\n=== 결과 ===")
    for ipo in recent:
        v = ipo.get("ai_verdict", "?")
        ret = (
            f"{ipo['first_day_return']:+.1f}%"
            if ipo.get("first_day_return") is not None
            else "N/A"
        )
        band = (
            f"{ipo.get('band_position', '?')}%"
            if ipo.get("band_position") is not None
            else "N/A"
        )
        print(
            f"  {ipo['name']:15s} | AI: {v:12s} | "
            f"밴드위치: {band:>6s} | 시초가수익률: {ret}"
        )
