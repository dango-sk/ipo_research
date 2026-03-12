"""IPO 판단 캘리브레이션 모듈

최근 IPO 데이터를 일괄 수집하고, AI 판단과 실제 시장 결과를 비교한다.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from collectors.crawler_38 import get_demand_forecast_list
from config.settings import DATA_DIR

CALIBRATION_DIR = DATA_DIR / "calibration"
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = CALIBRATION_DIR / "ipo_history.json"


def _parse_price(text: str) -> int | None:
    """가격 문자열에서 정수 추출. 예: '55,000' → 55000"""
    if not text or text == "-":
        return None
    try:
        return int(re.sub(r"[,\s원]", "", text.strip()))
    except (ValueError, TypeError):
        return None


def _parse_price_range(text: str) -> tuple[int | None, int | None]:
    """공모가 밴드 파싱. 예: '44,000~55,000' → (44000, 55000)"""
    if not text or text == "-":
        return None, None
    parts = re.split(r"[~\-]", text)
    if len(parts) == 2:
        return _parse_price(parts[0]), _parse_price(parts[1])
    elif len(parts) == 1:
        p = _parse_price(parts[0])
        return p, p
    return None, None


def _parse_competition(text: str) -> float | None:
    """경쟁률 파싱. 예: '231.87:1' → 231.87"""
    if not text or text == "-":
        return None
    match = re.search(r"([\d,.]+)\s*:\s*1", text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _parse_commitment(text: str) -> float | None:
    """확약비율 파싱. 예: '17.12%' → 17.12"""
    if not text or text == "-":
        return None
    match = re.search(r"([\d.]+)\s*%", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _parse_date(text: str) -> str | None:
    """날짜 파싱. 예: '2025.12.04' → '2025-12-04'"""
    if not text or text == "-":
        return None
    text = text.strip()
    # YYYY.MM.DD 형식
    match = re.match(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    return None


EXCLUDE_KEYWORDS = ["스팩", "SPAC", "리츠", "인프라"]


def collect_recent_ipos(pages: int = 5) -> list[dict]:
    """38.co.kr에서 최근 수요예측 완료 종목을 수집하고 계산 지표를 추가한다.

    스팩, 리츠 등은 자동 제외한다.

    Returns:
        정제된 IPO 데이터 리스트 (최신순 정렬)
    """
    raw_list = get_demand_forecast_list(pages=pages)

    # 스팩, 리츠 제외
    raw_list = [
        item for item in raw_list
        if not any(kw in item.get("name", "") for kw in EXCLUDE_KEYWORDS)
    ]

    results = []
    for item in raw_list:
        band_low, band_high = _parse_price_range(item.get("offering_price_range", ""))
        confirmed = _parse_price(item.get("confirmed_price", ""))
        first_price = _parse_price(item.get("first_price", ""))
        competition = _parse_competition(item.get("competition_rate", ""))
        commitment = _parse_commitment(item.get("commitment_rate", ""))
        demand_date = _parse_date(item.get("demand_date", ""))

        # 밴드 내 위치 계산 (0% = 하단, 100% = 상단)
        band_position = None
        if band_low and band_high and confirmed and band_high > band_low:
            band_position = round((confirmed - band_low) / (band_high - band_low) * 100, 1)
        elif band_low and band_high and confirmed and band_high == band_low:
            band_position = 100.0

        # 시초가 수익률 (공모가 대비)
        first_day_return = None
        if confirmed and first_price and confirmed > 0:
            first_day_return = round((first_price - confirmed) / confirmed * 100, 1)

        results.append({
            "name": item.get("name", ""),
            "no": item.get("no", ""),
            "demand_date": demand_date,
            "demand_date_raw": item.get("demand_date", ""),
            "band_low": band_low,
            "band_high": band_high,
            "confirmed_price": confirmed,
            "first_price": first_price,
            "competition_ratio": competition,
            "commitment_pct": commitment,
            "underwriter": item.get("underwriter", ""),
            "band_position": band_position,
            "first_day_return": first_day_return,
            "raw": item,
        })

    # 시초가 이상치 필터 (공모가 대비 3000%+ 수익률은 파싱 오류 가능성)
    for ipo in results:
        if ipo.get("first_day_return") is not None and ipo["first_day_return"] > 3000:
            ipo["first_price"] = None
            ipo["first_day_return"] = None
            ipo["_note"] = "시초가 이상치 제외"

    # 날짜 기준 정렬 (최신순)
    results.sort(key=lambda x: x.get("demand_date") or "", reverse=True)

    return results


def filter_recent_months(ipos: list[dict], months: int = 3) -> list[dict]:
    """최근 N개월 내 수요예측 종목만 필터링."""
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    return [
        ipo for ipo in ipos
        if ipo.get("demand_date") and ipo["demand_date"] >= cutoff
    ]


def save_history(ipos: list[dict]) -> Path:
    """캘리브레이션 데이터를 JSON으로 저장."""
    # raw 필드 제거 (저장 용량 절약)
    save_data = []
    for ipo in ipos:
        entry = {k: v for k, v in ipo.items() if k != "raw"}
        save_data.append(entry)

    HISTORY_FILE.write_text(
        json.dumps(save_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[캘리브레이션] {len(save_data)}건 저장 → {HISTORY_FILE}")
    return HISTORY_FILE


def load_history() -> list[dict]:
    """저장된 캘리브레이션 데이터를 로드."""
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def compute_calibration_stats(ipos: list[dict]) -> dict:
    """캘리브레이션 통계 계산.

    Returns:
        dict with keys:
        - total: 총 종목 수
        - with_first_price: 시초가 있는 종목 수
        - avg_first_day_return: 평균 시초가 수익률
        - avg_band_position: 평균 밴드 위치
        - avg_competition: 평균 경쟁률
        - band_upper_pct: 밴드 상단(80%+) 확정 비율
        - positive_return_pct: 양의 수익률 비율
        - by_verdict: AI 판단별 통계 (판단 데이터가 있는 경우)
    """
    total = len(ipos)
    with_fp = [i for i in ipos if i.get("first_day_return") is not None]
    with_band = [i for i in ipos if i.get("band_position") is not None]
    with_comp = [i for i in ipos if i.get("competition_ratio") is not None]

    stats = {
        "total": total,
        "with_first_price": len(with_fp),
        "avg_first_day_return": (
            round(sum(i["first_day_return"] for i in with_fp) / len(with_fp), 1)
            if with_fp else None
        ),
        "median_first_day_return": None,
        "avg_band_position": (
            round(sum(i["band_position"] for i in with_band) / len(with_band), 1)
            if with_band else None
        ),
        "avg_competition": (
            round(sum(i["competition_ratio"] for i in with_comp) / len(with_comp), 1)
            if with_comp else None
        ),
        "band_upper_pct": (
            round(sum(1 for i in with_band if i["band_position"] >= 80) / len(with_band) * 100, 1)
            if with_band else None
        ),
        "positive_return_pct": (
            round(sum(1 for i in with_fp if i["first_day_return"] > 0) / len(with_fp) * 100, 1)
            if with_fp else None
        ),
    }

    # 중앙값 계산
    if with_fp:
        sorted_returns = sorted(i["first_day_return"] for i in with_fp)
        mid = len(sorted_returns) // 2
        if len(sorted_returns) % 2 == 0:
            stats["median_first_day_return"] = round(
                (sorted_returns[mid - 1] + sorted_returns[mid]) / 2, 1
            )
        else:
            stats["median_first_day_return"] = sorted_returns[mid]

    # AI 판단별 통계
    by_verdict = {}
    for ipo in ipos:
        v = ipo.get("ai_verdict")
        if not v:
            continue
        if v not in by_verdict:
            by_verdict[v] = {"count": 0, "returns": [], "band_positions": []}
        by_verdict[v]["count"] += 1
        if ipo.get("first_day_return") is not None:
            by_verdict[v]["returns"].append(ipo["first_day_return"])
        if ipo.get("band_position") is not None:
            by_verdict[v]["band_positions"].append(ipo["band_position"])

    for v, d in by_verdict.items():
        d["avg_return"] = (
            round(sum(d["returns"]) / len(d["returns"]), 1) if d["returns"] else None
        )
        d["avg_band_position"] = (
            round(sum(d["band_positions"]) / len(d["band_positions"]), 1)
            if d["band_positions"] else None
        )
        d["positive_pct"] = (
            round(sum(1 for r in d["returns"] if r > 0) / len(d["returns"]) * 100, 1)
            if d["returns"] else None
        )

    stats["by_verdict"] = by_verdict
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=12, help="최근 N개월 (기본: 12)")
    parser.add_argument("--pages", type=int, default=15, help="크롤링 페이지 수 (기본: 15)")
    args = parser.parse_args()

    print(f"=== IPO 캘리브레이션 데이터 수집 (최근 {args.months}개월) ===")
    all_ipos = collect_recent_ipos(pages=args.pages)
    print(f"전체 수집: {len(all_ipos)}건")

    recent = filter_recent_months(all_ipos, months=args.months)
    print(f"최근 {args.months}개월: {len(recent)}건")

    save_history(recent)

    stats = compute_calibration_stats(recent)
    print(f"\n--- 통계 ---")
    print(f"총 종목: {stats['total']}")
    print(f"시초가 있는 종목: {stats['with_first_price']}")
    print(f"평균 시초가 수익률: {stats['avg_first_day_return']}%")
    print(f"밴드 상단(80%+) 비율: {stats['band_upper_pct']}%")
    print(f"양의 수익률 비율: {stats['positive_return_pct']}%")
