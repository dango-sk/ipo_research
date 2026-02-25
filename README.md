# IPO Research Tool

한국 IPO(공모주) 리서치를 자동화하는 도구입니다. DART API, 38.co.kr 크롤링, 증권신고서 LLM 파싱을 통해 데이터를 수집하고, AI 분석 리포트를 생성합니다.

![Dashboard Screenshot](docs/dashboard.png)

## Features

- **DART API 연동** - 기업개황, 증권신고서, 지분증권(공모사항), 재무제표 자동 수집
- **38.co.kr 크롤링** - 수요예측 결과, 기관경쟁률, 의무보유확약, 청약일정
- **증권신고서 LLM 파싱** - Claude API로 비정형 HTML에서 구조화된 데이터 추출
  - 유통가능주식수 / 보호예수 스케줄
  - Peer Group 밸류에이션 (비교회사 PER, 매출, 순이익)
  - 사업 내용 요약
  - 재무제표 (미상장 기업 fallback)
- **AI 종합 분석** - 7개 섹션 리서치 리포트 자동 생성
  - 공모개요, 사업분석, 재무분석, 밸류에이션 검토, 수급분석, 리스크 요인, 종합 의견
- **대시보드** - Streamlit + Plotly 인터랙티브 시각화
- **엑셀 출력** - 기관 리서치 포맷의 엑셀 시트

## Quick Start

### 1. 설치

```bash
git clone https://github.com/<your-username>/ipo-research.git
cd ipo-research
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp .env.example .env
# .env 파일에 API 키 입력
```

필요한 API 키:
| 키 | 용도 | 발급 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API (LLM 파싱 & 분석) | [Anthropic Console](https://console.anthropic.com/) |
| `DART_API_KEY` | DART 공시 데이터 | [OpenDART](https://opendart.fss.or.kr/) |

### 3. 실행

```bash
# 전체 파이프라인 (데이터 수집 → LLM 파싱 → AI 분석 → 리포트)
python main.py 리브스메드

# 증권신고서 파싱 건너뛰기 (빠른 실행)
python main.py 리브스메드 --skip-filing

# AI 분석 건너뛰기
python main.py 리브스메드 --skip-analysis
```

### 4. 대시보드

```bash
streamlit run dashboard.py
```

## Architecture

```
ipo_research/
├── main.py                 # CLI 진입점 & 파이프라인 오케스트레이션
├── dashboard.py            # Streamlit 대시보드
│
├── collectors/             # 데이터 수집
│   ├── dart_api.py         #   DART OpenAPI (기업코드, 공시, 재무제표, 원본문서)
│   └── crawler_38.py       #   38.co.kr 크롤러 (수요예측, 경쟁률, 확약)
│
├── parsers/                # 데이터 파싱
│   ├── llm_parser.py       #   Claude API 기반 비정형 데이터 추출
│   ├── financial.py        #   재무제표 정규화 & YoY 성장률
│   └── offering.py         #   공모사항 파싱 & 데이터 통합
│
├── analysis/               # AI 분석
│   └── analyst.py          #   Claude API 기반 종합 리서치 리포트
│
├── output/                 # 출력
│   ├── excel_writer.py     #   openpyxl 엑셀 리포트
│   └── report_writer.py    #   마크다운 리포트
│
└── config/
    └── settings.py         # API 키, 경로, LLM 모델 설정
```

## Pipeline

```
[Step 1] 기업 식별 (DART 기업코드 검색)
    ↓
[Step 2] DART API 정형 데이터 (기업개황, 공모사항, 재무제표)
    ↓
[Step 3] 38.co.kr 크롤링 (수요예측, 경쟁률, 확약비율)
    ↓
[Step 4] 증권신고서 LLM 파싱 (유통물량, Peer 밸류에이션, 사업내용, 재무)
    ↓
[Step 5] AI 종합 분석 (7개 섹션 리서치 리포트)
    ↓
[Step 6] 출력 (마크다운 + 엑셀 + JSON)
```

## Output

실행 결과물은 `data/reports/`에 저장됩니다:

| 파일 | 내용 |
|---|---|
| `YYYYMMDD_종목명_리서치.md` | AI 분석 리포트 (마크다운) |
| `YYYYMMDD_종목명_리서치.xlsx` | 엑셀 리서치 시트 |
| `YYYYMMDD_종목명_data.json` | 수집된 원본 데이터 |

## Tech Stack

- **Python 3.12+**
- **Claude API** (claude-sonnet-4-20250514) - LLM 파싱 & 분석
- **DART OpenAPI** - 한국 금융감독원 공시 데이터
- **Streamlit + Plotly** - 대시보드
- **openpyxl** - 엑셀 생성
- **BeautifulSoup** - HTML 파싱
- **requests** - HTTP 클라이언트

## License

MIT
