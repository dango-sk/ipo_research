"""재무제표 데이터 정리 모듈

DART API에서 받은 재무제표 raw 데이터를 정리된 딕셔너리로 변환한다.
"""


def _parse_amount(val: str | None) -> int | None:
    """금액 문자열 → 정수. 콤마, 공백 제거."""
    if not val:
        return None
    cleaned = val.replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return None


# 관심 계정 목록
KEY_ACCOUNTS = {
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
    "매출액": "revenue",
    "영업이익": "operating_income",
    "당기순이익": "net_income",
    "영업활동현금흐름": "operating_cashflow",
}


def parse_financials(raw_items: list[dict]) -> dict:
    """DART 재무제표 API 응답을 정리된 딕셔너리로 변환.

    Returns:
        {
            "연결": {
                "revenue": {"current": 27121460000, "prior": 17266860000, "two_yr_prior": 9677688000},
                "operating_income": {...},
                ...
            },
            "별도": {...}
        }
    """
    result: dict[str, dict] = {}

    for item in raw_items:
        fs_type = "연결" if item.get("fs_div") == "CFS" else "별도"
        account_name = item.get("account_nm", "")

        if account_name not in KEY_ACCOUNTS:
            continue

        field = KEY_ACCOUNTS[account_name]

        if fs_type not in result:
            result[fs_type] = {}

        result[fs_type][field] = {
            "current": _parse_amount(item.get("thstrm_amount")),
            "prior": _parse_amount(item.get("frmtrm_amount")),
            "two_yr_prior": _parse_amount(item.get("bfefrmtrm_amount")),
            "current_label": item.get("thstrm_nm", ""),
            "prior_label": item.get("frmtrm_nm", ""),
        }

    return result


def build_financial_summary(multi_year: dict[str, list[dict]]) -> list[dict]:
    """여러 연도 재무제표를 연도별 요약으로 변환.

    Returns:
        [
            {"year": "2022", "revenue": 9677688000, "operating_income": -16889731802, ...},
            {"year": "2023", ...},
            ...
        ]
    """
    yearly: dict[str, dict] = {}

    for year, items in multi_year.items():
        parsed = parse_financials(items)
        # 연결 우선, 없으면 별도
        fs = parsed.get("연결") or parsed.get("별도") or {}

        row = {"year": year}
        for field in KEY_ACCOUNTS.values():
            data = fs.get(field, {})
            row[field] = data.get("current")
        yearly[year] = row

    # 연도순 정렬
    return [yearly[y] for y in sorted(yearly.keys())]


def calc_growth_rates(summary: list[dict]) -> list[dict]:
    """연도별 요약에 YoY 성장률을 추가한다."""
    for i in range(1, len(summary)):
        prev = summary[i - 1]
        curr = summary[i]
        for field in ["revenue", "operating_income", "net_income"]:
            prev_val = prev.get(field)
            curr_val = curr.get(field)
            if prev_val and curr_val and prev_val != 0:
                curr[f"{field}_yoy"] = (curr_val - prev_val) / abs(prev_val)
    return summary
