"""IPO Research Dashboard — v2

2-panel layout: 좌측 판단 요약 + 우측 상세 분석 탭
사용법:
    streamlit run dashboard.py --server.port 8503
"""

import json
import os
import re
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

# ──────────────────────────────────────────────��──────────
# 설정
# ─────────────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).parent / "data" / "reports"
CALIBRATION_FILE = Path(__file__).parent / "data" / "calibration" / "ipo_history.json"

st.set_page_config(
    page_title="IPO Research",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────
# 스타일
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── 사이드바 ── */
    section[data-testid="stSidebar"] { width: 260px !important; min-width: 260px !important; }

    /* ── 전체 배경 ── */
    .stApp { background-color: #0e1117; }
    header[data-testid="stHeader"] { background-color: #0e1117; }
    .block-container { padding-top: 2.5rem; padding-bottom: 1rem; }

    /* ── 판단 배너 ── */
    .verdict-card {
        padding: 1.4rem 1.6rem;
        border-radius: 14px;
        margin-bottom: 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .verdict-card h2 {
        margin: 0;
        font-size: 1.25rem;
        font-weight: 800;
        letter-spacing: -0.3px;
    }
    .verdict-card .summary {
        margin: 0.6rem 0 0 0;
        font-size: 0.88rem;
        opacity: 0.92;
        line-height: 1.55;
    }
    .verdict-positive { background: linear-gradient(135deg, #0d4a2e 0%, #0a3d25 100%); border: 1px solid #1a7a4a; }
    .verdict-positive h2 { color: #4ade80; }
    .verdict-positive .summary { color: #bbf7d0; }
    .verdict-neutral { background: linear-gradient(135deg, #3b3100 0%, #302800 100%); border: 1px solid #7a6a1a; }
    .verdict-neutral h2 { color: #fbbf24; }
    .verdict-neutral .summary { color: #fef3c7; }
    .verdict-negative { background: linear-gradient(135deg, #4a0d0d 0%, #3d0a0a 100%); border: 1px solid #7a1a1a; }
    .verdict-negative h2 { color: #f87171; }
    .verdict-negative .summary { color: #fecaca; }

    /* ── 판단 근거 ── */
    .verdict-reasons {
        text-align: left;
        margin-top: 0.9rem;
        padding-top: 0.8rem;
        border-top: 1px solid rgba(255,255,255,0.10);
    }
    .reason-item {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
        margin-bottom: 0.55rem;
        font-size: 0.84rem;
        color: #d1d5db;
        line-height: 1.55;
    }
    .reason-icon {
        flex-shrink: 0;
        width: 18px;
        text-align: center;
        font-weight: 700;
        font-size: 0.9rem;
    }
    .reason-pos .reason-icon { color: #4ade80; }
    .reason-neg .reason-icon { color: #f87171; }
    .reason-neutral .reason-icon { color: #9ca3af; }

    /* ── AI 적정가 블록 ── */
    .fair-price-block {
        margin-top: 0.9rem;
        padding-top: 0.8rem;
        border-top: 1px solid rgba(255,255,255,0.10);
    }
    .fair-price-block .fp-label {
        font-size: 0.65rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.35rem;
    }
    .fair-price-block .fp-headline {
        display: flex;
        align-items: baseline;
        gap: 0.6rem;
        flex-wrap: wrap;
        margin-bottom: 0.3rem;
    }
    .fair-price-block .fp-value {
        font-size: 1.1rem;
        font-weight: 800;
        color: #fbbf24;
    }
    .fair-price-block .fp-vs {
        font-size: 0.78rem;
        color: #9ca3af;
    }
    .fair-price-block .fp-method {
        font-size: 0.73rem;
        color: #6b7280;
        margin-bottom: 0.5rem;
    }
    .fair-price-block .fp-steps {
        background: rgba(255,255,255,0.03);
        border-radius: 8px;
        padding: 0.55rem 0.7rem;
        margin-bottom: 0.5rem;
    }
    .fair-price-block .fp-step {
        font-size: 0.74rem;
        color: #c0c5cc;
        margin-bottom: 0.25rem;
        line-height: 1.55;
    }
    .fair-price-block .fp-step:last-child { margin-bottom: 0; }
    .fair-price-block .fp-step-label {
        color: #7a7f88;
        font-weight: 600;
    }
    .fair-price-block .fp-strategy {
        font-size: 0.8rem;
        color: #fbbf24;
        font-weight: 600;
        margin-top: 0.5rem;
    }

    /* ── 지표 카드 ── */
    .metric-card {
        background: #1a1d24;
        border: 1px solid #2a2d34;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        text-align: center;
        min-height: 82px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.2);
        transition: border-color 0.2s;
    }
    .metric-card:hover { border-color: #3a3f48; }
    .metric-card .label {
        font-size: 0.65rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.25rem;
    }
    .metric-card .value {
        font-size: 1.05rem;
        font-weight: 700;
        color: #f3f4f6;
    }
    .metric-card .sub {
        font-size: 0.63rem;
        color: #6b7280;
        margin-top: 0.15rem;
    }

    /* ── 체크포인트 ── */
    .checkpoint-compact {
        background: #1a1d24;
        border-left: 3px solid #f59e0b;
        padding: 0.5rem 0.85rem;
        margin-bottom: 0.4rem;
        border-radius: 0 8px 8px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.15);
    }
    .checkpoint-compact .cp-title {
        color: #fbbf24;
        font-size: 0.76rem;
        font-weight: 700;
    }
    .checkpoint-compact .cp-desc {
        color: #b0b5bd;
        font-size: 0.72rem;
        line-height: 1.5;
        margin-top: 0.12rem;
    }

    /* ── 회사 스냅샷 카드 ── */
    .snapshot-card {
        background: linear-gradient(135deg, #1a1d24 0%, #1e2130 100%);
        border: 1px solid #2a2d34;
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
    }
    .snapshot-card .snap-title {
        font-size: 0.65rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.45rem;
    }
    .snapshot-card .snap-easy {
        font-size: 0.95rem;
        font-weight: 700;
        color: #f3f4f6;
        line-height: 1.55;
        margin-bottom: 0.55rem;
    }
    .snapshot-card .snap-row {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
        margin-bottom: 0.4rem;
        font-size: 0.78rem;
        line-height: 1.5;
    }
    .snapshot-card .snap-label {
        color: #6b7280;
        flex-shrink: 0;
        min-width: 60px;
        font-weight: 600;
    }
    .snapshot-card .snap-value { color: #d1d5db; }
    .snapshot-card .snap-risk { color: #f87171; }
    .snapshot-card .snap-edge { color: #4ade80; }

    /* ── 수익 구조 카드 ── */
    .revenue-flow {
        background: #1a1d24;
        border: 1px solid #2a2d34;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.5rem;
    }
    .revenue-flow .flow-title {
        font-size: 0.72rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.4rem;
    }
    .revenue-flow .flow-desc {
        font-size: 0.85rem;
        color: #e5e7eb;
        line-height: 1.6;
    }

    /* ── Peer 맥락 박스 ── */
    .peer-context {
        background: #1a1d24;
        border-left: 3px solid #3b82f6;
        padding: 0.6rem 0.9rem;
        margin-bottom: 0.8rem;
        border-radius: 0 8px 8px 0;
    }
    .peer-context .ctx-title {
        color: #60a5fa;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .peer-context .ctx-desc {
        color: #b0b5bd;
        font-size: 0.75rem;
        line-height: 1.5;
    }

    /* ── 섹션 헤더 ── */
    .section-header {
        font-size: 1.05rem;
        font-weight: 700;
        color: #e5e7eb;
        padding-bottom: 0.45rem;
        border-bottom: 1px solid #2a2d34;
        margin: 1.4rem 0 0.9rem 0;
    }

    /* ── 밸류에이션 플로우 테이블 ── */
    .val-flow-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin: 0.5rem 0 1rem 0;
    }
    .val-flow-table th {
        background: #1a1d24;
        color: #9ca3af;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        padding: 0.5rem 0.8rem;
        border-bottom: 1px solid #2a2d34;
        text-align: left;
    }
    .val-flow-table td {
        padding: 0.6rem 0.8rem;
        border-bottom: 1px solid #1e2028;
        color: #e5e7eb;
        font-size: 0.85rem;
    }
    .val-flow-table tr:last-child td { border-bottom: none; }
    .val-flow-table .vf-step { color: #6b7280; font-size: 0.7rem; font-weight: 600; }
    .val-flow-table .vf-value { font-weight: 700; font-size: 0.95rem; }
    .val-flow-table .vf-note { color: #6b7280; font-size: 0.72rem; }
    .val-flow-table .vf-highlight {
        background: rgba(99, 102, 241, 0.08);
    }
    .val-flow-table .vf-result {
        background: rgba(99, 102, 241, 0.15);
        border-top: 2px solid #6366f1;
    }
    .val-flow-arrow {
        text-align: center;
        color: #4b5563;
        font-size: 1.1rem;
        padding: 0.2rem 0 !important;
        border-bottom: none !important;
    }

    /* ── 탭 스타일 ── */
    .stTabs [data-baseweb="tab-list"] { gap: 0; }
    .stTabs [data-baseweb="tab"] {
        padding: 0.55rem 1.1rem;
        font-size: 0.84rem;
    }

    /* ── 사이드바 ── */
    section[data-testid="stSidebar"] {
        background-color: #13161c;
        border-right: 1px solid #2a2d34;
    }

    /* ── 텍스트 가독성 ── */
    .stApp p, .stApp li, .stApp td, .stApp th,
    .stApp .stMarkdown, .stApp span {
        color: #e5e7eb !important;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #f9fafb !important;
    }
    .stApp strong, .stApp b { color: #f3f4f6 !important; }
    .stApp a { color: #818cf8 !important; }
    .stApp table { border-collapse: collapse; width: 100%; }
    .stApp table th {
        background-color: #1f2937 !important;
        color: #f3f4f6 !important;
        padding: 0.5rem 0.8rem;
        border: 1px solid #374151;
        font-weight: 600;
    }
    .stApp table td {
        background-color: #111827 !important;
        padding: 0.5rem 0.8rem;
        border: 1px solid #374151;
    }
    .stApp hr { border-color: #374151 !important; }
    .stApp code { color: #c7d2fe !important; background-color: #1e1e2e !important; }
    .stApp pre { background-color: #1e1e2e !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────
COLORS = {
    "primary": "#3b82f6",
    "secondary": "#22d3ee",
    "tertiary": "#a78bfa",
    "accent": "#f59e0b",
    "positive": "#10b981",
    "negative": "#ef4444",
    "positive_light": "rgba(16, 185, 129, 0.45)",
    "negative_light": "rgba(239, 68, 68, 0.45)",
    "neutral": "#94a3b8",
    "bg": "#1a1d24",
    "grid": "#2a2d34",
}

PLOTLY_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e5e7eb", size=12),
    xaxis=dict(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"]),
    yaxis=dict(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"]),
    margin=dict(l=40, r=20, t=40, b=30),
)


@st.cache_data
def load_data(filepath: str) -> dict:
    return json.loads(Path(filepath).read_text(encoding="utf-8"))


def find_data_files() -> dict[str, Path]:
    files = {}
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.glob("*_data.json"), reverse=True):
            parts = f.stem.replace("_data", "").split("_", 1)
            if len(parts) == 2:
                label = parts[1]
            else:
                label = f.stem
            # 같은 종목이면 최신 파일(먼저 등장)만 유지
            if label not in files:
                files[label] = f
    return files


def _clean_company_name(name: str) -> str:
    for prefix in ["(주)", "주식회사 ", "㈜"]:
        name = name.replace(prefix, "")
    return name.strip()


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
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def fmt_margin(revenue, income) -> str:
    rev = safe_num(revenue)
    inc = safe_num(income)
    if rev == 0:
        return "-"
    return f"{inc / rev * 100:.1f}%"


# ─────────────────────────────────────────────────────────
# 분석 실행 (프로그레스 표시)
# ─────────────────────────────────────────────────────────
_PIPELINE_STEPS = [
    ("[Step 1]", "기업 식별 중..."),
    ("[Step 2]", "DART API 데이터 수집 중..."),
    ("[Step 3]", "38.co.kr 수요예측 데이터 수집 중..."),
    ("[Step 4]", "증권신고서 파싱 중... (가장 오래 걸림)"),
    ("[Step 5]", "AI 종합 분석 중..."),
    ("[Step 6]", "리포트 생성 중..."),
]


def run_analysis_with_progress(company_name: str):
    """subprocess로 main.py를 실행하면서 stdout을 파싱해 프로그레스 바를 업데이트한다."""
    import subprocess

    progress_bar = st.progress(0, text=f"'{company_name}' 분석 준비 중...")
    status_text = st.empty()
    log_expander = st.expander("실행 로그 보기", expanded=False)
    log_area = log_expander.empty()
    log_lines = []

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-u", "main.py", company_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path(__file__).parent),
        bufsize=1,
        env=env,
    )

    current_step = 0
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            log_lines.append(line)
            log_area.code("\n".join(log_lines[-30:]), language=None)

            # 파이프라인 스텝 감지
            for i, (marker, desc) in enumerate(_PIPELINE_STEPS):
                if marker in line:
                    current_step = i + 1
                    pct = int(current_step / len(_PIPELINE_STEPS) * 100)
                    progress_bar.progress(
                        min(pct, 95),
                        text=f"({current_step}/{len(_PIPELINE_STEPS)}) {desc}",
                    )
                    status_text.caption(f"🔄 {desc}")
                    break

        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        progress_bar.empty()
        status_text.empty()
        st.error("분석 시간 초과 (10분)")
        return False

    if proc.returncode == 0:
        progress_bar.progress(100, text="분석 완료!")
        status_text.success("분석이 완료되었습니다.")
        return True
    else:
        progress_bar.empty()
        status_text.empty()
        st.error(f"분석 실패:\n{''.join(log_lines[-10:])}")
        return False


# ─────────────────────────────────────────────────────────
# 판단 파싱
# ─────────────────────────────────────────────────────────
def _extract_bullets(text: str) -> list[str]:
    items = re.findall(r"[-•]\s*(.+)", text)
    return [item.strip() for item in items if item.strip()]


def _parse_verdict(report_text: str) -> dict:
    """AI 리포트에서 투자 판단 + 핵심 근거 + 체크포인트를 추출한다."""
    verdict = {
        "signal": "",
        "summary": "",
        "price_opinion": "",
        "fair_price": "",
        "fair_price_vs": "",
        "fair_price_method": "",
        "fair_price_steps": [],
        "participation_strategy": "",
        "reasons": [],
        "positives": [],
        "negatives": [],
        "checkpoints": [],
    }

    # 1) 시그널 추출
    for pattern, signal in [
        (r"\[참여 적극 권고\]", "적극 권고"),
        (r"\[참여 권고\]", "참여 권고"),
        (r"\[조건부 참여\]", "조건부 참여"),
        (r"\[참여 비추천\]", "참여 비추천"),
        (r"\[참여 불가\]", "참여 불가"),
    ]:
        if re.search(pattern, report_text):
            verdict["signal"] = signal
            break

    if not verdict["signal"]:
        # "투자 판단:" 이후 텍스트에서 추출
        judge_match = re.search(r"투자 판단[:\s]*(.+?)(?:\n|$)", report_text)
        if judge_match:
            judge_text = judge_match.group(1).strip().strip("*")
            if "비추천" in judge_text or "불참" in judge_text or "불가" in judge_text:
                verdict["signal"] = "참여 비추천"
            elif "적극" in judge_text:
                verdict["signal"] = "적극 권고"
            elif "권고" in judge_text or "추천" in judge_text:
                verdict["signal"] = "참여 권고"
            elif "조건부" in judge_text or "제한적" in judge_text or "신중" in judge_text:
                verdict["signal"] = "조건부 참여"
            else:
                verdict["signal"] = judge_text[:20]

    # 2) 한 줄 요약
    summary_match = re.search(r"\*\*한 줄 요약\*\*[:\s]*(.+?)(?:\n|$)", report_text)
    if summary_match:
        verdict["summary"] = summary_match.group(1).strip()

    # 2-b) 적정 공모가 의견
    price_match = re.search(r"\*\*적정 공모가 의견\*\*[:\s]*(.+?)(?:\n|$)", report_text)
    if price_match:
        verdict["price_opinion"] = price_match.group(1).strip()
    # "공모가 대비 적정가" 패턴도 처리
    if not verdict["price_opinion"]:
        alt_match = re.search(r"공모가 대비 적정가[:\s]*(.+?)(?:\n|$)", report_text)
        if alt_match:
            verdict["price_opinion"] = alt_match.group(1).strip()
    # "참여 전략" 섹션의 참여 권고 내용
    if not verdict["price_opinion"]:
        strat_match = re.search(r"\*\*참여 전략\*\*\s*\n([\s\S]+?)(?=\n#{1,3}\s|\n---|\n\n\*\*|\Z)", report_text)
        if strat_match:
            lines = [l.strip().lstrip("- ") for l in strat_match.group(1).strip().split("\n") if l.strip()]
            verdict["price_opinion"] = " / ".join(lines[:2])

    # 3) 핵심 근거 추출
    # 전략 A: "핵심 근거" 섹션
    reasons_match = re.search(
        r"\*\*핵심 근거\*\*.*?\n((?:\s*[-•]\s*.+\n?)+)", report_text
    )
    if reasons_match:
        verdict["reasons"] = _extract_bullets(reasons_match.group(1))

    # 전략 B: "긍정 요소" / "부정 요소"
    pos_match = re.search(
        r"\*\*긍정\s*요소\*\*\s*\n((?:\s*[-•]\s*.+\n?)+)", report_text
    )
    neg_match = re.search(
        r"\*\*부정\s*요소\*\*\s*\n((?:\s*[-•]\s*.+\n?)+)", report_text
    )
    if pos_match:
        verdict["positives"] = _extract_bullets(pos_match.group(1))
    if neg_match:
        verdict["negatives"] = _extract_bullets(neg_match.group(1))

    # reasons가 비어 있으면 긍정/부정에서 채움
    if not verdict["reasons"] and (verdict["positives"] or verdict["negatives"]):
        verdict["reasons"] = (verdict["negatives"][:2] + verdict["positives"][:1])

    # 4) 체크포인트
    cp_match = re.search(
        r"(?:#{1,3}\s*(?:⚠️\s*)?핵심 체크포인트)\s*\n([\s\S]+?)(?=\n#{1,3}\s|\n---|\Z)",
        report_text,
    )
    if cp_match:
        cp_text = cp_match.group(1)
        # 번호 형식: "1. **title**: description"
        checkpoints = re.findall(
            r"\d+\.\s*\*\*(.+?)\*\*[:\s]*(.+?)(?=\n\d+\.|\n\n|\Z)",
            cp_text, re.DOTALL,
        )
        # bullet 형식: "- **title**: description"
        if not checkpoints:
            checkpoints = re.findall(
                r"[-•]\s*\*\*(.+?)\*\*[:\s]*(.+?)(?=\n[-•]\s*\*\*|\n\n|\Z)",
                cp_text, re.DOTALL,
            )
        verdict["checkpoints"] = [
            {"title": t.strip(), "description": d.strip().replace("\n", " ")}
            for t, d in checkpoints
        ]

    # 5) AI 적정가 산출 섹션
    fair_match = re.search(
        r"\*\*AI 산출 적정가\*\*[:\s]*(.+?)(?:\n|$)", report_text
    )
    if fair_match:
        verdict["fair_price"] = fair_match.group(1).strip()

    vs_match = re.search(
        r"\*\*현 공모가 대비\*\*[:\s]*(.+?)(?:\n|$)", report_text
    )
    if vs_match:
        verdict["fair_price_vs"] = vs_match.group(1).strip()

    method_match = re.search(
        r"\*\*산출 방법\*\*[:\s]*(.+?)(?:\n|$)", report_text
    )
    if method_match:
        verdict["fair_price_method"] = method_match.group(1).strip()

    # 산출 과정 스텝 파싱
    steps_match = re.search(
        r"\*\*산출 과정\*\*[:\s]*\n([\s\S]+?)(?=\n\*\*AI 산출|\n\*\*추가 검증|\n---|\Z)",
        report_text,
    )
    if steps_match:
        steps_text = steps_match.group(1)
        steps = re.findall(
            r"\d+\.\s*\*\*(.+?)\*\*[:\s]*(.+?)(?=\n\d+\.|\n\n|\Z)",
            steps_text, re.DOTALL,
        )
        verdict["fair_price_steps"] = [
            {"label": s[0].strip(), "value": s[1].strip().replace("\n", " ")}
            for s in steps
        ]

    strategy_match = re.search(
        r"\*\*참여 권고\*\*[:\s]*(.+?)(?:\n|$)", report_text
    )
    if strategy_match:
        verdict["participation_strategy"] = strategy_match.group(1).strip()

    # 6) "이 회사를 한마디로" 섹션
    snapshot = {}
    snapshot_match = re.search(
        r"#{1,3}\s*이 회사를 한마디로\s*\n([\s\S]+?)(?=\n#{1,3}\s|\n---|\Z)",
        report_text,
    )
    if snapshot_match:
        snap_text = snapshot_match.group(1)
        for fields, key in [
            (["사업 개요", "쉬운 설명"], "easy_summary"),
            (["업종"], "industry"),
            (["핵심 경쟁력"], "competitive_edge"),
            (["수익 모델", "돈 버는 구조"], "revenue_model"),
            (["핵심 리스크", "한줄 리스크"], "risk_oneliner"),
            (["산업 해설"], "industry_explainer"),
        ]:
            for field in fields:
                # 산업 해설은 여러 문장일 수 있으므로 다음 필드(- **)까지 매칭
                m = re.search(
                    rf"\*\*{field}\*\*[:\s]*(.+?)(?=\n-\s*\*\*|\n\n|\n#{1,3}\s|\Z)",
                    snap_text, re.DOTALL,
                )
                if m:
                    snapshot[key] = m.group(1).strip()
                    break
    verdict["snapshot"] = snapshot

    return verdict


def _truncate_reason(text: str, max_len: int = 80) -> str:
    """긴 근거 텍스트를 자연스러운 구분점에서 잘라 간결하게 만든다."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    for sep in [", ", " — ", ". ", " - ", " / "]:
        idx = text.find(sep)
        if 0 < idx <= max_len:
            return text[:idx]
    return text[:max_len].rstrip() + "…"


def _render_reasons_html(verdict: dict) -> str:
    parts = []
    positives = verdict.get("positives", [])
    negatives = verdict.get("negatives", [])
    reasons = verdict.get("reasons", [])

    if positives or negatives:
        for item in positives[:2]:
            parts.append(
                f'<div class="reason-item reason-pos">'
                f'<span class="reason-icon">+</span>'
                f'<span>{_truncate_reason(item)}</span></div>'
            )
        for item in negatives[:3]:
            parts.append(
                f'<div class="reason-item reason-neg">'
                f'<span class="reason-icon">-</span>'
                f'<span>{_truncate_reason(item)}</span></div>'
            )
    elif reasons:
        for item in reasons[:4]:
            parts.append(
                f'<div class="reason-item reason-neutral">'
                f'<span class="reason-icon">&#8226;</span>'
                f'<span>{_truncate_reason(item)}</span></div>'
            )

    return "\n".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────
# 차트 빌더
# ─────────────────────────────────────────────────────────
def build_revenue_chart(years, revenues):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years,
        y=[safe_num(r) / 1e8 for r in revenues],
        name="매출액",
        marker_color=COLORS["primary"],
        text=[fmt_억(r) for r in revenues],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    fig.update_layout(title="매출액 (억원)", height=360, showlegend=False, **PLOTLY_LAYOUT)
    return fig


def build_profit_chart(years, op_incomes, net_incomes):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years,
        y=[safe_num(o) / 1e8 for o in op_incomes],
        name="영업이익",
        marker_color=[COLORS["secondary"] if safe_num(o) >= 0 else COLORS["negative"] for o in op_incomes],
        text=[fmt_억(o) for o in op_incomes],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    fig.add_trace(go.Bar(
        x=years,
        y=[safe_num(n) / 1e8 for n in net_incomes],
        name="순이익",
        marker_color=[COLORS["tertiary"] if safe_num(n) >= 0 else COLORS["negative_light"] for n in net_incomes],
        text=[fmt_억(n) for n in net_incomes],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    fig.update_layout(title="영업이익 / 순이익 (억원)", height=360, barmode="group", **PLOTLY_LAYOUT)
    return fig


def build_peer_per_chart(company_name, target_per, peers, avg_per):
    names = [company_name] + [p.get("name", "") for p in peers]
    pers = [safe_num(target_per)] + [safe_num(p.get("per")) for p in peers]
    colors = [COLORS["accent"]] + [COLORS["primary"]] * len(peers)

    fig = go.Figure(go.Bar(
        x=names, y=pers,
        marker_color=colors,
        text=[f"{p:.1f}x" if p else "-" for p in pers],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    if avg_per:
        fig.add_hline(
            y=float(avg_per), line_dash="dash", line_color=COLORS["accent"],
            annotation_text=f"Peer 평균 {avg_per}x",
            annotation_position="top right",
            annotation_font_color=COLORS["accent"],
        )
    fig.update_layout(title="PER 비교", height=380, showlegend=False, **PLOTLY_LAYOUT)
    return fig


def build_peer_revenue_chart(company_name, company_revenue, peers):
    names = [company_name] + [p.get("name", "") for p in peers]
    revenues = [safe_num(company_revenue)] + [safe_num(p.get("revenue", 0)) for p in peers]
    revenues_억 = [r / 1e8 for r in revenues]
    colors = [COLORS["accent"]] + [COLORS["primary"]] * len(peers)

    fig = go.Figure(go.Bar(
        y=names, x=revenues_억,
        orientation="h",
        marker_color=colors,
        text=[f"{r:,.0f}억" for r in revenues_억],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    # 로그 스케일 (최대/최소 비율 100배 이상이면)
    max_r = max(revenues_억) if revenues_억 else 1
    min_r = min(r for r in revenues_억 if r > 0) if any(r > 0 for r in revenues_억) else 1
    if max_r / min_r > 100:
        fig.update_layout(xaxis_type="log")

    fig.update_layout(
        title="매출 규모 비교 (억원)",
        height=max(280, 70 * len(names)),
        showlegend=False,
        **PLOTLY_LAYOUT,
    )
    return fig


def build_peer_margin_chart(company_name, company_financials, peers):
    latest = company_financials[-1] if company_financials else {}
    rev = safe_num(latest.get("revenue", 0))
    op = safe_num(latest.get("operating_income", 0))
    company_margin = (op / rev * 100) if rev > 0 else 0

    names = [company_name]
    margins = [company_margin]

    for p in peers:
        p_rev = safe_num(p.get("revenue", 0))
        p_op = safe_num(p.get("operating_income", 0))
        margin = (p_op / p_rev * 100) if p_rev > 0 else 0
        names.append(p.get("name", ""))
        margins.append(margin)

    colors = [COLORS["positive"] if m >= 0 else COLORS["negative"] for m in margins]

    fig = go.Figure(go.Bar(
        x=names, y=margins,
        marker_color=colors,
        text=[f"{m:.1f}%" for m in margins],
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    fig.update_layout(
        title="영업이익률 비교 (%)",
        height=380,
        showlegend=False,
        **PLOTLY_LAYOUT,
    )
    return fig


def build_valuation_waterfall(valuation, confirmed_price_str):
    """공모가 산출 과정 워터폴 차트 — 할인율을 시각적으로 표시"""
    per_share = safe_num(valuation.get("per_share_value"))

    confirmed = 0
    if confirmed_price_str and confirmed_price_str != "-":
        try:
            confirmed = int(str(confirmed_price_str).replace(",", ""))
        except (ValueError, TypeError):
            confirmed = 0

    if per_share == 0:
        return None

    pr = valuation.get("offering_price_range", {})
    low = safe_num(pr.get("low")) if isinstance(pr, dict) else 0
    high = safe_num(pr.get("high")) if isinstance(pr, dict) else 0

    labels = ["주당 평가가액"]
    values = [per_share]
    annotations = [""]

    if high > 0:
        disc_h = round((1 - high / per_share) * 100, 1) if per_share > 0 else 0
        labels.append("밴드 상한")
        values.append(high)
        annotations.append(f"−{disc_h}%")
    if low > 0:
        disc_l = round((1 - low / per_share) * 100, 1) if per_share > 0 else 0
        labels.append("밴드 하한")
        values.append(low)
        annotations.append(f"−{disc_l}%")
    if confirmed > 0:
        disc_c = round((1 - confirmed / per_share) * 100, 1) if per_share > 0 else 0
        labels.append("확정 공모가")
        values.append(confirmed)
        annotations.append(f"−{disc_c}%")

    colors = []
    for i, v in enumerate(values):
        if i == 0:
            colors.append(COLORS["neutral"])
        elif v == confirmed:
            colors.append(COLORS["accent"])
        else:
            colors.append(COLORS["primary"])

    text_labels = [f"{fmt_원(v)}<br><span style='font-size:0.7em;color:#9ca3af'>{a}</span>"
                   for v, a in zip(values, annotations)]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=text_labels,
        textposition="outside",
        textfont=dict(color="#e5e7eb"),
    ))
    fig.update_layout(
        title="주당 평가가액 → 공모가 할인 과정",
        height=380, showlegend=False, **PLOTLY_LAYOUT,
    )
    return fig


def build_lockup_pie(lockup_data):
    first = lockup_data[0]
    listing_ratio = safe_num(first.get("ratio", 0))
    lockup_ratio = max(0, 1 - listing_ratio)

    fig = go.Figure(data=[go.Pie(
        labels=["상장일 유통", "보호예수"],
        values=[listing_ratio, lockup_ratio],
        marker_colors=[COLORS["accent"], COLORS["primary"]],
        textinfo="label+percent",
        hole=0.45,
        textfont=dict(color="#e5e7eb"),
    )])
    fig.update_layout(title="상장일 유통 비율", height=360, showlegend=False, **PLOTLY_LAYOUT)
    return fig


def build_lockup_timeline(lockup_data):
    periods = [item.get("period", "") for item in lockup_data]
    cum_ratios = [min(safe_num(item.get("cumulative_ratio", 0)) * 100, 100) for item in lockup_data]
    shares_list = [safe_num(item.get("shares", 0)) for item in lockup_data]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=periods, y=[s / 10000 for s in shares_list],
        name="유통 주식수", marker_color=COLORS["primary"], yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=cum_ratios, name="누적 비율",
        mode="lines+markers+text",
        text=[f"{r:.1f}%" for r in cum_ratios], textposition="top center",
        line=dict(color=COLORS["accent"], width=3),
        marker=dict(size=8), yaxis="y2",
        textfont=dict(color=COLORS["accent"]),
    ))
    layout = {**PLOTLY_LAYOUT}
    layout["yaxis"] = dict(title="만주", side="left", gridcolor=COLORS["grid"])
    layout["yaxis2"] = dict(title="%", side="right", overlaying="y", range=[0, 110], gridcolor=COLORS["grid"])
    fig.update_layout(
        title="유통가능주식 & 누적비율", height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#e5e7eb")),
        **layout,
    )
    return fig


def build_financial_mini_chart(financials):
    years = [str(f.get("year", "")) for f in financials]
    revenues = [safe_num(f.get("revenue", 0)) / 1e8 for f in financials]
    op_incomes = [safe_num(f.get("operating_income", 0)) / 1e8 for f in financials]
    net_incomes = [safe_num(f.get("net_income", 0)) / 1e8 for f in financials]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years, y=revenues, name="매출",
        marker_color=COLORS["primary"],
        textfont=dict(size=9),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=op_incomes, name="영업이익",
        mode="lines+markers+text",
        text=[f"{v:,.0f}" for v in op_incomes],
        textposition="top center",
        textfont=dict(color=COLORS["secondary"], size=9),
        line=dict(color=COLORS["secondary"], width=2),
        marker=dict(size=6),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=net_incomes, name="순이익",
        mode="lines+markers+text",
        text=[f"{v:,.0f}" for v in net_incomes],
        textposition="bottom center",
        textfont=dict(color=COLORS["tertiary"], size=9),
        line=dict(color=COLORS["tertiary"], width=2, dash="dot"),
        marker=dict(size=6),
    ))
    fig.update_layout(
        height=200,
        margin=dict(l=0, r=0, t=30, b=20),
        title=dict(text="재무 추이 (억원)", font=dict(size=11, color="#9ca3af")),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            font=dict(color="#9ca3af", size=9),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb", size=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False, gridcolor=COLORS["grid"]),
    )
    return fig


def build_product_pie(products):
    revenue_by_name: dict[str, float] = {}
    for p in products:
        if p.get("revenue_share"):
            name = p.get("name", "기타")
            revenue_by_name[name] = revenue_by_name.get(name, 0) + float(p["revenue_share"])
    if not revenue_by_name:
        return None
    fig = go.Figure(data=[go.Pie(
        labels=list(revenue_by_name.keys()),
        values=list(revenue_by_name.values()),
        hole=0.4, textinfo="label+percent",
        textfont=dict(color="#e5e7eb"),
    )])
    fig.update_layout(title="매출 구성", height=350, showlegend=False, **PLOTLY_LAYOUT)
    return fig


# ─────────────────────────────────────────────────────────
# 캘리브레이션 (판단 검증) 대시보드
# ─────────────────────────────────────────────────────────
def render_calibration_view():
    """캘리브레이션 대시보드: AI 판단 vs 실제 시장 결과 비교."""
    st.markdown("## IPO 판단 검증 대시보드")

    if not CALIBRATION_FILE.exists():
        st.warning(
            "캘리브레이션 데이터가 없습니다.\n\n"
            "`python -m analysis.calibration`을 먼저 실행하세요."
        )
        return

    ipos = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    if not ipos:
        st.info("데이터가 비어있습니다.")
        return

    from analysis.calibration import compute_calibration_stats
    stats = compute_calibration_stats(ipos)

    # ── KPI 카드 ──
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, label, val in [
        (k1, "전체 종목", f"{stats['total']}건"),
        (k2, "시초가 데이터", f"{stats['with_first_price']}건"),
        (k3, "평균 수익률", f"{stats['avg_first_day_return']}%" if stats["avg_first_day_return"] is not None else "-"),
        (k4, "밴드상단 비율", f"{stats['band_upper_pct']}%" if stats["band_upper_pct"] is not None else "-"),
        (k5, "양의수익률", f"{stats['positive_return_pct']}%" if stats["positive_return_pct"] is not None else "-"),
    ]:
        col.markdown(f"""
        <div class="metric-card">
            <div class="label">{label}</div>
            <div class="value">{val}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ── 전체 IPO 테이블 ──
    st.markdown('<div class="section-header">최근 IPO 전체 목록</div>', unsafe_allow_html=True)
    table_data = []
    for ipo in ipos:
        band_str = (
            f"{ipo['band_low']:,}~{ipo['band_high']:,}"
            if ipo.get("band_low") and ipo.get("band_high") else "-"
        )
        confirmed_str = f"{ipo['confirmed_price']:,}" if ipo.get("confirmed_price") else "-"
        band_pos_str = f"{ipo['band_position']}%" if ipo.get("band_position") is not None else "-"
        comp_str = f"{ipo['competition_ratio']:,.0f}:1" if ipo.get("competition_ratio") is not None else "-"
        commit_str = f"{ipo['commitment_pct']}%" if ipo.get("commitment_pct") is not None else "-"
        first_str = f"{ipo['first_price']:,}" if ipo.get("first_price") else "-"
        ret_str = f"{ipo['first_day_return']:+.1f}%" if ipo.get("first_day_return") is not None else "-"

        table_data.append({
            "종목": ipo.get("name", ""),
            "수요예측일": ipo.get("demand_date", ""),
            "밴드": band_str,
            "확정가": confirmed_str,
            "밴드위치": band_pos_str,
            "경쟁률": comp_str,
            "확약": commit_str,
            "AI판단": ipo.get("ai_verdict", "-"),
            "시초가": first_str,
            "수익률": ret_str,
        })
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # ── 차트: 경쟁률 vs 수익률, 밴드위치 vs 수익률 ──
    with_fp = [i for i in ipos if i.get("first_day_return") is not None]

    if with_fp:
        c1, c2 = st.columns(2)

        with c1:
            with_comp = [i for i in with_fp if i.get("competition_ratio") is not None]
            if with_comp:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[i["competition_ratio"] for i in with_comp],
                    y=[i["first_day_return"] for i in with_comp],
                    mode="markers+text",
                    text=[i["name"][:5] for i in with_comp],
                    textposition="top center",
                    textfont=dict(size=9, color="#e5e7eb"),
                    marker=dict(
                        size=10,
                        color=[i["first_day_return"] for i in with_comp],
                        colorscale="RdYlGn",
                        showscale=True,
                    ),
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="#666")
                fig.update_layout(
                    title="기관경쟁률 vs 시초가 수익률",
                    xaxis_title="기관경쟁률 (:1)",
                    yaxis_title="시초가 수익률 (%)",
                    height=400, **PLOTLY_LAYOUT,
                )
                st.plotly_chart(fig, key="cal_comp", use_container_width=True)

        with c2:
            with_band = [i for i in with_fp if i.get("band_position") is not None]
            if with_band:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[i["band_position"] for i in with_band],
                    y=[i["first_day_return"] for i in with_band],
                    mode="markers+text",
                    text=[i["name"][:5] for i in with_band],
                    textposition="top center",
                    textfont=dict(size=9, color="#e5e7eb"),
                    marker=dict(
                        size=10,
                        color=[i["first_day_return"] for i in with_band],
                        colorscale="RdYlGn",
                        showscale=True,
                    ),
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="#666")
                fig.update_layout(
                    title="밴드 위치 vs 시초가 수익률",
                    xaxis_title="밴드 위치 (%)",
                    yaxis_title="시초가 수익률 (%)",
                    height=400, **PLOTLY_LAYOUT,
                )
                st.plotly_chart(fig, key="cal_band", use_container_width=True)

    # ── AI 판단별 성과 ──
    by_verdict = stats.get("by_verdict", {})
    if by_verdict:
        st.markdown('<div class="section-header">AI 판단별 성과</div>', unsafe_allow_html=True)
        verdict_colors = {
            "BUY": COLORS["positive"],
            "CONDITIONAL": COLORS["accent"],
            "AVOID": COLORS["negative"],
        }
        vnames = []
        vreturns = []
        vcounts = []
        vcolors = []
        for v, d in by_verdict.items():
            if d.get("avg_return") is not None:
                vnames.append(v)
                vreturns.append(d["avg_return"])
                vcounts.append(d["count"])
                vcolors.append(verdict_colors.get(v, COLORS["neutral"]))

        if vnames:
            fig = go.Figure(go.Bar(
                x=vnames, y=vreturns,
                marker_color=vcolors,
                text=[f"{r:+.1f}%\n({c}건)" for r, c in zip(vreturns, vcounts)],
                textposition="outside",
                textfont=dict(color="#e5e7eb"),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#666")
            fig.update_layout(
                title="AI 판단별 평균 시초가 수익률",
                height=380, showlegend=False, **PLOTLY_LAYOUT,
            )
            st.plotly_chart(fig, key="cal_verdict", use_container_width=True)

    # ── 확약비율 vs 수익률 ──
    if with_fp:
        with_commit = [i for i in with_fp if i.get("commitment_pct") is not None]
        if with_commit:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[i["commitment_pct"] for i in with_commit],
                y=[i["first_day_return"] for i in with_commit],
                mode="markers+text",
                text=[i["name"][:5] for i in with_commit],
                textposition="top center",
                textfont=dict(size=9, color="#e5e7eb"),
                marker=dict(
                    size=10,
                    color=[i["first_day_return"] for i in with_commit],
                    colorscale="RdYlGn",
                    showscale=True,
                ),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#666")
            fig.update_layout(
                title="의무보유확약 vs 시초가 수익률",
                xaxis_title="의무보유확약 (%)",
                yaxis_title="시초가 수익률 (%)",
                height=400, **PLOTLY_LAYOUT,
            )
            st.plotly_chart(fig, key="cal_commit", use_container_width=True)


# ─────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### IPO Research")
    st.divider()

    dashboard_mode = st.radio(
        "모드", ["종목 분석", "판단 검증"],
        horizontal=True, label_visibility="collapsed",
    )

    selected = None
    data = None

    if dashboard_mode == "종목 분석":
        data_files = find_data_files()
        if not data_files:
            st.error("데이터 없음. `python main.py <종목명>`으로 분석을 먼저 실행하세요.")
            st.stop()

        selected = st.selectbox("종목 선택", list(data_files.keys()))
        data = load_data(str(data_files[selected]))

        # 선택된 종목 재분석
        if selected:
            st.divider()
            display = selected.split(" (")[0]
            if st.button(f"'{display}' 재분석", use_container_width=True):
                st.session_state["_run_analysis"] = display

        st.divider()
        st.markdown("##### 새 종목 분석")
        new_company = st.text_input("회사명", placeholder="예: 리브스메드")
        if st.button("분석 실행", type="primary", use_container_width=True):
            if new_company:
                st.session_state["_run_analysis"] = new_company

# ─────────────────────────────────────────────────────────
# 분석 실행 처리 (사이드바 밖에서 프로그레스 표시)
# ─────────────────────────────────────────────────────────
if st.session_state.get("_run_analysis"):
    _target = st.session_state.pop("_run_analysis")
    if run_analysis_with_progress(_target):
        import time
        time.sleep(1)
        st.rerun()

# ─────────────────────────────────────────────────────────
# 모드 라우팅
# ─────────────────────────────────────────────────────────
if dashboard_mode == "판단 검증":
    render_calibration_view()
    st.stop()

# ─────────────────────────────────────────────────────────
# 데이터 준비 (종목 분석 모드)
# ─────────────────────────────────────────────────────────
company_info = data.get("company_info", {})
offering = data.get("offering", {})
crawler = data.get("crawler_data", {})
financials = data.get("financials", [])
valuation = data.get("valuation", {})
lockup = data.get("lockup_schedule", [])
business = data.get("business", {})
peers = valuation.get("peers", [])

display_name = selected.split(" (")[0]
company_name = _clean_company_name(company_info.get("corp_name", display_name))

securities = offering.get("securities", [{}])
sec = securities[0] if securities else {}
confirmed_price = crawler.get("confirmed_price", "")
offering_price = sec.get("offering_price")

# AI 리포트 로드
md_files = sorted(REPORTS_DIR.glob(f"*_{display_name}_리서치.md"), reverse=True)
if not md_files:
    clean_name = _clean_company_name(company_info.get("corp_name", display_name))
    md_files = sorted(REPORTS_DIR.glob(f"*_{clean_name}_리서치.md"), reverse=True)
report_text = md_files[0].read_text(encoding="utf-8") if md_files else ""
verdict = _parse_verdict(report_text)

# 시그널 분류
signal = verdict.get("signal", "")
if "비추천" in signal or "불가" in signal:
    banner_cls = "verdict-negative"
    signal_display = f"AVOID — {signal}"
elif "조건부" in signal or "제한적" in signal or "신중" in signal:
    banner_cls = "verdict-neutral"
    signal_display = f"CONDITIONAL — {signal}"
elif signal:
    banner_cls = "verdict-positive"
    signal_display = f"BUY — {signal}"
else:
    banner_cls = "verdict-neutral"
    signal_display = "분석 완료"


# ═══════════════════════════════════════════════════════════
# 투자 판단 카드 (전체 너비)
# ═══════════════════════════════════════════════════════════
summary_text = verdict.get("summary", "")
price_opinion = verdict.get("price_opinion", "")
reasons_html = _render_reasons_html(verdict)

reasons_block = ""
if reasons_html:
    reasons_block = f'<div class="verdict-reasons">{reasons_html}</div>'

# AI 적정가 블록
fair_price = verdict.get("fair_price", "")
fair_price_vs = verdict.get("fair_price_vs", "")
fair_price_method = verdict.get("fair_price_method", "")
fair_price_steps = verdict.get("fair_price_steps", [])
participation = verdict.get("participation_strategy", "")
price_opinion = verdict.get("price_opinion", "")

price_block = ""
if fair_price:
    vs_html = f'<span class="fp-vs">({fair_price_vs})</span>' if fair_price_vs else ""
    inner = f'<div class="fp-label">AI 적정가</div>'
    inner += f'<div class="fp-headline"><span class="fp-value">{fair_price}</span> {vs_html}</div>'

    if fair_price_method:
        inner += f'<div class="fp-method">방법: {fair_price_method}</div>'

    if fair_price_steps:
        steps_html = ""
        for step in fair_price_steps[:4]:
            steps_html += (
                f'<div class="fp-step">'
                f'<span class="fp-step-label">{step["label"]}:</span> {step["value"]}</div>'
            )
        inner += f'<div class="fp-steps">{steps_html}</div>'

    if participation:
        inner += f'<div class="fp-strategy">{participation}</div>'

    price_block = f'<div class="fair-price-block">{inner}</div>'
elif price_opinion:
    price_block = (
        f'<div class="fair-price-block">'
        f'<div class="fp-label">적정가 의견</div>'
        f'<div class="fp-headline"><span class="fp-value" style="font-size:0.88rem;">{price_opinion}</span></div>'
        f'</div>'
    )

# 2-column hero: 왼쪽 = 판단 + 근거 + 적정가, 오른쪽 = 스냅샷 + 지표
hero_left, hero_right = st.columns([0.55, 0.45])

with hero_left:
    st.markdown(f"""
    <div class="verdict-card {banner_cls}">
        <h2>{company_name} | {signal_display}</h2>
        <p class="summary">{summary_text}</p>
        {reasons_block}
        {price_block}
    </div>
    """, unsafe_allow_html=True)

with hero_right:
    # 스냅샷 카드
    snapshot = verdict.get("snapshot", {})
    if snapshot:
        easy = snapshot.get("easy_summary", "")
        industry = snapshot.get("industry", "")
        edge = snapshot.get("competitive_edge", "")
        rev_model = snapshot.get("revenue_model", "")
        risk_one = snapshot.get("risk_oneliner", "")

        snap_rows = ""
        if industry:
            snap_rows += f'<div class="snap-row"><span class="snap-label">업종</span><span class="snap-value">{industry}</span></div>'
        if edge:
            snap_rows += f'<div class="snap-row"><span class="snap-label">경쟁력</span><span class="snap-edge">{edge}</span></div>'
        if rev_model:
            snap_rows += f'<div class="snap-row"><span class="snap-label">수익구조</span><span class="snap-value">{rev_model}</span></div>'
        if risk_one:
            snap_rows += f'<div class="snap-row"><span class="snap-label">리스크</span><span class="snap-risk">{risk_one}</span></div>'

        st.markdown(f"""
        <div class="snapshot-card">
            <div class="snap-title">Company Snapshot</div>
            <div class="snap-easy">{easy}</div>
            {snap_rows}
        </div>
        """, unsafe_allow_html=True)

    # 산업 해설 (비전문가용)
    industry_explainer = snapshot.get("industry_explainer", "") if snapshot else ""
    if industry_explainer:
        st.markdown(f"""
        <div style="background:#12151a; border:1px solid #1e2028; border-radius:8px; padding:0.7rem 0.9rem; margin-bottom:0.5rem;">
            <div style="color:#6b7280; font-size:0.65rem; font-weight:600; text-transform:uppercase; margin-bottom:0.3rem;">이 산업을 쉽게 말하면</div>
            <div style="color:#9ca3af; font-size:0.78rem; line-height:1.55;">{industry_explainer}</div>
        </div>
        """, unsafe_allow_html=True)

    # 공모 개요 카드 + 일정
    price_display = (
        f"{confirmed_price}"
        if confirmed_price and confirmed_price != "-"
        else (fmt_원(offering_price) if offering_price else "-")
    )
    price_label = "확정공모가" if confirmed_price and confirmed_price != "-" else "공모가"
    competition = crawler.get("institutional_competition", "-") or "-"
    commitment = crawler.get("lockup_commitment", "-") or "-"
    per_val = f"{valuation['applied_multiple']}배" if valuation.get("applied_multiple") else "-"
    listing_ratio_str = fmt_pct(lockup[0].get("ratio")) if lockup else "-"
    amount_str = fmt_억(sec.get("total_amount")) if sec.get("total_amount") else "-"

    underwriter = crawler.get("lead_underwriter", "-") or "-"
    demand_date = crawler.get("demand_forecast_date", "-") or "-"
    sub_date = offering.get("subscription_date", "") or crawler.get("subscription_date", "-") or "-"
    listing_date = crawler.get("listing_date", "-") or "-"

    # 2x3 카드 그리드
    metrics = [
        (price_label, price_display),
        ("공모금액", amount_str),
        ("기관경쟁률", competition),
        ("의무보유확약", commitment),
        ("적용 배수", per_val),
        ("상장일 유통", listing_ratio_str),
    ]
    for row_start in range(0, 6, 2):
        m1, m2 = st.columns(2)
        for col, (label, value) in zip([m1, m2], metrics[row_start:row_start + 2]):
            col.markdown(f"""
            <div class="metric-card">
                <div class="label">{label}</div>
                <div class="value">{value}</div>
            </div>
            """, unsafe_allow_html=True)

    # 일정 정보 (compact)
    schedule_items = []
    if underwriter and underwriter != "-":
        schedule_items.append(f"<b>주관사</b> {underwriter}")
    if demand_date and demand_date != "-":
        schedule_items.append(f"<b>수요예측</b> {demand_date}")
    if sub_date and sub_date != "-":
        schedule_items.append(f"<b>청약</b> {sub_date}")
    if listing_date and listing_date != "-":
        schedule_items.append(f"<b>상장</b> {listing_date}")
    if schedule_items:
        schedule_html = " &middot; ".join(schedule_items)
        st.markdown(f'<div style="color:#6b7280; font-size:0.72rem; padding:0.3rem 0.2rem; line-height:1.6;">{schedule_html}</div>', unsafe_allow_html=True)

    # 핵심 체크포인트
    checkpoints = verdict.get("checkpoints", [])
    if checkpoints:
        st.markdown('<div class="section-header">핵심 체크포인트</div>', unsafe_allow_html=True)
        for cp in checkpoints[:3]:
            desc = cp['description']
            st.markdown(f"""
            <div class="checkpoint-compact">
                <div class="cp-title">{cp['title']}</div>
                <div class="cp-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 상세 분석 탭 (전체 너비)
# ═══════════════════════════════════════════════════════════
tab_fin, tab_peer, tab_val, tab_supply, tab_biz, tab_report = st.tabs(
    ["재무", "Peer 비교", "밸류에이션", "수급", "사업분석", "AI 리포트"]
)

# ── 재무 탭 ──
with tab_fin:
    if not financials:
        st.info("재무제표 데이터가 없습니다.")
    else:
        years = [str(f.get("year", "")) for f in financials]
        revenues = [f.get("revenue") for f in financials]
        op_incomes = [f.get("operating_income") for f in financials]
        net_incomes = [f.get("net_income") for f in financials]

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(build_revenue_chart(years, revenues), key="rev", width="stretch")
        with c2:
            st.plotly_chart(build_profit_chart(years, op_incomes, net_incomes), key="profit", width="stretch")

        table_rows = []
        for f in financials:
            table_rows.append({
                "연도": f.get("year", ""),
                "매출액": fmt_억(f.get("revenue")),
                "영업이익": fmt_억(f.get("operating_income")),
                "순이익": fmt_억(f.get("net_income")),
                "자산": fmt_억(f.get("total_assets")),
                "부채": fmt_억(f.get("total_liabilities")),
                "자본": fmt_억(f.get("total_equity")),
                "매출YoY": fmt_pct(f.get("revenue_yoy")) if f.get("revenue_yoy") is not None else "-",
            })
        st.dataframe(table_rows, width="stretch", hide_index=True)

        source = financials[0].get("source", "DART API") if financials else ""
        if source == "증권신고서":
            st.caption("* 출처: 증권신고서 (DART API 미제공)")

# ── Peer 비교 탭 ──
with tab_peer:
    if not peers:
        st.info("비교회사(Peer) 데이터가 없습니다.")
    else:
        target_per = valuation.get("applied_multiple")
        avg_per = valuation.get("average_peer_per") or target_per

        # Peer 비교 맥락 안내
        latest_fin_peer = financials[-1] if financials else {}
        my_rev = safe_num(latest_fin_peer.get("revenue", 0))
        if my_rev > 0:
            peer_revs = [safe_num(p.get("revenue", 0)) for p in peers if safe_num(p.get("revenue", 0)) > 0]
            if peer_revs:
                avg_peer_rev = sum(peer_revs) / len(peer_revs)
                ratio = avg_peer_rev / my_rev if my_rev > 0 else 0
                my_rev_str = f"{my_rev / 1e8:,.0f}억"
                avg_peer_str = f"{avg_peer_rev / 1e8:,.0f}억" if avg_peer_rev < 1e12 else f"{avg_peer_rev / 1e12:,.1f}조"

                if ratio > 10:
                    ctx_msg = (
                        f"{company_name}의 매출은 {my_rev_str}이지만 비교회사 평균 매출은 {avg_peer_str}으로 "
                        f"약 {ratio:,.0f}배 차이가 납니다. "
                        f"매출 규모가 크게 다른 회사와 비교하면 밸류에이션이 과대평가될 수 있으니 주의가 필요합니다."
                    )
                    st.markdown(f"""
                    <div class="peer-context">
                        <div class="ctx-title">비교회사 매출 규모 차이 주의</div>
                        <div class="ctx-desc">{ctx_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif ratio > 3:
                    ctx_msg = (
                        f"{company_name} 매출 {my_rev_str} vs 비교회사 평균 {avg_peer_str} "
                        f"(약 {ratio:,.0f}배 차이). 비교는 참고용으로만 활용하세요."
                    )
                    st.markdown(f"""
                    <div class="peer-context">
                        <div class="ctx-title">비교회사와의 규모 차이</div>
                        <div class="ctx-desc">{ctx_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # PER 비교
        st.plotly_chart(
            build_peer_per_chart(company_name, target_per, peers, avg_per),
            key="peer_per", width="stretch",
        )

        # 매출 + 마진 비교
        pc1, pc2 = st.columns(2)
        latest_fin = financials[-1] if financials else {}
        with pc1:
            st.plotly_chart(
                build_peer_revenue_chart(company_name, latest_fin.get("revenue", 0), peers),
                key="peer_rev", width="stretch",
            )
        with pc2:
            st.plotly_chart(
                build_peer_margin_chart(company_name, financials, peers),
                key="peer_margin", width="stretch",
            )

        # 종합 비교 테이블
        st.markdown('<div class="section-header">Peer Group 종합 비교</div>', unsafe_allow_html=True)
        peer_table = []
        # 공모기업 행
        peer_table.append({
            "회사": f"{company_name} (공모기업)",
            "시장": company_info.get("corp_cls", "-"),
            "매출액": fmt_억(latest_fin.get("revenue")),
            "영업이익": fmt_억(latest_fin.get("operating_income")),
            "영업이익률": fmt_margin(latest_fin.get("revenue"), latest_fin.get("operating_income")),
            "시가총액": "-",
            "PER": f"{target_per}x" if target_per else "-",
        })
        for p in peers:
            peer_table.append({
                "회사": p.get("name", ""),
                "시장": p.get("market", ""),
                "매출액": fmt_조(p.get("revenue")),
                "영업이익": fmt_조(p.get("operating_income")),
                "영업이익률": fmt_margin(p.get("revenue"), p.get("operating_income")),
                "시가총액": fmt_조(p.get("market_cap")),
                "PER": f"{p['per']:.1f}x" if p.get("per") else "-",
            })
        st.dataframe(peer_table, width="stretch", hide_index=True)

# ── 밸류에이션 탭 ──
with tab_val:
    if not valuation:
        st.info("밸류에이션 데이터가 없습니다.")
    else:
        st.markdown('<div class="section-header">공모가 산출 과정</div>', unsafe_allow_html=True)

        per_share = safe_num(valuation.get("per_share_value"))
        pr = valuation.get("offering_price_range", {})
        band_low = safe_num(pr.get("low")) if isinstance(pr, dict) else 0
        band_high = safe_num(pr.get("high")) if isinstance(pr, dict) else 0
        discount_rate = safe_num(valuation.get("discount_rate"))
        base_value = safe_num(valuation.get("base_value"))
        multiple = valuation.get("applied_multiple")

        # 할인율 역산: 주당평가가액 → 밴드 상한/하한
        disc_high = round((1 - band_high / per_share) * 100, 1) if per_share > 0 and band_high > 0 else None
        disc_low = round((1 - band_low / per_share) * 100, 1) if per_share > 0 and band_low > 0 else None

        # 확정공모가 할인율
        cp_val = 0
        if confirmed_price and confirmed_price != "-":
            try:
                cp_val = int(str(confirmed_price).replace(",", ""))
            except (ValueError, TypeError):
                pass
        disc_confirmed = round((1 - cp_val / per_share) * 100, 1) if per_share > 0 and cp_val > 0 else None

        # 현재가치 할인 적용 후 기준이익
        discounted_value = round(base_value * (1 - discount_rate)) if base_value > 0 and discount_rate > 0 else None

        rows = []
        # 1. 방법론
        rows.append(("① 밸류에이션 방법", f"<b>{valuation.get('valuation_method', '-')}</b>", valuation.get("base_metric", "")))
        # 2. 기준 이익
        rows.append(("② 추정 이익", f"<b>{fmt_억(base_value)}</b>", "증권신고서 추정치"))
        # 3. 현재가치 할인
        if discount_rate > 0:
            rows.append((
                "③ 현재가치 할인",
                f"× (1 − {fmt_pct(discount_rate)}) = <b>{fmt_억(discounted_value)}</b>" if discounted_value else f"할인율 {fmt_pct(discount_rate)}",
                "미래이익 → 현재가치 환산",
            ))
        # 4. 배수 적용
        if multiple:
            rows.append(("④ Peer 배수 적용", f"× <b>{multiple}배</b>", f"Peer 평균 PER (비교회사 {len(valuation.get('peers', []))}개사)"))
        # 5. 주당 평가가액
        rows.append(("⑤ 주당 평가가액", f"<b>{fmt_원(per_share)}</b>", ""))

        # 6. 공모가 밴드 (핵심: 할인율 차이로 상한/하한 도출)
        if band_high > 0 and disc_high is not None and disc_low is not None:
            rows.append(("⑥ 공모가 밴드 상한", f"{fmt_원(per_share)} × (1 − {disc_high}%) = <b>{fmt_원(band_high)}</b>", f"평가가액 대비 {disc_high}% 할인"))
            rows.append(("⑦ 공모가 밴드 하한", f"{fmt_원(per_share)} × (1 − {disc_low}%) = <b>{fmt_원(band_low)}</b>", f"평가가액 대비 {disc_low}% 할인"))

        # 7. 확정공모가
        if cp_val > 0 and disc_confirmed is not None:
            rows.append(("⑧ 확정 공모가", f"<b>{fmt_원(cp_val)}</b>", f"평가가액 대비 {disc_confirmed}% 할인"))

        # 렌더링
        html = '<table class="val-flow-table"><thead><tr><th style="width:22%">단계</th><th>산출</th><th style="width:30%">비고</th></tr></thead><tbody>'
        for i, (step, value, note) in enumerate(rows):
            cls = ""
            if step.startswith("⑤"):
                cls = ' class="vf-highlight"'
            elif step.startswith("⑥") or step.startswith("⑦") or step.startswith("⑧"):
                cls = ' class="vf-result"'
            html += f'<tr{cls}><td class="vf-step">{step}</td><td class="vf-value">{value}</td><td class="vf-note">{note}</td></tr>'
        html += '</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)

        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

# ── 수급 탭 ──
with tab_supply:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-header">일정</div>', unsafe_allow_html=True)
        schedule = {
            "수요예측일": crawler.get("demand_forecast_date", "-"),
            "청약일": offering.get("subscription_date", "") or crawler.get("subscription_date", "-"),
            "납입일": offering.get("payment_date", "-"),
            "상장예정일": crawler.get("listing_date", "-"),
            "주관사": crawler.get("lead_underwriter", "-"),
        }
        for k, v in schedule.items():
            if v and v != "-":
                st.markdown(f"**{k}**: {v}")

    with col_r:
        st.markdown('<div class="section-header">수요예측 결과</div>', unsafe_allow_html=True)
        demand = {
            "기관경쟁률": competition,
            "의무보유확약": commitment,
            "기관배정": str(crawler.get("institutional_allocation", "-")).replace("\xa0", " ").replace("~", " ~ "),
            "일반배정": str(crawler.get("retail_allocation", "-")).replace("\xa0", " ").replace("~", " ~ "),
        }
        for k, v in demand.items():
            if v and v != "-":
                st.markdown(f"**{k}**: {v}")

    if lockup:
        st.markdown('<div class="section-header">유통가능주식수</div>', unsafe_allow_html=True)
        lc1, lc2 = st.columns(2)

        with lc1:
            st.plotly_chart(build_lockup_pie(lockup), key="lockup_pie", width="stretch")
        with lc2:
            st.plotly_chart(build_lockup_timeline(lockup), key="lockup_tl", width="stretch")

        lockup_table = []
        for item in lockup:
            lockup_table.append({
                "기간": item.get("period", ""),
                "주식수": f"{int(safe_num(item.get('shares', 0))):,}주",
                "비율": fmt_pct(item.get("ratio")),
                "누적비율": fmt_pct(item.get("cumulative_ratio")),
            })
        st.dataframe(lockup_table, width="stretch", hide_index=True)

# ── 사업분석 탭 ──
with tab_biz:
    if not business:
        st.info("사업 분석 데이터가 없습니다.")
    else:
        # 비전문가 한줄 요약 + 수익 구조 (스냅샷에서)
        snapshot = verdict.get("snapshot", {})
        if snapshot.get("easy_summary") or snapshot.get("revenue_model"):
            biz_top1, biz_top2 = st.columns(2)
            with biz_top1:
                if snapshot.get("easy_summary"):
                    st.markdown(f"""
                    <div class="revenue-flow">
                        <div class="flow-title">사업 개요</div>
                        <div class="flow-desc">{snapshot['easy_summary']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                if snapshot.get("competitive_edge"):
                    st.markdown(f"""
                    <div class="revenue-flow">
                        <div class="flow-title">핵심 경쟁력</div>
                        <div class="flow-desc" style="color: #4ade80;">{snapshot['competitive_edge']}</div>
                    </div>
                    """, unsafe_allow_html=True)
            with biz_top2:
                if snapshot.get("revenue_model"):
                    st.markdown(f"""
                    <div class="revenue-flow">
                        <div class="flow-title">수익 모델</div>
                        <div class="flow-desc">{snapshot['revenue_model']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                if snapshot.get("risk_oneliner"):
                    st.markdown(f"""
                    <div class="revenue-flow">
                        <div class="flow-title">핵심 리스크</div>
                        <div class="flow-desc" style="color: #f87171;">{snapshot['risk_oneliner']}</div>
                    </div>
                    """, unsafe_allow_html=True)

        bc1, bc2 = st.columns(2)
        with bc1:
            st.markdown('<div class="section-header">회사 개요</div>', unsafe_allow_html=True)
            st.write(business.get("company_overview", ""))
            st.markdown('<div class="section-header">핵심 사업</div>', unsafe_allow_html=True)
            st.write(business.get("main_business", ""))
        with bc2:
            st.markdown('<div class="section-header">핵심 기술</div>', unsafe_allow_html=True)
            st.write(business.get("key_technology", "-"))
            st.markdown('<div class="section-header">시장 규모</div>', unsafe_allow_html=True)
            st.write(business.get("market_size", "-"))

        products = business.get("products", [])
        if products:
            st.markdown('<div class="section-header">주요 제품</div>', unsafe_allow_html=True)
            fig_prod = build_product_pie(products)
            if fig_prod:
                st.plotly_chart(fig_prod, key="products", width="stretch")

# ── AI 리포트 탭 ──
with tab_report:
    if report_text:
        st.markdown(report_text)
    else:
        st.info("AI 분석 리포트가 없습니다.")
