"""AI 종합 분석 엔진

수집된 모든 데이터를 바탕으로 다각도 IPO 분석 리포트를 생성한다.
단순 숫자 비교가 아니라, 사업성·밸류에이션·수급·리스크를
맥락적으로 분석한다.
"""

import json

import anthropic

from config.settings import ANTHROPIC_API_KEY, LLM_MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ANALYST_SYSTEM_PROMPT = """너는 기관투자자의 IPO 리서치 애널리스트다.
증권신고서와 수집된 데이터를 바탕으로 공모주 투자 판단에 필요한 분석을 수행한다.

분석 원칙:
1. 회사가 제시한 스토리를 그대로 받아들이지 않고, 비판적으로 검증한다
2. 비교회사(Peer) 선정의 적정성을 반드시 따진다 (매출 규모, 성장 단계 비교)
3. 미래 실적 추정의 공격성을 과거 실적 추세와 비교한다
4. 유통물량과 기존 투자자 구성으로 수급 리스크를 판단한다
5. 기술특례/이익미실현 상장의 경우 추가 리스크를 명시한다
6. 최종적으로 "참여 여부와 참여 수준"에 대한 구체적 의견을 제시한다

출력 형식: 마크다운
언어: 한국어"""


def _format_data_for_prompt(data: dict) -> str:
    """수집된 데이터를 프롬프트에 넣을 수 있는 형태로 정리."""
    sections = []

    # 기업 개황
    if "company_info" in data:
        ci = data["company_info"]
        sections.append(f"""## 기업 개황
- 회사명: {ci.get('corp_name', '')}
- 대표: {ci.get('ceo_nm', '')}
- 설립일: {ci.get('est_dt', '')}
- 업종: {ci.get('induty_code', '')}
- 주소: {ci.get('adres', '')}
- 시장: {ci.get('corp_cls', '')}""")

    # 공모사항
    if "offering" in data:
        sections.append(f"## 공모사항\n```json\n{json.dumps(data['offering'], ensure_ascii=False, indent=2, default=str)}\n```")

    # 38.co.kr 데이터 (기관경쟁률, 확약 등)
    if "crawler_data" in data and data["crawler_data"]:
        sections.append(f"## 수요예측 결과 (38.co.kr)\n```json\n{json.dumps(data['crawler_data'], ensure_ascii=False, indent=2, default=str)}\n```")

    # 재무제표
    if "financials" in data:
        sections.append(f"## 재무제표\n```json\n{json.dumps(data['financials'], ensure_ascii=False, indent=2, default=str)}\n```")

    # 유통가능주식수
    if "lockup_schedule" in data:
        sections.append(f"## 유통가능주식수 (보호예수)\n```json\n{json.dumps(data['lockup_schedule'], ensure_ascii=False, indent=2, default=str)}\n```")

    # 사업내용
    if "business" in data:
        sections.append(f"## 사업내용\n```json\n{json.dumps(data['business'], ensure_ascii=False, indent=2, default=str)}\n```")

    # Valuation
    if "valuation" in data:
        sections.append(f"## 밸류에이션 (Peer 비교)\n```json\n{json.dumps(data['valuation'], ensure_ascii=False, indent=2, default=str)}\n```")

    return "\n\n".join(sections)


def generate_analysis(data: dict, company_name: str) -> str:
    """수집된 모든 데이터를 기반으로 종합 분석 리포트를 생성한다.

    Args:
        data: 파이프라인에서 수집·파싱한 전체 데이터
        company_name: 분석 대상 회사명

    Returns:
        마크다운 형식의 종합 분석 리포트
    """
    formatted = _format_data_for_prompt(data)

    user_prompt = f"""아래는 '{company_name}'의 IPO 관련 수집 데이터입니다.
이 데이터를 바탕으로 종합 분석 리포트를 작성해주세요.

{formatted}

---

다음 구조로 작성해주세요:

# {company_name} IPO 리서치 리포트

## 1. 공모 개요
- 공모사항 요약 (공모가, 시가총액, 공모비율, 주관사 등)
- 주요 일정

## 2. 사업 분석
- 핵심 사업 내용과 시장 내 위치
- 제품/서비스의 경쟁력과 차별화 요소
- 시장 규모와 성장성
- 경쟁 현황과 진입 장벽

## 3. 재무 분석
- 매출 성장 추세 (YoY)
- 수익성 (영업이익률, 순이익률)
- 재무 건전성 (부채비율 등)
- 현금흐름 상태

## 4. 밸류에이션 검토
- 회사가 선정한 비교회사(Peer)의 적정성 평가
  (매출 규모 차이, 사업 유사성, 성장 단계 비교)
- 적용 PER/배수의 합리성
- 공모가 할인율 평가
- 상장 후 적정 시가총액 추정

## 5. 수급 분석
- 상장일 유통가능물량 비율 평가
- 기간별 락업 해제 스케줄과 오버행 리스크
- 기관 수요예측 결과 해석 (경쟁률, 확약비율)
- 기존 투자자(VC/PE) Exit 가능성

## 6. 리스크 요인
- 특례상장 관련 리스크
- 사업/시장 고유 리스크
- 실적 추정의 공격성
- 기타 주의사항

## 7. 종합 의견
- 투자 판단 요약 (긍정/부정 요소 정리)
- 참여 전략 제안 (참여 여부, 공모가 대비 적정가, 규모)

## ⚠️ 핵심 체크포인트
- 반드시 추가로 확인해야 할 사항 3~5개 (구체적으로)
"""

    print("[AI 분석] 종합 리포트 생성 중...")
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=8192,
        system=ANALYST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    report = resp.content[0].text
    print(f"[AI 분석] 리포트 생성 완료 ({len(report):,}자)")
    return report
