"""IPO Research Dashboard

사용법:
    streamlit run dashboard.py
"""

import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

# ─────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).parent / "data" / "reports"

st.set_page_config(
    page_title="IPO Research Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────────────────
@st.cache_data
def load_data(filepath: str) -> dict:
    return json.loads(Path(filepath).read_text(encoding="utf-8"))


def find_data_files() -> dict[str, Path]:
    """reports 디렉토리에서 *_data.json 파일들을 찾는다."""
    files = {}
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.glob("*_data.json"), reverse=True):
            # 20260225_리브스메드_data.json → "리브스메드 (2026-02-25)"
            parts = f.stem.replace("_data", "").split("_", 1)
            if len(parts) == 2:
                date_str = parts[0]
                name = parts[1]
                label = f"{name} ({date_str[:4]}-{date_str[4:6]}-{date_str[6:]})"
            else:
                label = f.stem
            files[label] = f
    return files


def _clean_company_name(name: str) -> str:
    """(주), 주식회사 등 접두어를 제거한다."""
    for prefix in ["(주)", "주식회사 ", "㈜"]:
        name = name.replace(prefix, "")
    return name.strip()


# ─────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────
def fmt_억(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val) / 1e8:,.0f}억"
    except (ValueError, TypeError):
        return str(val)


def fmt_조(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val) / 1e12:,.1f}조"
    except (ValueError, TypeError):
        return str(val)


