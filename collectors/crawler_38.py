"""38.co.kr 크롤러

수요예측 결과, 기관경쟁률, 의무보유확약, 청약일정 등
DART API에서 제공하지 않는 데이터를 가져온다.
"""

import re
import ssl
import time
import warnings

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# 38.co.kr SSL 인증서 경고 숨김
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

BASE_URL = "https://www.38.co.kr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class _LegacySSLAdapter(HTTPAdapter):
    """38.co.kr처럼 오래된 SSL을 사용하는 사이트 대응."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _get_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", _LegacySSLAdapter())
    session.headers.update(HEADERS)
    return session


def _get_soup(url: str) -> BeautifulSoup:
    session = _get_session()
    resp = session.get(url, timeout=15, verify=False)
    resp.encoding = "euc-kr"
    return BeautifulSoup(resp.text, "html.parser")


def _clean_number(text: str) -> str:
    """콤마, 공백 제거."""
    return re.sub(r"[,\s]", "", text.strip())


# ---------------------------------------------------------------------------
# 수요예측 결과 목록 (기관경쟁률, 확약비율 포함)
# ---------------------------------------------------------------------------


def get_demand_forecast_list(pages: int = 3) -> list[dict]:
    """수요예측결과 페이지에서 종목 목록을 가져온다.

    테이블 구조 (실제 확인됨):
    td[0]: 종목명 (a 태그에 ?o=v&no=XXX 링크)
    td[1]: 수요예측일
    td[2]: 공모가 밴드
    td[3]: 확정공모가
    td[4]: 상장초가
    td[5]: 기관경쟁률
    td[6]: 의무보유확약(%)
    td[7]: 주관사
    """
    results = []
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/html/fund/index.htm?o=r1&page={page}"
        soup = _get_soup(url)

        # 종목 상세 링크가 있는 행만 필터
        for a_tag in soup.find_all("a", href=re.compile(r"\?o=v&no=\d+")):
            tr = a_tag.find_parent("tr")
            if not tr:
                continue
            cols = tr.find_all("td")
            if len(cols) < 6:
                continue

            href = a_tag.get("href", "")
            no_match = re.search(r"no=(\d+)", href)
            name = a_tag.get_text(strip=True)
            if not name:
                continue

            results.append({
                "name": name,
                "no": no_match.group(1) if no_match else "",
                "demand_date": cols[1].get_text(strip=True) if len(cols) > 1 else "",
                "offering_price_range": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                "confirmed_price": cols[3].get_text(strip=True) if len(cols) > 3 else "",
                "first_price": cols[4].get_text(strip=True) if len(cols) > 4 else "",
                "competition_rate": cols[5].get_text(strip=True) if len(cols) > 5 else "",
                "commitment_rate": cols[6].get_text(strip=True) if len(cols) > 6 else "",
                "underwriter": cols[7].get_text(strip=True) if len(cols) > 7 else "",
            })

        time.sleep(0.5)

    # 중복 제거 (같은 no)
    seen = set()
    unique = []
    for item in results:
        if item["no"] and item["no"] not in seen:
            seen.add(item["no"])
            unique.append(item)
    results = unique

    print(f"[38.co.kr] 수요예측 목록 {len(results)}건 수집")
    return results


# ---------------------------------------------------------------------------
# 수요예측 일정 목록 (수요예측 전/진행 중 종목)
# ---------------------------------------------------------------------------


def get_demand_schedule_list(pages: int = 2) -> list[dict]:
    """수요예측일정 페이지에서 종목 목록을 가져온다.

    수요예측 결과가 아직 없는 종목(예정/진행 중)이 여기에 표시된다.

    테이블 구조:
    td[0]: 종목명 (a 태그에 ?o=v&no=XXX 링크)
    td[1]: 수요예측일
    td[2]: 희망공모가(원)
    td[3]: 확정공모가
    td[4]: 공모금액(백만)
    td[5]: 주간사
    """
    results = []
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/html/fund/index.htm?o=r&page={page}"
        soup = _get_soup(url)

        for a_tag in soup.find_all("a", href=re.compile(r"\?o=v&no=\d+")):
            tr = a_tag.find_parent("tr")
            if not tr:
                continue
            cols = tr.find_all("td")
            if len(cols) < 5:
                continue

            href = a_tag.get("href", "")
            no_match = re.search(r"no=(\d+)", href)
            name = a_tag.get_text(strip=True)
            if not name:
                continue

            results.append({
                "name": name,
                "no": no_match.group(1) if no_match else "",
                "demand_date": cols[1].get_text(strip=True) if len(cols) > 1 else "",
                "offering_price_range": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                "confirmed_price": cols[3].get_text(strip=True) if len(cols) > 3 else "",
                "offering_amount_million": cols[4].get_text(strip=True) if len(cols) > 4 else "",
                "underwriter": cols[5].get_text(strip=True) if len(cols) > 5 else "",
            })

        time.sleep(0.5)

    # 중복 제거
    seen = set()
    unique = []
    for item in results:
        if item["no"] and item["no"] not in seen:
            seen.add(item["no"])
            unique.append(item)
    results = unique

    print(f"[38.co.kr] 수요예측 일정 {len(results)}건 수집")
    return results


# ---------------------------------------------------------------------------
# 종목 상세 페이지
# ---------------------------------------------------------------------------


def get_ipo_detail(no: str) -> dict:
    """38.co.kr 종목 상세페이지에서 데이터를 파싱한다."""
    url = f"{BASE_URL}/html/fund/?o=v&no={no}"
    soup = _get_soup(url)

    detail: dict = {"url": url}

    # 정보 테이블만 필터 (2~4칸 key-value 구조, 네비게이션/사이드바 제외)
    all_rows: list[tuple[str, str]] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        # 네비게이션/메뉴 테이블 제외: 셀이 너무 많거나 텍스트가 지나치게 긴 행
        valid_rows = 0
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            if 2 <= len(cells) <= 6:
                valid_rows += 1
        if valid_rows < 2:
            continue

        for tr in rows:
            cells = tr.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if not (2 <= len(texts) <= 6):
                continue
            # key-value 쌍 추출 (2칸씩)
            for i in range(0, len(texts) - 1, 2):
                key = texts[i]
                val = texts[i + 1] if i + 1 < len(texts) else ""
                # key가 너무 길면 정보 테이블이 아님
                if key and len(key) <= 20 and len(val) <= 200:
                    all_rows.append((key, val))

    # 주요 필드 매핑 (정확도를 위해 key 길이를 제한하여 네비게이션 텍스트 제외)
    field_map = {
        "확정공모가": "confirmed_price",
        "공모가": "offering_price_range",
        "공모주식수": "offering_shares",
        "상장예정주식수": "total_shares",
        "기관경쟁률": "institutional_competition",
        "의무보유확약": "lockup_commitment",
        "의무보유확약비율": "lockup_commitment",
        "수요예측일": "demand_forecast_date",
        "청약일": "subscription_date",
        "환불일": "refund_date",
        "상장일": "listing_date",
        "상장예정일": "listing_date",
        "주간사": "lead_underwriter",
        "주관사": "lead_underwriter",
        "대표주관": "lead_underwriter",
    }

    for key, val in all_rows:
        for pattern, field in field_map.items():
            if pattern in key and val:
                detail[field] = val
                break

    # 배정비율 파싱 (기관/일반/우리사주)
    for key, val in all_rows:
        if "기관" in key and "%" in val and len(val) <= 100:
            detail["institutional_allocation"] = val
        elif "일반" in key and "%" in val and len(val) <= 100:
            detail["retail_allocation"] = val
        elif "우리사주" in key and "%" in val and len(val) <= 100:
            detail["employee_allocation"] = val

    print(f"[38.co.kr] 상세 데이터 {len(detail)}개 필드 수집")
    return detail


# ---------------------------------------------------------------------------
# 종목명으로 검색
# ---------------------------------------------------------------------------


def _match_name(company_name: str, item_name: str) -> bool:
    """종목명 매칭 (부분 일치)."""
    return company_name in item_name or item_name in company_name


def _enrich_from_detail(result: dict, no: str) -> None:
    """상세 페이지에서 추가 정보를 가져와 result에 병합한다."""
    if not no:
        return
    try:
        detail = get_ipo_detail(no)
        for key in ["subscription_date", "listing_date",
                     "institutional_allocation", "retail_allocation",
                     "employee_allocation", "offering_shares", "total_shares"]:
            if key in detail and detail[key]:
                result[key] = detail[key]
    except Exception as e:
        print(f"  상세 페이지 파싱 실패 (무시): {e}")


def search_by_name(company_name: str, pages: int = 5) -> dict | None:
    """종목명으로 38.co.kr에서 검색하여 데이터를 반환한다.

    1) 수요예측 결과 페이지(o=r1)에서 검색 — 경쟁률, 확약비율 등 포함
    2) 없으면 수요예측 일정 페이지(o=r)에서 검색 — 예정/진행 중 종목
    두 경우 모두 상세 페이지에서 추가 정보를 보완한다.
    """
    # --- 1) 수요예측 결과 페이지 (경쟁률, 확약비율 있음) ---
    listings = get_demand_forecast_list(pages=pages)

    for item in listings:
        if _match_name(company_name, item["name"]):
            print(f"[38.co.kr] '{company_name}' 발견 (수요예측 결과) → no={item['no']}")

            result = {
                "source": "수요예측결과",
                "institutional_competition": item.get("competition_rate", ""),
                "lockup_commitment": item.get("commitment_rate", ""),
                "confirmed_price": item.get("confirmed_price", ""),
                "offering_price_range": item.get("offering_price_range", ""),
                "demand_forecast_date": item.get("demand_date", ""),
                "lead_underwriter": item.get("underwriter", ""),
                "first_price": item.get("first_price", ""),
                "list_info": item,
            }

            _enrich_from_detail(result, item.get("no", ""))
            return result

    # --- 2) 수요예측 일정 페이지 (예정/진행 중 종목) ---
    schedule = get_demand_schedule_list(pages=2)

    for item in schedule:
        if _match_name(company_name, item["name"]):
            print(f"[38.co.kr] '{company_name}' 발견 (수요예측 일정) → no={item['no']}")

            result = {
                "source": "수요예측일정",
                "institutional_competition": "",   # 아직 결과 없음
                "lockup_commitment": "",
                "confirmed_price": item.get("confirmed_price", ""),
                "offering_price_range": item.get("offering_price_range", ""),
                "demand_forecast_date": item.get("demand_date", ""),
                "lead_underwriter": item.get("underwriter", ""),
                "offering_amount_million": item.get("offering_amount_million", ""),
                "first_price": "",
                "list_info": item,
            }

            _enrich_from_detail(result, item.get("no", ""))
            return result

    print(f"[38.co.kr] '{company_name}' 찾지 못함")
    return None
