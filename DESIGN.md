# IPO Research Tool — 설계 문서

## 1. 목표

**수작업 2시간 → 15분**: IPO 공모주 리서치 시트를 자동 생성하고,
투자 판단에 필요한 다각도 사전 분석을 AI가 제공한다.

### 레퍼런스
- `주식운용1팀(인턴)_남수경_주식리서치.xlsx` — 리브스메드 시트
- 섹션: 일정 / 공모사항 / 유통가능주식수 / 사업내용 / Financials / Valuation / 종합의견

---

## 2. 전체 아키텍처

```
[종목명 입력]
     │
     ├─ (1) DART API ──────────→ 공시검색 → 증권신고서 식별
     │      ├─ estkRs API ─────→ 공모개요, 공모가, 주관사, 자금용도
     │      ├─ fnlttSinglAcnt ─→ 재무제표 (매출, 영업이익, 순이익 등)
     │      └─ document.xml ───→ 증권신고서 원본 ZIP (HTML)
     │
     ├─ (2) 38.co.kr 크롤링 ───→ 기관경쟁률, 의무보유확약, 청약일정
     │
     ├─ (3) 증권신고서 HTML ───→ LLM 파싱
     │      ├─ 유통가능주식수 (의무보유기간별)
     │      ├─ 사업내용 요약
     │      ├─ Peer Valuation (비교회사 PER 등)
     │      └─ 공모가 산출 근거
     │
     └─ (4) AI 분석 엔진 ─────→ 종합 리서치 리포트
            ├─ 사업 분석 (시장성, 경쟁, 제품 파이프라인)
            ├─ 밸류에이션 검토 (Peer 적정성, 할인율)
            ├─ 수급 분석 (유통물량, 오버행 리스크)
            ├─ 실적 추정 검증 (회사 프로젝션 vs 현실)
            └─ 투자 체크리스트 (핵심 검토 포인트)
```

---

## 3. 데이터 소스 상세

### 3.1 DART OpenAPI (정형 데이터)

| API | 엔드포인트 | 얻을 수 있는 것 |
|-----|-----------|----------------|
| 공시검색 | `/api/list.json` | 증권신고서 접수번호(rcept_no), 회사코드 |
| 기업개황 | `/api/company.json` | 설립일, 대표, 주소, 업종코드 |
| 지분증권 | `/api/estkRs.json` | 청약일, 납입일, 공모가, 공모총액, 주관사, 자금용도 |
| 재무제표 | `/api/fnlttSinglAcnt.json` | 자산/부채/매출/영업이익/순이익 (최근 3년) |
| 원본문서 | `/api/document.xml` | 증권신고서 전체 HTML (ZIP) |
| 고유번호 | `/api/corpCode.xml` | 전체 기업 코드 마스터 |

**API 키**: 무료, 일 10,000건 제한
**보유 키**: `DART_API_KEY` (alpha_radar/.env)

### 3.2 38.co.kr 크롤링 (수요예측 결과)

| 데이터 | 페이지 | 방법 |
|--------|--------|------|
| 기관경쟁률 | `/html/fund/?o=r1` (수요예측결과) | requests + BeautifulSoup |
| 의무보유확약 비율 | 상동 | 상동 |
| 확정공모가 | `/html/fund/?o=k` (청약일정) | 상동 |
| 상장일 | 상동 | 상동 |

### 3.3 증권신고서 HTML → LLM 파싱 (비정형 데이터)

DART `document.xml`로 받은 증권신고서 ZIP 내부 HTML에서 추출:

| 데이터 | 증권신고서 내 위치 | 파싱 난이도 |
|--------|-------------------|------------|
| 유통가능주식수 테이블 | "보호예수 및 유통제한에 관한 사항" | 높음 (포맷 상이) |
| 사업내용 요약 | "사업의 내용" | 중간 |
| 매출 구성 (제품별) | "사업의 내용" 내 매출 테이블 | 높음 |
| Peer 비교회사 목록 | "공모가격 산정" | 높음 |
| 공모가 산출 로직 | "공모가격 산정" | 높음 |

→ HTML 청크를 잘라서 LLM(Claude API)에 "이 표에서 X 데이터를 JSON으로 추출" 요청

### 3.4 추가 데이터 소스 (보유 키 활용)

| 소스 | 키 | 용도 |
|------|-----|------|
| Naver API | `NAVER_CLIENT_ID` / `SECRET` | 뉴스 검색 (해당 기업 관련 기사) |
| FnSpace API | `FNSPACE_API_KEY` | 재무 데이터 교차 검증 |

---

## 4. 프로젝트 구조