def fmt_pct(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(val)


def fmt_원(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{int(val):,}원"
    except (ValueError, TypeError):
        return str(val)


def safe_num(val, default=0):
    """None이면 default 반환."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


COLORS = {
    "primary": "#4472C4",
    "accent": "#ED7D31",
    "positive": "#00B050",
    "negative": "#FF4444",
    "positive_light": "rgba(0, 176, 80, 0.5)",
    "negative_light": "rgba(255, 68, 68, 0.5)",
    "neutral": "#7F7F7F",
}


# ─────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 IPO Research")
    st.divider()

    data_files = find_data_files()
    if not data_files:
        st.error("데이터 파일이 없습니다. `python main.py <종목명>`으로 먼저 분석을 실행하세요.")
        st.stop()

    selected = st.selectbox("종목 선택", list(data_files.keys()))
    data = load_data(str(data_files[selected]))

    st.divider()

    # 새 종목 분석 실행
    st.subheader("새 종목 분석")
    new_company = st.text_input("회사명", placeholder="예: 리브스메드")
    if st.button("분석 실행", type="primary", use_container_width=True):
        if new_company:
            with st.spinner(f"'{new_company}' 분석 중... (3~5분 소요)"):
                import subprocess

                result = subprocess.run(
                    [sys.executable, "main.py", new_company],
                    capture_output=True,
                    text=True,
                    cwd=str(Path(__file__).parent),
                    timeout=600,
                )
                if result.returncode == 0:
                    st.success("분석 완료! 페이지를 새로고침하세요.")
                    st.rerun()
                else:
                    st.error(f"분석 실패:\n{result.stderr[-500:]}")

# ─────────────────────────────────────────────────────────
# 메인 영역
# ─────────────────────────────────────────────────────────
company_info = data.get("company_info", {})
offering = data.get("offering", {})
crawler = data.get("crawler_data", {})
financials = data.get("financials", [])
valuation = data.get("valuation", {})
lockup = data.get("lockup_schedule", [])
business = data.get("business", {})

# 파일명에서 추출한 이름 사용 (selected = "리브스메드 (2026-02-25)")
display_name = selected.split(" (")[0]
company_name = _clean_company_name(company_info.get("corp_name", display_name))

# ─── 헤더 ───
st.markdown(f"# {company_name} IPO 리서치")

securities = offering.get("securities", [{}])
sec = securities[0] if securities else {}

# ─── 핵심 지표 카드 ───
cols = st.columns(5)

confirmed_price = crawler.get("confirmed_price", "")
offering_price = sec.get("offering_price")

if confirmed_price:
    cols[0].metric("확정공모가", f"{confirmed_price}원")
elif offering_price:
    cols[0].metric("공모가", fmt_원(offering_price))
else:
    cols[0].metric("공모가", "-")

cols[1].metric("공모주식수", f"{sec['count']:,}주" if sec.get("count") else "-")
cols[2].metric("기관경쟁률", crawler.get("institutional_competition", "-"))
cols[3].metric("의무보유확약", crawler.get("lockup_commitment", "-"))

if valuation.get("applied_multiple"):
    cols[4].metric("적용 PER", f"{valuation['applied_multiple']}배")
else:
    cols[4].metric("적용 PER", "-")

st.divider()

# ─────────────────────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📋 개요", "💰 재무", "📈 밸류에이션", "🔄 수급", "🏢 사업분석", "📝 AI 리포트"]
)

# ═══════════════════════════════════════════════════════════
# 탭 1: 개요
# ═══════════════════════════════════════════════════════════
with tab1:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("공모 개요")

        overview_data = {
            "대표이사": company_info.get("ceo_nm", "-"),
            "설립일": company_info.get("est_dt", "-"),
            "업종": company_info.get("induty_code", "-"),
            "홈페이지": company_info.get("hm_url", "-"),
        }
        for k, v in overview_data.items():
            st.markdown(f"**{k}**: {v}")

        st.markdown("---")
        st.subheader("공모사항")
        offering_data = {
            "공모가 밴드": offering.get("crawler_offering_price_range", "-"),
            "확정공모가": f"{confirmed_price}원" if confirmed_price else "-",
            "공모주식수": f"{sec['count']:,}주" if sec.get("count") else "-",
            "공모총액": fmt_억(sec.get("total_amount")) if sec.get("total_amount") else "-",
            "공모방법": sec.get("method", "-"),
        }
        for k, v in offering_data.items():
            st.markdown(f"**{k}**: {v}")

    with col_r:
        st.subheader("일정")
        schedule = {
            "수요예측일": crawler.get("demand_forecast_date", "-"),
            "청약일": offering.get("subscription_date", "") or crawler.get("subscription_date", "-"),
            "납입일": offering.get("payment_date", "-"),
            "상장예정일": crawler.get("listing_date", "-"),
            "주관사": crawler.get("lead_underwriter", "-"),
        }
        for k, v in schedule.items():
            st.markdown(f"**{k}**: {v}")

        st.markdown("---")
        st.subheader("수요예측 결과")
        demand = {
            "기관경쟁률": crawler.get("institutional_competition", "-"),
            "의무보유확약": crawler.get("lockup_commitment", "-"),
            "기관배정": crawler.get("institutional_allocation", "-"),
            "일반배정": crawler.get("retail_allocation", "-"),
        }
        for k, v in demand.items():
            if v and v != "-":
                st.markdown(f"**{k}**: {v}")

        # 주관사 목록
        underwriters = offering.get("underwriters", [])
        if underwriters:
            st.markdown("---")
            st.subheader("주관사")
            for uw in underwriters:
                name = uw.get("name", "")
                amt = uw.get("amount")
                if name:
                    st.markdown(f"- {name}" + (f" ({fmt_억(amt)})" if amt else ""))


# ═══════════════════════════════════════════════════════════
# 탭 2: 재무
# ═══════════════════════════════════════════════════════════
with tab2:
    if not financials:
        st.info("재무제표 데이터가 없습니다.")
    else:
        years = [str(f.get("year", "")) for f in financials]
        revenues = [f.get("revenue") for f in financials]
        op_incomes = [f.get("operating_income") for f in financials]
        net_incomes = [f.get("net_income") for f in financials]

        # 매출 & 이익 차트
        col1, col2 = st.columns(2)

        with col1:
            fig_rev = go.Figure()
            fig_rev.add_trace(go.Bar(
                x=years,
                y=[safe_num(r) / 1e8 for r in revenues],
                name="매출액",
                marker_color=COLORS["primary"],
                text=[fmt_억(r) for r in revenues],
                textposition="outside",
            ))
            fig_rev.update_layout(
                title="매출액 추이 (억원)",
                yaxis_title="억원",
                height=400,
                showlegend=False,
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_rev, use_container_width=True)

        with col2:
            fig_profit = go.Figure()
            fig_profit.add_trace(go.Bar(
                x=years,
                y=[safe_num(o) / 1e8 for o in op_incomes],
                name="영업이익",
                marker_color=[
                    COLORS["positive"] if safe_num(o) >= 0 else COLORS["negative"]
                    for o in op_incomes
                ],
                text=[fmt_억(o) for o in op_incomes],
                textposition="outside",
            ))
            fig_profit.add_trace(go.Bar(
                x=years,
                y=[safe_num(n) / 1e8 for n in net_incomes],
                name="당기순이익",
                marker_color=[
                    COLORS["positive_light"] if safe_num(n) >= 0 else COLORS["negative_light"]
                    for n in net_incomes
                ],
                text=[fmt_억(n) for n in net_incomes],
                textposition="outside",
            ))
            fig_profit.update_layout(
                title="영업이익 / 순이익 (억원)",
                yaxis_title="억원",
                height=400,
                barmode="group",
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_profit, use_container_width=True)

        # 성장률 차트
        yoy_data = [
            (f.get("year"), f.get("revenue_yoy"))
            for f in financials
            if f.get("revenue_yoy") is not None
        ]
        if yoy_data:
            fig_yoy = go.Figure()
            fig_yoy.add_trace(go.Scatter(
                x=[str(y) for y, _ in yoy_data],
                y=[v * 100 for _, v in yoy_data],
                mode="lines+markers+text",
                text=[f"{v*100:.1f}%" for _, v in yoy_data],
                textposition="top center",
                line=dict(color=COLORS["accent"], width=3),
                marker=dict(size=10),
            ))
            fig_yoy.update_layout(
                title="매출 YoY 성장률 (%)",
                yaxis_title="%",
                height=350,
                showlegend=False,
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_yoy, use_container_width=True)

        # 재무 테이블
        st.subheader("재무제표 상세")
        table_rows = []
        for f in financials:
            table_rows.append({
                "연도": f.get("year", ""),
                "매출액": fmt_억(f.get("revenue")),
                "영업이익": fmt_억(f.get("operating_income")),
                "당기순이익": fmt_억(f.get("net_income")),
                "자산총계": fmt_억(f.get("total_assets")),
                "부채총계": fmt_억(f.get("total_liabilities")),
                "자본총계": fmt_억(f.get("total_equity")),
                "매출YoY": fmt_pct(f.get("revenue_yoy")) if f.get("revenue_yoy") is not None else "-",
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        source = financials[0].get("source", "DART API") if financials else ""
        if source == "증권신고서":
            st.caption("* 재무제표 출처: 증권신고서 (DART API 미제공 기업)")


# ═══════════════════════════════════════════════════════════
# 탭 3: 밸류에이션
# ═══════════════════════════════════════════════════════════
with tab3:
    if not valuation:
        st.info("밸류에이션 데이터가 없습니다.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("공모가 산출")
            val_items = {
                "밸류에이션 방법": valuation.get("valuation_method", "-"),
                "기준 지표": valuation.get("base_metric", "-"),
                "기준 값": fmt_억(valuation.get("base_value")) if valuation.get("base_value") else "-",
                "적용 배수": f"{valuation['applied_multiple']}배" if valuation.get("applied_multiple") else "-",
                "할인율": fmt_pct(valuation.get("discount_rate")) if valuation.get("discount_rate") else "-",
                "주당 평가가액": fmt_원(valuation.get("per_share_value")),
            }
            for k, v in val_items.items():
                st.markdown(f"**{k}**: {v}")

            price_range = valuation.get("offering_price_range", {})
            if price_range:
                st.markdown(
                    f"**희망 공모가**: {fmt_원(price_range.get('low'))} ~ {fmt_원(price_range.get('high'))}"
                )

        with col2:
            # 공모가 vs 이론가 비교
            per_share = valuation.get("per_share_value")
            if per_share and confirmed_price:
                try:
                    cp = int(str(confirmed_price).replace(",", ""))
                    discount = (per_share - cp) / per_share
                    fig_price = go.Figure()
                    fig_price.add_trace(go.Bar(
                        x=["주당 평가가액", "확정 공모가"],
                        y=[per_share, cp],
                        marker_color=[COLORS["neutral"], COLORS["primary"]],
                        text=[fmt_원(per_share), fmt_원(cp)],
                        textposition="outside",
                    ))
                    fig_price.update_layout(
                        title=f"공모가 할인율: {discount*100:.1f}%",
                        yaxis_title="원",
                        height=350,
                        showlegend=False,
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_price, use_container_width=True)
                except (ValueError, TypeError):
                    pass

        # Peer 비교
        peers = valuation.get("peers", [])
        if peers:
            st.divider()
            st.subheader("Peer Group 비교")

            # PER 비교 차트
            peer_names = [p.get("name", "") for p in peers]
            peer_pers = [p.get("per") for p in peers]
            avg_per = valuation.get("average_peer_per") or valuation.get("applied_multiple")

            if any(p is not None for p in peer_pers):
                fig_per = go.Figure()
                fig_per.add_trace(go.Bar(
                    x=peer_names,
                    y=[safe_num(p) for p in peer_pers],
                    marker_color=COLORS["primary"],
                    text=[f"{p:.1f}x" if p else "-" for p in peer_pers],
                    textposition="outside",
                ))
                if avg_per:
                    fig_per.add_hline(
                        y=float(avg_per),
                        line_dash="dash",
                        line_color=COLORS["accent"],
                        annotation_text=f"적용 PER {avg_per}x",
                        annotation_position="top right",
                    )
                fig_per.update_layout(
                    title="비교회사 PER",
                    yaxis_title="PER (배)",
                    height=400,
                    showlegend=False,
                    plot_bgcolor="white",
                )
                st.plotly_chart(fig_per, use_container_width=True)

            # 매출 비교 차트 (Peer vs 대상기업)
            peer_revs = [p.get("revenue") for p in peers]
            if any(r is not None for r in peer_revs):
                # 대상기업 최근 매출
                target_rev = None
                if financials:
                    target_rev = financials[-1].get("revenue")

                fig_rev_comp = go.Figure()
                all_names = peer_names + ([company_name] if target_rev else [])
                all_revs = [safe_num(r) / 1e12 for r in peer_revs] + (
                    [safe_num(target_rev) / 1e12] if target_rev else []
                )
                all_colors = [COLORS["primary"]] * len(peers) + (
                    [COLORS["accent"]] if target_rev else []
                )
                fig_rev_comp.add_trace(go.Bar(
                    x=all_names,
                    y=all_revs,
                    marker_color=all_colors,
                    text=[f"{v:.1f}조" if v >= 0.1 else f"{v*1000:.0f}억" for v in all_revs],
                    textposition="outside",
                ))
                fig_rev_comp.update_layout(
                    title="매출 규모 비교 (조원)",
                    yaxis_title="조원",
                    height=400,
                    showlegend=False,
                    plot_bgcolor="white",
                )
                st.plotly_chart(fig_rev_comp, use_container_width=True)

            # Peer 테이블
            peer_table = []
            for p in peers:
                peer_table.append({
                    "회사": p.get("name", ""),
                    "거래소": p.get("market", ""),
                    "매출액": fmt_조(p.get("revenue")) if p.get("revenue") else "-",
                    "영업이익": fmt_조(p.get("operating_income")) if p.get("operating_income") else "-",
                    "당기순이익": fmt_조(p.get("net_income")) if p.get("net_income") else "-",
                    "PER": f"{p['per']:.1f}x" if p.get("per") else "-",
                })
            st.dataframe(peer_table, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# 탭 4: 수급
# ═══════════════════════════════════════════════════════════
with tab4:
    if not lockup:
        st.info("유통가능주식수 데이터가 없습니다.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            # 파이 차트: 상장일 유통 vs 보호예수
            first = lockup[0]
            listing_ratio = safe_num(first.get("ratio", 0))
            lockup_ratio = max(0, 1 - listing_ratio)

            fig_pie = go.Figure(data=[go.Pie(
                labels=["상장일 유통가능", "보호예수"],
                values=[listing_ratio, lockup_ratio],
                marker_colors=[COLORS["accent"], COLORS["primary"]],
                textinfo="label+percent",
                hole=0.4,
            )])
            fig_pie.update_layout(
                title="상장일 유통 비율",
                height=400,
                showlegend=False,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            # 누적 유통비율 차트
            periods = [item.get("period", "") for item in lockup]
            cum_ratios = [min(safe_num(item.get("cumulative_ratio", 0)) * 100, 100) for item in lockup]
            shares_list = [safe_num(item.get("shares", 0)) for item in lockup]

            fig_lockup = go.Figure()
            fig_lockup.add_trace(go.Bar(
                x=periods,
                y=[s / 10000 for s in shares_list],
                name="유통 주식수",
                marker_color=COLORS["primary"],
                yaxis="y",
            ))
            fig_lockup.add_trace(go.Scatter(
                x=periods,
                y=cum_ratios,
                name="누적 비율",
                mode="lines+markers+text",
                text=[f"{r:.1f}%" for r in cum_ratios],
                textposition="top center",
                line=dict(color=COLORS["accent"], width=3),
                marker=dict(size=8),
                yaxis="y2",
            ))
            fig_lockup.update_layout(
                title="유통가능주식 & 누적비율",
                yaxis=dict(title="주식수 (만주)", side="left"),
                yaxis2=dict(title="누적 비율 (%)", side="right", overlaying="y", range=[0, 110]),
                height=400,
                plot_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_lockup, use_container_width=True)

        # 유통 테이블
        st.subheader("유통가능주식수 상세")
        lockup_table = []
        for item in lockup:
            lockup_table.append({
                "기간": item.get("period", ""),
                "주식수": f"{int(safe_num(item.get('shares', 0))):,}주",
                "비율": fmt_pct(item.get("ratio")),
                "누적비율": fmt_pct(item.get("cumulative_ratio")),
            })
        st.dataframe(lockup_table, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# 탭 5: 사업분석
# ═══════════════════════════════════════════════════════════
with tab5:
    if not business:
        st.info("사업 분석 데이터가 없습니다.")
    else:
        st.subheader("회사 개요")
        st.write(business.get("company_overview", ""))

        st.subheader("핵심 사업")
        st.write(business.get("main_business", ""))

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("주요 제품")
            products = business.get("products", [])
            if products:
                for p in products:
                    name = p.get("name", "")
                    desc = p.get("description", "")
                    share = p.get("revenue_share")
                    share_str = f" ({float(share)*100:.0f}%)" if share else ""
                    st.markdown(f"**{name}{share_str}**")
                    if desc:
                        st.caption(desc)

                # 제품별 매출 비중 차트 - 중복 이름 합산
                revenue_by_name: dict[str, float] = {}
                for p in products:
                    if p.get("revenue_share"):
                        name = p.get("name", "기타")
                        revenue_by_name[name] = revenue_by_name.get(name, 0) + float(p["revenue_share"])
                if revenue_by_name:
                    fig_prod = go.Figure(data=[go.Pie(
                        labels=list(revenue_by_name.keys()),
                        values=list(revenue_by_name.values()),
                        hole=0.35,
                        textinfo="label+percent",
                    )])
                    fig_prod.update_layout(title="매출 구성", height=300, showlegend=False)
                    st.plotly_chart(fig_prod, use_container_width=True)

        with col2:
            st.subheader("핵심 기술")
            st.write(business.get("key_technology", "-"))

            st.subheader("시장 규모")
            st.write(business.get("market_size", "-"))

            st.subheader("성장 전략")
            st.write(business.get("growth_strategy", "-"))

            competitors = business.get("competitors", [])
            if competitors and competitors != ["정보 없음"]:
                st.subheader("주요 경쟁사")
                for c in competitors:
                    st.markdown(f"- {c}")


# ═══════════════════════════════════════════════════════════
# 탭 6: AI 리포트
# ═══════════════════════════════════════════════════════════
with tab6:
    # 마크다운 리포트 파일 찾기 - display_name 사용 (파일명 기준)
    md_files = sorted(REPORTS_DIR.glob(f"*_{display_name}_리서치.md"), reverse=True)
    if not md_files:
        # corp_name에서 (주) 제거 후 재시도
        clean_name = _clean_company_name(company_info.get("corp_name", display_name))
        md_files = sorted(REPORTS_DIR.glob(f"*_{clean_name}_리서치.md"), reverse=True)

    if md_files:
        report_text = md_files[0].read_text(encoding="utf-8")
        st.markdown(report_text)
    else:
        st.info("AI 분석 리포트가 없습니다. `--skip-analysis` 없이 파이프라인을 실행하세요.")
