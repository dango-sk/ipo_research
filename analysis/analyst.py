
"""AI 종합 분석 엔진

수집된 모든 데이터를 바탕으로 다각도 IPO 분석 리포트를 생성한다.
단순 숫자 비교가 아니라, 사업성·밸류에이션·수급·리스크를
맥락적으로 분석한다.
"""

import json

import anthropic

from config.settings import ANTHROPIC_API_KEY

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
7. 펀더멘털 분석과 시장 수요 시그널을 균형있게 반영한다. 펀더멘털이 부족해도 시장 수요가 강하면 단기 참여 기회가 될 수 있고, 반대도 가능하다
8. **캘리브레이션 결과를 반드시 반영한다.** 프롬프트에 포함된 과거 블라인드 테스트 결과는 너의 판단 편향을 보정하기 위한 것이다. 유사 종목의 실제 시장 결과를 무시하지 마라

밸류에이션 방법론 가이드 (AI 적정가 산출 시 반드시 참고):
- 증권신고서에 회사가 제시한 밸류에이션 방법론(PER, PSR, EV/EBITDA 등)을 기본 프레임으로 따르되, 가정을 보수적으로 조정하라
- 즉 "방법론은 회사 것을 따르되, 가정은 비판적으로 재검토"하는 것이 원칙
- 비판적으로 조정해야 할 가정들:
  · Peer 선정: 매출 규모·성장 단계가 유사한가? 유리하게 고른 것은 아닌가?
  · 미래 실적 추정: 과거 추세 대비 지나치게 공격적인가? 일회성 매출을 반복 매출로 가정하지 않았는가?
  · 적용 배수: Peer 평균 대비 높거나 낮은 근거가 있는가?
  · 할인율: IPO 할인율이 충분한가? 추가 할인 요소(적자, 기술 불확실성 등)를 반영했는가?
- 일회성 매출(라이선스, 기술이전 등)은 반드시 구분하고, 지속가능 매출과 분리 평가하라
- 최종 적정가에는 반드시 "어떤 시점의 어떤 매출/이익을 기준으로 삼았는지" 명시하라

조정 시 근거의 구체성 요구:
- 추정실적을 조정할 때 "보수적으로 하향"이라는 이유만으로 임의의 숫자를 사용하지 마라. 반드시 과거 실적 CAGR, 업종 평균 성장률, 수주잔고 등 검증 가능한 근거를 사용하라
- 적용 배수를 변경할 때는 대안 Peer 기업명과 해당 기업의 실제 배수를 인용하라. "바이오 섹터 평균 PER 15배" 같은 출처 불명의 수치를 사용하지 마라
- 추가 할인율을 적용할 때는 할인 사유와 할인율의 근거를 명시하라 (예: "기술특례 상장 기업의 통상 IPO 할인율 20~30%")
- 조정 항목이 여러 개면 각각의 효과가 중첩됨을 인식하라. 추정실적 하향 × 배수 하향 × 추가 할인이 복리로 작용하면 적정가가 비현실적으로 낮아질 수 있다. 최종 산출가가 상식적으로 타당한지 sanity check를 수행하라

시장 수요 시그널 해석 가이드:
- 기관경쟁률 500:1 이상 = 수요 강함, 1000:1 이상 = 매우 강함
- 의무보유확약 15%+ = 기관 확신 높음, 25%+ = 매우 높음
- 확정공모가 밴드 상단(100%) = 시장이 밸류에이션을 지지
- 밴드 상단 확정 + 경쟁률 500:1+ 조합 = 상장일 양의 수익률 가능성 높음
- 펀더멘털 대비 고평가라도 시장 수요가 강한 IPO는 단기 수익 가능성을 별도 언급할 것

