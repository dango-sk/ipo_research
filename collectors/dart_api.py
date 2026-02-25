"""DART OpenAPI 연동 모듈

기업코드 조회, 공시검색, 증권신고서(지분증권), 재무제표 등
정형 데이터를 가져온다.
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx

from config.settings import CORP_CODES_DIR, DART_API_KEY, DART_BASE_URL


# ---------------------------------------------------------------------------
# 기업 코드 마스터
# ---------------------------------------------------------------------------

_corp_code_cache: dict[str, dict] | None = None


def _load_corp_codes() -> dict[str, dict]:
    """DART 전체 기업코드를 로드한다. 캐시 파일이 없으면 다운로드."""
    global _corp_code_cache
    if _corp_code_cache is not None:
        return _corp_code_cache

    cache_file = CORP_CODES_DIR / "corp_codes.xml"
    if not cache_file.exists():
        print("[DART] 기업코드 마스터 다운로드 중...")
        _download_corp_codes(cache_file)

    tree = ET.parse(cache_file)
    root = tree.getroot()

    codes: dict[str, dict] = {}
    for item in root.iter("list"):
        name = (item.findtext("corp_name") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if name:
            codes[name] = {
                "corp_code": corp_code,
                "stock_code": stock_code,
                "corp_name": name,
            }

    _corp_code_cache = codes
    print(f"[DART] 기업코드 {len(codes):,}개 로드 완료")
    return codes


def _download_corp_codes(dest: Path) -> None:
    """DART에서 기업코드 ZIP을 받아서 XML로 저장."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(
        f"{DART_BASE_URL}/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_name = zf.namelist()[0]
        dest.write_bytes(zf.read(xml_name))
    print(f"[DART] 기업코드 저장: {dest}")


def search_corp_code(company_name: str) -> dict | None:
    """회사명으로 DART 기업코드를 검색한다.

    정확히 일치하는 것을 먼저 찾고, 없으면 포함하는 것을 찾는다.
    """
    codes = _load_corp_codes()

    # 정확히 일치
    if company_name in codes:
        return codes[company_name]

    # 부분 일치
    matches = [v for k, v in codes.items() if company_name in k]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"[DART] '{company_name}' 검색 결과 {len(matches)}개:")
        for m in matches[:10]:
            print(f"  - {m['corp_name']} ({m['corp_code']})")
        return matches[0]

    return None


# ---------------------------------------------------------------------------
# 공시 검색
# ---------------------------------------------------------------------------


def search_filings(
    corp_code: str,
    pblntf_detail_ty: str = "C001",  # 증권신고서(지분증권)
    bgn_de: str = "20150101",
    end_de: str = "20261231",
    last_reprt_at: str = "Y",
) -> list[dict]:
    """DART 공시검색 — 증권신고서 등 특정 유형 공시를 검색한다."""
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_ty": "C",
        "pblntf_detail_ty": pblntf_detail_ty,
        "last_reprt_at": last_reprt_at,
        "page_count": "100",
    }
    resp = httpx.get(f"{DART_BASE_URL}/list.json", params=params, timeout=15)
    data = resp.json()

    if data.get("status") != "000":
        print(f"[DART] 공시검색 실패: {data.get('message')}")
        return []

    filings = data.get("list", [])
    print(f"[DART] 공시 {len(filings)}건 발견")
    return filings


# ---------------------------------------------------------------------------
# 기업 개황
# ---------------------------------------------------------------------------


def get_company_info(corp_code: str) -> dict | None:
    """DART 기업개황 API."""
    resp = httpx.get(
        f"{DART_BASE_URL}/company.json",
        params={"crtfc_key": DART_API_KEY, "corp_code": corp_code},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "000":
        print(f"[DART] 기업개황 실패: {data.get('message')}")
        return None
    return data


# ---------------------------------------------------------------------------
# 증권신고서 — 지분증권 (IPO 핵심 데이터)
# ---------------------------------------------------------------------------


def get_equity_registration(
    corp_code: str,
    bgn_de: str = "20150101",
    end_de: str = "20261231",
) -> dict | None:
    """증권신고서(지분증권) 주요정보 — 공모개요, 공모가, 주관사, 자금용도."""
    resp = httpx.get(
        f"{DART_BASE_URL}/estkRs.json",
        params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "000":
        print(f"[DART] 지분증권 API 실패: {data.get('message')}")
        return None

    result = {
        "general": [],      # 일반사항
        "securities": [],   # 증권의종류 (공모가 정보)
        "underwriters": [], # 인수인 (주관사)
        "fund_usage": [],   # 자금의사용목적
        "sellers": [],      # 매출인에관한사항
    }

    for group in data.get("group", []):
        title = group.get("title", "")
        items = group.get("list", [])
        if "일반사항" in title:
            result["general"] = items
        elif "증권의종류" in title:
            result["securities"] = items
        elif "인수인" in title:
            result["underwriters"] = items
        elif "자금" in title:
            result["fund_usage"] = items
        elif "매출인" in title:
            result["sellers"] = items

    print(f"[DART] 지분증권 데이터 수신 완료")
    return result


# ---------------------------------------------------------------------------
# 재무제표
# ---------------------------------------------------------------------------


def get_financials(
    corp_code: str,
    bsns_year: str,
    reprt_code: str = "11011",  # 사업보고서 (연간)
) -> list[dict]:
    """단일회사 주요계정 재무제표."""
    resp = httpx.get(
        f"{DART_BASE_URL}/fnlttSinglAcnt.json",
        params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "000":
        # 미상장 기업은 사업보고서가 없을 수 있음
        return []
    return data.get("list", [])


def get_financials_multi_year(
    corp_code: str,
    years: list[str] | None = None,
) -> dict[str, list[dict]]:
    """여러 연도의 재무제표를 한번에 가져온다."""
    if years is None:
        years = ["2022", "2023", "2024"]

    result = {}
    for year in years:
        items = get_financials(corp_code, year)
        if items:
            result[year] = items
            print(f"[DART] {year}년 재무제표 {len(items)}개 항목")
        else:
            # 반기/분기 시도
            for code, label in [("11012", "반기"), ("11014", "3분기"), ("11013", "1분기")]:
                items = get_financials(corp_code, year, code)
                if items:
                    result[year] = items
                    print(f"[DART] {year}년 {label} 재무제표 {len(items)}개 항목")
                    break
    return result


# ---------------------------------------------------------------------------
# 증권신고서 원본 문서 다운로드
# ---------------------------------------------------------------------------


def download_document(rcept_no: str, save_dir: Path | None = None) -> Path | None:
    """증권신고서 원본 ZIP을 다운로드하고 압축을 풀어 반환한다."""
    from config.settings import FILINGS_DIR

    if save_dir is None:
        save_dir = FILINGS_DIR / rcept_no
    save_dir.mkdir(parents=True, exist_ok=True)

    # 이미 다운로드된 경우
    html_files = list(save_dir.glob("*.html")) + list(save_dir.glob("*.xml"))
    if html_files:
        print(f"[DART] 이미 다운로드됨: {save_dir}")
        return save_dir

    resp = httpx.get(
        f"{DART_BASE_URL}/document.xml",
        params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no},
        timeout=60,
    )

    if resp.status_code != 200 or len(resp.content) < 1000:
        print(f"[DART] 문서 다운로드 실패: {rcept_no}")
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(save_dir)
        print(f"[DART] 문서 저장: {save_dir} ({len(list(save_dir.iterdir()))}개 파일)")
        return save_dir
    except zipfile.BadZipFile:
        print(f"[DART] ZIP 파일 아님: {rcept_no}")
        return None
