"""공모사항 데이터 정리 모듈

DART 지분증권 API + 38.co.kr 데이터를 통합 정리한다.
"""

import re


def _clean_num(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = re.sub(r"[,\s원주배%]", "", val.strip())
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return None


def _clean_float(val: str | None) -> float | None:
    if not val:
        return None
    cleaned = re.sub(r"[,\s%]", "", val.strip())
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_equity_registration(data: dict) -> dict:
    """DART estkRs API 응답을 정리한다.

    Returns:
        {
            "subscription_date": "...",
            "payment_date": "...",
            "securities": [{"type": "보통주", "count": 2470000, "price": 55000, ...}],
            "underwriters": [{"name": "삼성증권", "count": ..., "amount": ...}],
            "fund_usage": [{"category": "시설자금", "amount": ...}],
        }
    """
    result = {}

    # 일반사항
    for item in data.get("general", []):
        result["subscription_date"] = item.get("sbd", "")
        result["payment_date"] = item.get("pymd", "")
        result["subscription_announcement"] = item.get("sband", "")

    # 증권의종류 (공모가 정보)
    securities = []
    for item in data.get("securities", []):
        securities.append({
            "type": item.get("stksen", ""),
            "count": _clean_num(item.get("stkcnt")),
            "face_value": _clean_num(item.get("fv")),
            "offering_price": _clean_num(item.get("slprc")),
            "total_amount": _clean_num(item.get("slta")),
            "method": item.get("slmthn", ""),
        })
    result["securities"] = securities

    # 인수인 (주관사)
    underwriters = []
    for item in data.get("underwriters", []):
        underwriters.append({
            "type": item.get("actsen", ""),
            "name": item.get("actnmn", ""),
            "count": _clean_num(item.get("udtcnt")),
            "amount": _clean_num(item.get("udtamt")),
            "method": item.get("udtmth", ""),
        })
    result["underwriters"] = underwriters

    # 자금의사용목적
    fund_usage = []
    for item in data.get("fund_usage", []):
        fund_usage.append({
            "category": item.get("se", ""),
            "amount": _clean_num(item.get("amt")),
        })
    result["fund_usage"] = fund_usage

    # 매출인 (구주매출)
    sellers = []
    for item in data.get("sellers", []):
        sellers.append({
            "holder": item.get("hdr", ""),
            "relationship": item.get("rl_cmp", ""),
            "before_sale": _clean_num(item.get("bfsl_hdstk")),
            "sold": _clean_num(item.get("slstk")),
            "after_sale": _clean_num(item.get("atsl_hdstk")),
        })
    result["sellers"] = sellers

    return result


def merge_offering_data(dart_data: dict, crawler_data: dict | None) -> dict:
    """DART + 38.co.kr 데이터를 통합한다."""
    merged = dict(dart_data)

    if not crawler_data:
        return merged

    # 38.co.kr에서만 얻을 수 있는 데이터
    extra_fields = {
        "confirmed_price": "확정공모가",
        "institutional_competition": "기관경쟁률",
        "lockup_commitment": "의무보유확약비율",
        "listing_date": "상장예정일",
        "demand_forecast_date": "수요예측일",
        "subscription_date": "청약일",
        "lead_underwriter": "주관사",
        "offering_shares": "공모주식수",
        "total_shares": "상장예정주식수",
        "institutional_allocation": "기관배정비율",
        "retail_allocation": "일반배정비율",
        "employee_allocation": "우리사주배정비율",
    }

    for field, label in extra_fields.items():
        if field in crawler_data and crawler_data[field]:
            merged[f"crawler_{field}"] = crawler_data[field]

    return merged