출력 형식: 마크다운
언어: 한국어"""


def _get_calibration_context(company_data: dict | None = None) -> str:
    """캘리브레이션 결과를 판단 보정 프레임워크로 생성한다.

    단순 통계 나열이 아니라, AI의 과거 편향을 진단하고
    유사 종목 실적을 보여줘서 판단을 실질적으로 교정한다.
    """
    try:
        from analysis.calibration import load_history, compute_calibration_stats
        history = load_history()
        if not history or len(history) < 5:
            return ""

        stats = compute_calibration_stats(history)
        by_verdict = stats.get("by_verdict", {})
        avoid = by_verdict.get("AVOID", {})

        lines = []
        lines.append("## ⚠️ AI 판단 보정 — 캘리브레이션 결과 (반드시 반영할 것)")
        lines.append("")
        lines.append("### 과거 블라인드 테스트 성과")
        lines.append(f"최근 1년 IPO {stats['total']}건에 대해 동일한 프롬프트로 블라인드 판단한 결과:")
        lines.append("")

        # 판단별 실제 성과
        if avoid:
            avoid_positive = avoid.get("positive_pct", 0)
            avoid_avg = avoid.get("avg_return", 0)
            lines.append(f"- **AVOID 판단 {avoid['count']}건 → 실제 양의 수익률 {avoid_positive}%, 평균 수익률 +{avoid_avg}%**")
            lines.append(f"  → 즉, AVOID라고 판단한 종목의 {avoid_positive}%가 실제로 돈을 벌었다")
        for v in ["CONDITIONAL", "BUY"]:
            vd = by_verdict.get(v, {})
            if vd and vd.get("count", 0) > 0:
                lines.append(f"- {v} 판단 {vd['count']}건: 평균 수익률 +{vd.get('avg_return', 'N/A')}%")

        lines.append(f"- 시장 전체: 평균 시초가 수익률 +{stats.get('avg_first_day_return', 'N/A')}%, "
                     f"양의 수익률 비율 {stats.get('positive_return_pct', 'N/A')}%")
        lines.append("")

        # 편향 진단
        lines.append("### 편향 진단")
        lines.append("위 결과는 너의 판단이 **체계적으로 과도하게 보수적**임을 보여준다.")
        lines.append("특히 밸류에이션 산출 시 추정실적 대폭 삭감 + 배수 하향 + 추가 할인을 중첩 적용하여")
        lines.append("적정가가 공모가의 20~40% 수준으로 산출되는 패턴이 반복되었다.")
        lines.append("그러나 실제로는 이 종목들의 93%가 공모가 대비 양의 수익을 냈다.")
        lines.append("")
        lines.append("### 교정 지침")
        lines.append("1. **밸류에이션**: 증권신고서 방법론의 가정을 조정할 때, 1~2개 핵심 항목만 조정하라. 모든 가정을 동시에 하향하면 비현실적 결과가 나온다")
        lines.append("2. **판단 기준**: AVOID는 '참여하면 손실 가능성이 높은' 종목에만 사용하라. 고평가 의견이 있어도 시장 수요가 강하면 CONDITIONAL로 판단하라")
        lines.append("3. **시장 수요 존중**: 기관경쟁률 500:1+, 확약 15%+ 조합은 시장이 밸류에이션을 수용한다는 의미다. 이 경우 펀더멘털 약점이 있어도 단기 참여 관점을 제시하라")

        # 유사 종목 매칭 (시초가 있는 종목만)
        with_return = [h for h in history
                       if h.get("first_day_return") is not None
                       and h.get("ai_verdict") == "AVOID"]
        if with_return and company_data:
            # 업종 키워드 매칭 시도
            industry = (company_data.get("company_info", {}).get("induty_code", "")
                        + " " + company_data.get("company_info", {}).get("corp_name", ""))
            bio_keywords = ["바이오", "제약", "의약", "항체", "임상", "치료"]
            tech_keywords = ["반도체", "전자", "소프트", "AI", "로봇", "플랫폼"]
            is_bio = any(kw in industry for kw in bio_keywords)
            is_tech = any(kw in industry for kw in tech_keywords)

            # 유사 종목 필터: 같은 업종 또는 전체에서 최근 5건
            similar = []
            for h in with_return:
                name = h.get("name", "")
                reasons = " ".join(h.get("ai_key_reasons", []))
                text = name + " " + reasons
                if is_bio and any(kw in text for kw in bio_keywords):
                    similar.append(h)
                elif is_tech and any(kw in text for kw in tech_keywords):
                    similar.append(h)

            # 유사 업종이 부족하면 최근 종목으로 보충
            if len(similar) < 3:
                for h in with_return:
                    if h not in similar:
                        similar.append(h)
                    if len(similar) >= 5:
                        break

            if similar:
                lines.append("")
                lines.append("### 유사 과거 종목 실적 (AI가 AVOID 판단했으나 실제 수익 발생)")
                lines.append("| 종목 | AI 적정가 | 확정공모가 | 시초가 수익률 | AI 리스크 요약 |")
                lines.append("|------|-----------|-----------|-------------|---------------|")
                for h in similar[:5]:
                    fair_low = h.get("ai_fair_price_low", "?")
                    fair_high = h.get("ai_fair_price_high", "?")
                    fair_str = f"{fair_low:,}~{fair_high:,}" if isinstance(fair_low, (int, float)) and isinstance(fair_high, (int, float)) else "N/A"
                    confirmed = h.get("confirmed_price", "?")
                    confirmed_str = f"{confirmed:,}" if isinstance(confirmed, (int, float)) else "N/A"
                    ret = h.get("first_day_return", "?")
                    risk = h.get("ai_risk_note", "")[:40]
                    lines.append(f"| {h.get('name', '')} | {fair_str} | {confirmed_str} | +{ret}% | {risk} |")
                lines.append("")
                lines.append("위 종목들은 모두 너와 동일한 분석 프레임워크에서 AVOID 판단을 받았지만,")
                lines.append("실제 시장에서는 공모가 대비 큰 폭의 양의 수익률을 기록했다.")
                lines.append("이번 분석에서도 같은 패턴이 반복되고 있지 않은지 점검하라.")

        return "\n".join(lines)
    except Exception:
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
    calibration_ctx = _get_calibration_context(company_data=data)

    user_prompt = f"""아래는 '{company_name}'의 IPO 관련 수집 데이터입니다.
