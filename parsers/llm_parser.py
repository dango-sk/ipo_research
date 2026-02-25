"""LLM 기반 비정형 데이터 파싱 모듈

증권신고서 HTML에서 유통가능주식수, Peer Valuation,
사업내용 등 비정형 데이터를 Claude API로 추출한다.
"""

import json
import re
from pathlib import Path

import anthropic

from config.settings import ANTHROPIC_API_KEY, LLM_MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    """Claude API 호출 래퍼."""
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _extract_json(text: str) -> dict | list | None:
    """LLM 응답에서 JSON 블록을 추출한다."""
    # ```json ... ``` 블록 찾기
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 전체를 JSON으로 시도
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # { 또는 [ 로 시작하는 부분 찾기
    for pattern in [r"(\{.*\})", r"(\[.*\])"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None


# ---------------------------------------------------------------------------
# 증권신고서 HTML 로드 & 섹션 분리
# ---------------------------------------------------------------------------


def load_filing_html(filing_dir: Path) -> str:
    """다운로드된 증권신고서 HTML 파일들을 하나의 텍스트로 합친다."""
    html_files = sorted(filing_dir.glob("*.html")) + sorted(filing_dir.glob("*.htm"))
    if not html_files:
        # XML 파일 시도
        html_files = sorted(filing_dir.glob("*.xml"))

    combined = ""
    for f in html_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            combined += f"\n<!-- FILE: {f.name} -->\n{content}"
        except Exception:
            try:
                content = f.read_text(encoding="euc-kr", errors="ignore")
                combined += f"\n<!-- FILE: {f.name} -->\n{content}"
            except Exception:
                continue

    return combined


def _extract_section(html: str, keywords: list[str], max_chars: int = 15000) -> str:
    """HTML에서 특정 키워드가 포함된 영역을 추출한다.

    키워드는 우선순위 순서로 배열한다.
    1차: DART XML의 <TITLE> 태그 내 키워드
    2차: 일반 텍스트에서 키워드 (우선순위 순서 유지)
    """
    import re as _re

    # 1차: TITLE 태그 내에서 키워드 찾기 (우선순위 순서)
    for kw in keywords:
        pattern = f"<TITLE[^>]*>[^<]*{_re.escape(kw)}[^<]*</TITLE>"
        match = _re.search(pattern, html, _re.IGNORECASE)
        if match:
            idx = match.start()
            return html[idx : min(len(html), idx + max_chars)]

    # 2차: 일반 텍스트에서 키워드 찾기 (우선순위 순서)
    # 각 키워드의 가장 데이터가 풍부한 매칭을 찾고, 키워드 우선순위대로 반환
    html_lower = html.lower()
    for kw in keywords:
        best_section = ""
        best_score = 0
        start_pos = 0

        while True:
            idx = html_lower.find(kw.lower(), start_pos)
            if idx < 0:
                break

            start = max(0, idx - 200)
            end = min(len(html), idx + max_chars)
            section = html[start:end]

            table_count = section.lower().count("<table")
            number_count = len(_re.findall(r"\d{3,}", section))
            score = table_count * 5 + number_count

            if score > best_score:
                best_score = score
                best_section = section

            start_pos = idx + len(kw)

        if best_section and best_score > 10:
            return best_section

    return ""


# ---------------------------------------------------------------------------
# 유통가능주식수 추출
# ---------------------------------------------------------------------------


def extract_lockup_schedule(html: str) -> list[dict] | None:
    """증권신고서에서 유통가능주식수/보호예수 테이블을 추출한다.

    Returns:
        [
            {"period": "상장일 유통가능", "shares": 7897858, "ratio": 0.3203, "cumulative": 0.3203},
            {"period": "1개월", "shares": 2541629, "ratio": 0.1031, "cumulative": 0.4233},
            ...
        ]
    """
    # 유통가능주식 테이블은 "유통가능주식인 X주" 텍스트 바로 뒤에 나옴
    section = _extract_section(html, [
        "상장 후 유통가능 및 매각제한",   # 실제 테이블 제목
        "유통가능주식인",                  # 본문 텍스트
        "매각제한 물량",
        "보호예수", "유통제한",
        "Lock-up", "lock-up"
    ])

    if not section:
        print("[LLM Parser] 유통가능주식수 섹션 찾지 못함")
        return None

    prompt = """아래 증권신고서 HTML에서 유통가능주식수(보호예수/Lock-up) 테이블을 찾아서
JSON 배열로 추출해줘.

각 항목은 이 형식으로:
{
    "period": "상장일 유통가능" 또는 "1개월", "3개월", "6개월", "12개월", "36개월" 등,
    "shares": 주식수 (정수),
    "ratio": 전체 대비 비율 (0~1 사이 소수),
    "cumulative_ratio": 누적 비율 (0~1 사이 소수)
}

⚠️ 매우 중요:
- 반드시 "상장일 유통가능" 항목을 첫 번째로 포함해. 이 항목은 상장 직후 바로 유통 가능한 주식으로, 보호예수 기간이 없는 물량이야.
- 그 다음 보호예수 해제 기간별 항목(1개월, 3개월, 6개월, 12개월 등)을 순서대로 포함해.
- 단위를 확인하고 '주' 단위로 통일해. (천주라면 ×1000)
- 비율은 0~1 사이 소수로 변환해. (32.03% → 0.3203)
- 누적비율이 없으면 직접 계산해 (상장일 유통가능 비율부터 순차 누적)
- 합계 행은 포함하지 마

```json
[...]
```"""

    result = _call_llm(
        system="증권신고서에서 정량 데이터를 정확히 추출하는 전문가. 상장일 유통가능 물량을 반드시 포함해야 한다.",
        user=f"{prompt}\n\n---\n\n{section[:15000]}",
    )

    return _extract_json(result)


# ---------------------------------------------------------------------------
# 사업 내용 요약
# ---------------------------------------------------------------------------


def extract_business_summary(html: str) -> dict | None:
    """증권신고서에서 사업내용을 요약 추출한다.

    Returns:
        {
            "company_overview": "설립일, 소재지, 대표, 직원수 등",
            "main_business": "핵심 사업 설명",
            "products": [{"name": "ArtiSential", "description": "...", "revenue_share": 0.99}],
            "market_position": "시장 내 위치/경쟁 현황",
            "growth_strategy": "성장 전략/신제품 계획"
        }
    """
    section = _extract_section(html, [
        "사업의 내용",       # DART TITLE: "II. 사업의 내용"
        "사업의내용",
        "회사의 개요",       # DART TITLE: "회사의 개요"
        "주요제품",
        "주요 제품",
    ], max_chars=20000)

    if not section:
        print("[LLM Parser] 사업내용 섹션 찾지 못함")
        return None

    prompt = """아래 증권신고서 HTML에서 사업 내용을 분석해서 JSON으로 정리해줘.

{
    "company_overview": "설립연도, 소재지, 대표이사명, 직원 수 등 기본 정보 한 문장",
    "main_business": "핵심 사업 내용 2~3문장 요약",
    "products": [
        {"name": "제품명", "description": "설명", "revenue_share": 매출비중(0~1)}
    ],
    "key_technology": "핵심 기술/특허 요약",
    "market_size": "타겟 시장 규모 (언급된 경우)",
    "competitors": ["주요 경쟁사 목록"],
    "growth_strategy": "향후 성장 전략 요약"
}

```json
{...}
```"""

    result = _call_llm(
        system="증권신고서에서 사업 내용을 정확하고 간결하게 추출하는 전문가.",
        user=f"{prompt}\n\n---\n\n{section[:15000]}",
    )

    return _extract_json(result)


# ---------------------------------------------------------------------------
# Peer Valuation 추출
# ---------------------------------------------------------------------------


def extract_peer_valuation(html: str) -> dict | None:
    """증권신고서에서 비교회사 Valuation 정보를 추출한다.

    인수인의 의견 섹션이 매우 길기 때문에 (수십만 자),
    2-pass로 나눠서 추출한다:
      1) 밸류에이션 요약 (PER 배수, 할인율, 공모가 범위)
      2) 비교회사 개별 재무 데이터 (매출, 순이익, PER 등)

    Returns:
        {
            "valuation_method": "PER 비교",
            "applied_multiple": 45.5,
            "discount_rate": 0.25,
            "offering_price_range": {"low": 44000, "high": 55000},
            "peers": [
                {"name": "Medtronic", "per": 25.57, "revenue": ..., "net_income": ...},
                ...
            ]
        }
    """
    # --- Pass 1: 밸류에이션 요약 추출 ---
    val_section = _extract_section(html, [
        "인수인의 의견",          # DART TITLE
        "비교가치",
        "공모가격에 대한 의견",
    ], max_chars=20000)

    valuation_summary = {}
    if val_section:
        prompt_val = """아래 증권신고서 HTML에서 공모가 산출 요약 정보를 추출해줘.

{
    "valuation_method": "공모가 산출 방법 (예: PER 비교, EV/EBITDA 등)",
    "base_metric": "기준 지표 설명 (예: 2027년 추정 당기순이익)",
    "base_value": 기준 값 (원 단위 정수),
    "discount_rate": 할인율 (0~1 사이 소수),
    "applied_multiple": 적용 배수 (예: PER 45.5),
    "per_share_value": 주당 평가가액 (원),
    "offering_price_range": {"low": 하단가, "high": 상단가}
}

단위를 반드시 확인해. 백만원이면 ×1,000,000.

```json
{...}
```"""
        result = _call_llm(
            system="증권신고서의 공모가 산정 요약을 정확히 추출하는 전문가.",
            user=f"{prompt_val}\n\n---\n\n{val_section[:18000]}",
        )
        valuation_summary = _extract_json(result) or {}

    # --- Pass 2: 비교회사 개별 재무 데이터 추출 ---
    # "비교기업의 주요 재무현황" 테이블은 인수인의 의견 섹션 깊은 곳에 있음
    peer_section = _extract_section(html, [
        "비교기업의 주요 재무현황",  # 가장 정확한 테이블 제목
        "유사기업 요약 재무 현황",
        "비교기업 현황",
        "유사기업 현황",
    ], max_chars=25000)

    # 추가로 "적용 PER" 근처에서 개별 PER 산출 테이블 추출
    per_section = _extract_section(html, [
        "비교기업 PER 산출",
        "적용 PER",
        "유사기업 PER",
        "PER 산출내역",
        "PER 산출 내역",
    ], max_chars=15000)

    peers = []
    if peer_section or per_section:
        # 두 섹션을 합쳐서 LLM에 전달
        combined = ""
        if per_section:
            combined += f"[PER 산출 영역]\n{per_section[:12000]}\n\n"
        if peer_section:
            combined += f"[비교기업 재무현황]\n{peer_section[:15000]}\n\n"

        if combined:
            prompt_peer = """아래 증권신고서 HTML에서 비교회사(Peer) 개별 데이터를 추출해줘.

각 비교회사별로:
{
    "name": "회사명",
    "market": "상장 거래소 (NYSE, NASDAQ, KOSPI, KOSDAQ 등)",
    "revenue": 매출액 (백만원 단위면 ×1,000,000하여 원 단위 정수),
    "operating_income": 영업이익 (원 단위 정수),
    "net_income": 당기순이익/지배주주순이익 (원 단위 정수),
    "total_assets": 자산총계 (원 단위 정수),
    "total_equity": 자본총계 (원 단위 정수),
    "market_cap": 시가총액 (원 단위 정수),
    "share_price": 기준주가 (원),
    "shares": 발행주식수/상장주식수 (정수),
    "per": PER (배수, 소수점까지),
    "ev_ebitda": EV/EBITDA (배수, 있는 경우)
}

⚠️ 매우 중요:
- 단위를 반드시 확인해! "백만원"이면 ×1,000,000, "천원"이면 ×1,000
- 테이블의 모든 비교회사를 빠짐없이 추출
- 평균 PER이 있으면 "average_per" 필드에도 기록
- 발행회사(동사) 데이터는 제외하고 비교회사만 추출

```json
{"peers": [...], "average_per": 평균PER}
```"""
            result = _call_llm(
                system="증권신고서의 비교회사 재무 데이터를 정확히 추출하는 전문가. 단위 변환을 정확히 수행한다.",
                user=f"{prompt_peer}\n\n---\n\n{combined}",
                max_tokens=6000,
            )
            peer_data = _extract_json(result)
            if peer_data:
                if isinstance(peer_data, dict):
                    peers = peer_data.get("peers", [])
                    if peer_data.get("average_per"):
                        valuation_summary["average_peer_per"] = peer_data["average_per"]
                elif isinstance(peer_data, list):
                    peers = peer_data

    if not valuation_summary and not peers:
        print("[LLM Parser] Valuation 섹션 찾지 못함")
        return None

    # 결과 병합
    valuation_summary["peers"] = peers
    return valuation_summary


# ---------------------------------------------------------------------------
# 재무제표 추출 (DART API fallback)
# ---------------------------------------------------------------------------


def extract_financials_from_filing(html: str) -> list[dict] | None:
    """증권신고서에서 재무제표를 추출한다.

    DART 재무제표 API가 데이터를 반환하지 않는 미상장 기업을 위한 fallback.

    Returns:
        [
            {"year": "2022", "revenue": 9677688000, "operating_income": -16889731802, ...},
            {"year": "2023", ...},
            ...
        ]
    """
    # 재무제표는 여러 TITLE에 걸쳐 있을 수 있음
    section = _extract_section(html, [
        "요약 재무정보",           # DART TITLE: 가장 간결한 재무 요약 테이블
        "요약재무정보",
        "재무에 관한 사항",        # DART TITLE: "III. 재무에 관한 사항"
        "재무제표",
        "손익계산서",
        "포괄손익계산서",
    ], max_chars=25000)

    if not section:
        print("[LLM Parser] 재무제표 섹션 찾지 못함")
        return None

    prompt = """아래 증권신고서 HTML에서 재무제표 데이터를 추출해줘.

연도별로 다음 항목을 JSON 배열로 정리해:
[
    {
        "year": "2024" (연도 또는 "2024.1Q" 등 기간),
        "period_type": "annual" 또는 "half" 또는 "quarter",
        "fs_type": "연결" 또는 "별도",
        "revenue": 매출액 (원 단위 정수),
        "operating_income": 영업이익 (원 단위 정수),
        "net_income": 당기순이익 (원 단위 정수),
        "total_assets": 자산총계 (원 단위 정수),
        "total_liabilities": 부채총계 (원 단위 정수),
        "total_equity": 자본총계 (원 단위 정수),
        "operating_cashflow": 영업활동현금흐름 (원 단위 정수, 있는 경우)
    }
]

⚠️ 중요:
- 단위를 반드시 확인해! "백만원"이면 ×1,000,000, "천원"이면 ×1,000, "원"이면 그대로
- 연결재무제표와 별도재무제표가 둘 다 있으면 연결재무제표를 우선 사용
- 사업연도가 완전한 연도(12개월)인지, 반기/분기인지 구분해서 period_type에 기록
- 가장 최근 3~5개년 데이터를 추출해
- 적자(음수)도 정확히 음수로 기록해
- 재무요약 테이블이 여러 개 있으면 가장 상세한 것을 사용

```json
[...]
```"""

    result = _call_llm(
        system="증권신고서의 재무제표 데이터를 정확히 추출하는 전문가. 단위 변환을 정확히 수행한다.",
        user=f"{prompt}\n\n---\n\n{section[:20000]}",
        max_tokens=4096,
    )

    return _extract_json(result)


# ---------------------------------------------------------------------------
# 통합 파싱
# ---------------------------------------------------------------------------


def parse_full_filing(filing_dir: Path, need_financials: bool = False) -> dict:
    """증권신고서 HTML 전체를 파싱하여 구조화된 데이터를 반환한다.

    Args:
        filing_dir: 증권신고서 HTML 파일이 있는 디렉토리
        need_financials: True이면 재무제표도 LLM으로 추출 (DART API fallback)
    """
    html = load_filing_html(filing_dir)
    if not html:
        print("[LLM Parser] HTML 파일 없음")
        return {}

    print(f"[LLM Parser] HTML 로드 완료 ({len(html):,}자)")

    result = {}

    print("[LLM Parser] 유통가능주식수 추출 중...")
    lockup = extract_lockup_schedule(html)
    if lockup:
        result["lockup_schedule"] = lockup
        print(f"  → {len(lockup)}개 항목 추출")

    print("[LLM Parser] 사업내용 추출 중...")
    business = extract_business_summary(html)
    if business:
        result["business"] = business
        print("  → 추출 완료")

    print("[LLM Parser] Peer Valuation 추출 중...")
    valuation = extract_peer_valuation(html)
    if valuation:
        result["valuation"] = valuation
        print("  → 추출 완료")

    if need_financials:
        print("[LLM Parser] 재무제표 추출 중 (DART API fallback)...")
        financials = extract_financials_from_filing(html)
        if financials:
            result["filing_financials"] = financials
            print(f"  → {len(financials)}개 연도 추출")

    return result
