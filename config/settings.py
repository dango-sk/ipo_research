import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# API Keys
DART_API_KEY = os.getenv("DART_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

# DART API
DART_BASE_URL = "https://opendart.fss.or.kr/api"

# 데이터 경로
DATA_DIR = BASE_DIR / "data"
CORP_CODES_DIR = DATA_DIR / "corp_codes"
FILINGS_DIR = DATA_DIR / "filings"
REPORTS_DIR = DATA_DIR / "reports"

# LLM 설정
LLM_MODEL = "claude-sonnet-4-20250514"