이 데이터를 바탕으로 종합 분석 리포트를 작성해주세요.

{formatted}

{calibration_ctx}

---

**매우 중요**: 아래 구조를 정확히 따라주세요. 판단이 먼저, 근거가 뒤에 옵니다.

# {company_name} IPO 리서치 리포트

## 투자 판단

맨 첫 줄에 아래 형식으로 한 줄 판단을 작성:
**[참여 적극 권고]** 또는 **[참여 권고]** 또는 **[조건부 참여]** 또는 **[참여 비추천]** 또는 **[참여 불가]**

그 아래에:
- **한 줄 요약**: 이 IPO를 왜 참여/불참해야 하는지 1문장
- **적정 공모가 의견**: 현 공모가 대비 고평가/적정/저평가 판단
- **핵심 근거** 3개를 bullet point로 (각 1줄)

## 이 회사를 한마디로

기관투자자 리서치 톤으로 간결하게 작성. 아래 형식을 **정확히** 따르세요:

- **사업 개요**: 핵심 사업과 시장 포지셔닝을 한 문장으로 (예: "MIS 수술용 다관절 로봇 플랫폼 개발사, 국내 최초 FDA 510(k) 인허가 추진 중", "SiC 기반 전력반도체 파운드리 전문기업, 국내 유일 6인치 양산 라인 보유")
- **업종**: 대분류 > 소분류 형태 (예: "의료기기 > 수술로봇", "반도체 > 파운드리")
- **핵심 경쟁력**: 경쟁사 대비 기술적·사업적 차별화 요소를 한 줄로 (예: "다관절 170° 굴절 기술로 최소 절개 구현, 글로벌 경쟁사 대비 원가 우위", "독자 CDMO 플랫폼 기반 후보물질~임상 수탁 원스톱 대응 역량")
- **수익 모델**: 고객-제품-과금 구조로 요약 (예: "대형병원 대상 장비 납품(일시매출) + 시술당 소모품(반복매출)", "글로벌 제약사 기술이전 계약금 + 마일스톤 + 로열티")
- **핵심 리스크**: 투자 관점 핵심 리스크 한 줄 (예: "Pre-revenue 단계, 임상 3상 미진입으로 상업화 시점 불확실", "매출의 70%가 단일 고객 의존, 계약 해지 시 실적 급감 우려")
- **산업 해설**: 이 회사가 속한 산업을 비전문가도 이해할 수 있게 2~3문장으로 설명. 전문 용어가 나오면 괄호로 쉬운 설명을 덧붙인다. (예: "항체치료제는 우리 몸의 면역세포가 만드는 단백질(항체)을 인공적으로 대량 생산해 질병을 치료하는 약이다. 기존 화학 합성 약물보다 부작용이 적고 특정 질병만 정확히 공격할 수 있어 '표적치료'라 불린다. 다만 개발에 10년 이상, 수천억원이 소요되며 임상시험 성공률은 10% 내외로 매우 낮다.")

## 공모 개요
공모사항 요약을 테이블 형식으로 간결하게:
- 공모가, 시가총액, 공모주식수, 공모금액
- 주관사, 상장시장
- 주요 일정 (수요예측 → 청약 → 상장)

## 핵심 체크포인트
반드시 추가로 확인해야 할 사항 3~5개.
각 항목마다 "왜 확인해야 하는지"를 한 줄로 설명.

## 사업 분석
- 핵심 사업 내용과 시장 내 위치
- 제품/서비스의 경쟁력과 차별화 요소
- 시장 규모와 성장성
- 경쟁 현황과 진입 장벽
- **수익 구조**: 매출이 어디서 발생하는지를 "고객 → 제품/서비스 → 매출 비중" 형태로 설명. 반복 매출(구독/소모품)과 일회성 매출(장비 판매/라이선스)을 구분.