```
ipo_research/
├── .env                      # API 키 (DART, Anthropic, Naver, FnSpace)
├── requirements.txt
├── config/
│   └── settings.py           # 설정값 (API URL, 스코어링 기준 등)
│
├── data/
│   ├── corp_codes/            # DART 기업코드 마스터 캐시
│   ├── filings/               # 다운로드된 증권신고서 ZIP/HTML
│   └── reports/               # 생성된 리서치 리포트
│
├── collectors/                # 데이터 수집 모듈
│   ├── __init__.py
│   ├── dart_api.py            # DART OpenAPI 호출
│   ├── dart_document.py       # 증권신고서 원본 다운로드 & HTML 추출
│   └── crawler_38.py          # 38.co.kr 크롤링
│
├── parsers/                   # 데이터 파싱 모듈
│   ├── __init__.py
│   ├── financial.py           # 재무제표 정리 (단위 통일 등)
│   ├── offering.py            # 공모사항 정리
│   └── llm_parser.py          # LLM 기반 비정형 데이터 파싱
│                               #  - 유통가능주식수 추출
│                               #  - Peer Valuation 추출
│                               #  - 사업내용 요약
│                               #  - 공모가 산출 근거 추출
│
├── analysis/                  # AI 분석 모듈
│   ├── __init__.py
│   └── analyst.py             # 종합 분석 리포트 생성
│                               #  - 사업 다각도 분석
│                               #  - Peer 적정성 검토
│                               #  - 수급/오버행 분석
│                               #  - 실적 추정 검증
│                               #  - 투자 체크리스트
│
├── output/                    # 출력 모듈
│   ├── __init__.py
│   ├── excel_writer.py        # 리서치 시트 엑셀 생성
│   └── report_writer.py       # 마크다운/PDF 리포트 생성
│
└── main.py                    # CLI 진입점
```

---

## 5. 핵심 데이터 모델

```python
@dataclass
class IPOResearch:
    """하나의 IPO 종목에 대한 전체 리서치 데이터"""

    # 기본 정보
    company_name: str           # 회사명
    corp_code: str              # DART 고유번호
    market: str                 # 코스피/코스닥/코넥스
    listing_type: str           # 일반/기술특례/이익미실현 등

    # 일정
    schedule: IPOSchedule       # 수요예측일, 청약일, 납입일, 상장예정일

    # 공모사항
    offering: OfferingDetail    # 공모주식수, 상장주식수, 공모가 밴드,
                                # 신주/구주, 시가총액, 배정비율

    # 주관사
    underwriters: list[Underwriter]  # 주관사명, 인수수량, 인수금액

    # 유통가능주식수
    lockup_schedule: list[LockupEntry]  # 기간별 유통물량, 비율, 누적비율

    # 수요예측 결과
    demand: DemandResult        # 기관경쟁률, 의무보유확약비율, 확정공모가

    # 사업 내용
    business: BusinessSummary   # 설립일, 대표, 직원수, 주요제품, 매출구성

    # 재무제표
    financials: list[FinancialYear]  # 연도별 자산/부채/매출/영업이익/순이익

    # 밸류에이션
    valuation: ValuationDetail  # 추정이익, 할인율, 적용PER,
                                # Peer 목록 (회사별 PER/매출/이익)

    # AI 분석
    analysis: AnalysisReport    # 사업분석, Peer검토, 수급분석, 체크리스트
```

---

## 6. 파이프라인 흐름

```
main.py "리브스메드"
│
├─ Step 1: 기업 식별
│  └─ corp_codes에서 검색 → corp_code 획득
│     (없으면 DART corpCode.xml 다운로드 후 캐시)
│
├─ Step 2: DART 정형 데이터 수집 (병렬)
│  ├─ dart_api.search_filings(corp_code, type="C001")
│  │   → rcept_no 획득
│  ├─ dart_api.get_equity_registration(corp_code)
│  │   → 공모개요, 공모가, 주관사
│  ├─ dart_api.get_company_info(corp_code)
│  │   → 기업개황
│  └─ dart_api.get_financials(corp_code, years=[2022,2023,2024])
│      → 재무제표
│
├─ Step 3: 38.co.kr 크롤링
│  └─ crawler_38.get_demand_result("리브스메드")
│      → 기관경쟁률, 의무보유확약, 확정공모가
│
├─ Step 4: 증권신고서 원본 다운로드 & LLM 파싱 (병렬)
│  ├─ dart_document.download(rcept_no) → HTML 파일들
│  ├─ llm_parser.extract_lockup(html)
│  │   → 유통가능주식수 테이블
│  ├─ llm_parser.extract_business(html)
│  │   → 사업내용, 매출구성
│  └─ llm_parser.extract_valuation(html)
│      → Peer 비교회사, 공모가 산출 근거
│
├─ Step 5: AI 종합 분석
│  └─ analyst.analyze(ipo_research)
│      → 사업 다각도 분석
│      → Peer 적정성 검토
│      → 수급/오버행 분석
│      → 실적 추정 검증
│      → 핵심 검토 포인트
│
└─ Step 6: 출력
   ├─ excel_writer.generate(ipo_research)
   │   → 리브스메드 엑셀 포맷과 동일한 시트
   └─ report_writer.generate(ipo_research)
       → 마크다운 리서치 리포트
```

