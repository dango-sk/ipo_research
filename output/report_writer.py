"""마크다운 리포트 생성 모듈

AI 분석 결과 + 수집 데이터를 마크다운 파일로 저장한다.
"""

from datetime import datetime
from pathlib import Path

from config.settings import REPORTS_DIR


def save_report(
    company_name: str,
    analysis_report: str,
    data: dict,
) -> Path:
    """분석 리포트를 마크다운 파일로 저장한다."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    filename = f"{today}_{company_name}_리서치.md"
    filepath = REPORTS_DIR / filename

    content_parts = [analysis_report]

    # 데이터 요약 부록
    content_parts.append("\n\n---\n\n## 부록: 수집 데이터 요약\n")

    # 재무제표 테이블
    if "financials" in data and data["financials"]:
        content_parts.append("### 재무제표\n")
        content_parts.append("| 연도 | 매출액 | 영업이익 | 당기순이익 | 자산총계 | 부채총계 |")
        content_parts.append("|------|--------|----------|-----------|---------|---------|")
        for row in data["financials"]:
            content_parts.append(
                f"| {row.get('year', '')} "
                f"| {_fmt_num(row.get('revenue'))} "
                f"| {_fmt_num(row.get('operating_income'))} "
                f"| {_fmt_num(row.get('net_income'))} "
                f"| {_fmt_num(row.get('total_assets'))} "
                f"| {_fmt_num(row.get('total_liabilities'))} |"
            )
        content_parts.append("")

    # 유통가능주식수
    if "lockup_schedule" in data and data["lockup_schedule"]:
        content_parts.append("### 유통가능주식수\n")
        content_parts.append("| 기간 | 주식수 | 비율 | 누적비율 |")
        content_parts.append("|------|--------|------|---------|")
        for item in data["lockup_schedule"]:
            content_parts.append(
                f"| {item.get('period', '')} "
                f"| {_fmt_shares(item.get('shares'))} "
                f"| {_fmt_pct(item.get('ratio'))} "
                f"| {_fmt_pct(item.get('cumulative_ratio'))} |"
            )
        content_parts.append("")

    content_parts.append(f"\n\n---\n*생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    filepath.write_text("\n".join(content_parts), encoding="utf-8")
    print(f"[리포트] 저장 완료: {filepath}")
    return filepath


def _fmt_num(val) -> str:
    """숫자를 억원 단위로 포맷."""
    if val is None:
        return "-"
    try:
        v = int(val)
        if abs(v) >= 100_000_000:
            return f"{v / 100_000_000:,.1f}억"
        elif abs(v) >= 10_000:
            return f"{v / 10_000:,.0f}만"
        else:
            return f"{v:,}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_shares(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{int(val):,}주"
    except (ValueError, TypeError):
        return str(val)


def _fmt_pct(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(val)