**중요**: 기관투자자가 읽는 리서치 수준의 전문적 톤을 유지하되, 업종 특화 용어에는 간결한 괄호 설명을 추가하세요.
예: "자본잠식(자본총계 음수)", "오버행(보호예수 해제에 따른 매도 압력)", "레퍼런스 확보(Tier 1 고객사 납품 실적)"

## 재무 분석
- 연도별 매출/영업이익/순이익 테이블 (반드시 포함)
- 매출 성장 추세, 수익성, 재무 건전성
- 특이사항 (일회성 매출, 자본잠식 등)

**참고**: 일반적 재무 용어(PER, 영업이익률 등)는 괄호 설명 불필요. 업종 특화 지표만 필요 시 간결하게 보충.

## 밸류에이션 검토
- 회사가 선정한 비교회사(Peer)의 적정성 평가
  (매출 규모 차이, 사업 유사성, 성장 단계 비교)
- 적용 PER/배수의 합리성
- 공모가 할인율 평가
- **Peer 비교 맥락**: 비교회사와의 매출 규모 차이가 크면 "A사는 매출 X조, 이 회사는 Y억 — Z배 차이"처럼 구체적으로 명시하고, 이 차이가 밸류에이션에 어떤 영향을 주는지 설명

## 수급 분석
- 상장일 유통가능물량 비율 평가
- 기간별 락업 해제 스케줄과 오버행 리스크
- 기관 수요예측 결과 해석 (경쟁률, 확약비율)
- 기존 투자자(VC/PE) Exit 가능성

## 리스크 요인
각 리스크를 심각도(높음/중간/낮음)와 함께 나열.

## AI 적정가 산출

**매우 중요**: 증권신고서의 밸류에이션 방법론을 기본 프레임으로 따르되, 가정을 비판적으로 재검토하여 독자적 적정가를 산출하세요.
- 증권신고서가 PER을 사용했으면 PER로, PSR을 사용했으면 PSR로 산출
- Peer 선정·미래 추정·할인율 각각에 대해 문제가 있으면 조정하되, **모든 항목을 동시에 하향 조정하지 마라**. 가장 문제가 큰 1~2개 가정만 조정하고, 나머지는 증권신고서 수치를 수용하라
- 각 조정에는 검증 가능한 근거를 반드시 제시 (과거 CAGR, 실제 Peer 배수, 업종 통계 등). "보수적으로"라는 이유만으로 숫자를 임의 축소하지 마라
- 최종 산출 후 sanity check: "이 적정가로 거래된다면 시가총액이 얼마인가? 동종 상장사 대비 합리적인가?" 확인

아래 형식을 **정확히** 따르세요:

**산출 방법**: [증권신고서 방법론 + 보수적 조정. 예: "증권신고서 PER 비교법 기반, 추정실적 보수적 조정"]

**산출 과정**:
1. **증권신고서 방법론**: [회사가 사용한 밸류에이션 방법과 주요 가정 요약]
2. **비판적 검토**: [Peer 적정성, 미래 추정의 공격성, 할인율 충분성 등 문제점]
3. **보수적 조정**: [어떤 가정을 어떻게 조정했는지 + **조정 근거**. 예: "추정 순이익 295억 → 150억 적용 (근거: 과거 3년 매출 CAGR XX%를 적용하면 2028년 매출 XX억, 영업이익률 XX% 가정 시 순이익 XX억)"]
4. **산출 결과**: [조정된 가정으로 재계산. 구체적 숫자 과정 포함]

**AI 산출 적정가**: XX,XXX원 ~ XX,XXX원
**현 공모가 대비**: [고평가 XX% / 적정 / 저평가 XX%]
**참여 권고**: [구체적 참여 전략. 예: "XX,XXX원 이하에서 제한적 참여" 또는 "참여 불가 — 현 공모가 기준 XX% 고평가"]
"""

    # 최종 분석은 Opus로 — 밸류에이션 추론 품질이 중요
    ANALYST_MODEL = "claude-opus-4-20250514"
    print(f"[AI 분석] 종합 리포트 생성 중... (model: {ANALYST_MODEL})")
    resp = client.messages.create(
        model=ANALYST_MODEL,
        max_tokens=8192,
        system=ANALYST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    report = resp.content[0].text
    print(f"[AI 분석] 리포트 생성 완료 ({len(report):,}자)")
    return report