---

## 7. AI 분석 엔진 설계 (핵심)

단순 숫자 비교가 아니라, 다각도 정성 분석을 수행한다.

### 7.1 분석 프롬프트 구조

```
[System]
너는 기관투자자 IPO 리서치 애널리스트다.
증권신고서와 수집된 데이터를 바탕으로 투자 판단에 필요한 분석을 수행한다.

[Input - 수집된 데이터 전체]
- 공모사항, 재무제표, 유통물량, Peer Valuation, 사업내용...

[분석 항목]

1. 사업 분석
   - 이 회사가 속한 시장의 규모와 성장성
   - 주요 제품/서비스의 경쟁력과 차별화 요소
   - 경쟁사 대비 포지셔닝
   - 향후 성장 동력 (신제품, 해외진출 등)

2. 밸류에이션 검토
   - 회사가 선정한 Peer Group이 적정한가?
     (매출 규모, 사업 유사성, 시장 지배력 비교)
   - 적용 PER의 합리성
   - 공모가 할인율이 충분한가?
   - 상장 후 적정 시가총액 추정

3. 실적 추정 검증
   - 회사가 제시한 미래 실적 추정이 현실적인가?
   - 과거 매출 성장률 대비 추정치의 괴리
   - 흑자전환 시점의 합리성
   - 핵심 가정 (시장점유율, ASP, 신규 사업 기여도)

4. 수급 분석
   - 상장일 유통가능물량 비율
   - 기간별 락업 해제 스케줄과 오버행 리스크
   - 기존 투자자(VC/PE) 구성과 Exit 가능성
   - 기관 수요예측 결과 해석

5. 리스크 요인
   - 기술특례/이익미실현 상장 여부
   - 업종 고유 리스크
   - 규제/정책 리스크
   - 핵심 인력 의존도

6. 투자 체크리스트
   - ⚠️ 반드시 확인해야 할 포인트 3~5개
   - 예: "27년 순이익 710억 추정의 근거가 무엇인지 증권신고서 p.XX 확인"
```

### 7.2 출력 예시

```markdown
# 리브스메드 (KOSDAQ) — IPO 리서치 리포트

## 사업 분석
- 최소침습수술 기구 → 수술로봇으로 확장하는 전략
- 주력 제품 ArtiSential 매출 YoY +57%, 수출 비중 86%
- 글로벌 수술로봇 시장은 Intuitive Surgical이 지배적이나,
  handheld 카테고리는 아직 경쟁이 제한적
- 리스크: 로봇(Stark) 출시가 25-26년으로 아직 매출 기여 전

## 밸류에이션 검토
- Peer: Medtronic(매출 30조), Stryker(20조), Intuitive(15조)
  → 리브스메드 매출 270억과 100배 이상 괴리. 업종 유사성은 있으나
    성장 단계가 완전히 다른 기업들을 비교 대상으로 삼아 공격적
- 적용 PER 45.5배 → 공모가 PER 26.5~33배 (할인 27~42%)
- 기술특례 기준으로 PER 26.5배는 적정 범위이나,
  추정 이익 자체의 공격성이 문제

## 수급 분석
- 상장일 유통: 32% (양호)
- 3개월 후 유통: 57.4% (급증) ← 시리즈 투자자 물량
- 12개월 후: 60.6%
- ⚠️ 상장 3개월 시점 오버행 리스크 높음

## ⚠️ 핵심 검토 포인트
1. 27년 순이익 710억 추정 — 현재 적자인데 근거는?
2. 수술로봇 Stark 출시 일정과 FDA 승인 진행 현황
3. 미국 시장 handheld 매출 확대의 구체적 채널/파트너
4. 시리즈 투자자(상장 3개월 후 유통) Exit 가능성
```

---

## 8. 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| HTTP | `httpx` (비동기 지원) |
| 크롤링 | `requests` + `beautifulsoup4` |
| HTML 파싱 | `lxml` |
| LLM | `anthropic` SDK (Claude API) |
| 엑셀 | `openpyxl` |
| 환경변수 | `python-dotenv` |
| CLI | `typer` 또는 `argparse` |

---

## 9. 개발 순서 (우선순위)

### Phase 1: 데이터 수집 파이프라인
1. DART API 연동 (corp_code 조회, 공시검색, 지분증권 API)
2. DART 재무제표 API 연동
3. 증권신고서 원본 다운로드

### Phase 2: 비정형 데이터 파싱
4. 증권신고서 HTML에서 섹션 분리
5. LLM 파싱 (유통물량, Peer Valuation, 사업내용)
6. 38.co.kr 크롤러

### Phase 3: 분석 & 출력
7. AI 종합 분석 엔진
8. 엑셀 리서치 시트 생성
9. 마크다운 리포트 생성

### Phase 4: 고도화 (선택)
10. Streamlit 대시보드
11. 과거 IPO DB 축적 → 통계 분석
12. 상장일 수익률 예측 모델
