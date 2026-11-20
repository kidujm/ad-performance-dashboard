"""공개 저장소용 가짜 샘플 데이터를 만든다. 실제 광고 숫자는 하나도 쓰지 않고 난수(seed 고정)로 만든다.

    python make_sample.py   # sample/ads_sample.json, ../MetaAdsDashboard/sample/meta_sample.json 생성

이 데이터로 `python ads_dashboard.py --demo` · `python meta_dashboard.py --demo` 를 돌리면
GA4 키나 광고 계정 없이 화면을 볼 수 있다.
"""
import datetime as dt
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
rnd = random.Random(42)
END = dt.date.today() - dt.timedelta(days=1)
DAYS = [(END - dt.timedelta(days=i)).isoformat() for i in range(59, -1, -1)]
CAMPAIGN = "SAMPLE_Google_KR_SEARCH_INTENT_000000"
BRAND_CAMPAIGN = "SAMPLE_Google_KR_SEARCH_BRAND_000000"

# 가상의 예약 관리 서비스를 광고한다고 가정한 광고그룹 · 키워드
ADGROUPS = {
    "INTENT_BOOKING": ["예약 관리 프로그램", "온라인 예약 시스템", "예약 앱 만들기"],
    "INTENT_PRICE": ["예약 프로그램 가격", "무료 예약 시스템"],
    "INTENT_USECASE": ["미용실 예약", "필라테스 예약 관리", "스터디카페 예약"],
    "BRAND": ["샘플브랜드", "sample brand"],
}
TERMS = {
    "INTENT_BOOKING": ["예약 관리 프로그램 추천", "예약 시스템 만들기", "온라인 예약 페이지"],
    "INTENT_PRICE": ["예약 프로그램 무료", "예약 시스템 비용"],
    "INTENT_USECASE": ["미용실 예약 프로그램", "필라테스 회원 관리"],
    "BRAND": ["샘플브랜드", "샘플브랜드 가격"],
}


def google():
    groups, queries, keywords, terms, ads = [], [], [], [], []
    for i, d in enumerate(DAYS):
        trend = 0.7 + i / len(DAYS) * 0.6  # 기간 뒤로 갈수록 조금씩 늘어나는 흐름
        for g, kws in ADGROUPS.items():
            camp = BRAND_CAMPAIGN if g == "BRAND" else CAMPAIGN
            cpc = 300 if g == "BRAND" else rnd.uniform(700, 1500)
            gi = gc = gcost = gconv = 0
            for kw in kws:
                imp = int(rnd.uniform(20, 160) * trend)
                clk = int(imp * rnd.uniform(0.02, 0.12))
                cost = round(clk * cpc * rnd.uniform(0.8, 1.2))
                conv = sum(rnd.random() < 0.06 for _ in range(clk))
                match = rnd.choice(["완전 일치검색", "구문 검색"])
                keywords.append({"date": d, "campaign": camp, "adgroup": g, "keyword": f"[{kw}]" if "일치" in match else f'"{kw}"',
                                 "match": match, "qs": str(rnd.randint(4, 9)), "imp": imp, "clk": clk, "cost": cost, "conv": conv})
                gi, gc, gcost, gconv = gi + imp, gc + clk, gcost + cost, gconv + conv
            for t in TERMS[g]:
                imp = int(rnd.uniform(5, 60) * trend)
                clk = int(imp * rnd.uniform(0, 0.1))
                terms.append({"date": d, "campaign": camp, "adgroup": g, "term": t, "keyword": "", "match": "구문 검색",
                              "imp": imp, "clk": clk, "cost": round(clk * cpc), "conv": 0})
                if clk:
                    ses = clk + rnd.randint(0, 2)
                    queries.append({"date": d, "campaign": camp, "adgroup": g, "query": t, "clk": clk, "cost": round(clk * cpc),
                                    "ses": ses, "eng": int(ses * rnd.uniform(0.4, 0.8)), "key": int(ses * 0.05)})
            for name, share in ((f"{g}_RSA_01", 0.55), (f"{g}_RSA_02", 0.45)):
                ads.append({"date": d, "campaign": camp, "adgroup": g, "name": name, "strength": rnd.choice(["좋음", "보통", "매우 좋음"]),
                            "imp": int(gi * share), "clk": int(gc * share), "cost": round(gcost * share), "conv": int(gconv * share)})
            ses = gc + rnd.randint(0, 3)
            groups.append({"date": d, "campaign": camp, "adgroup": g, "imp": gi, "clk": gc, "cost": gcost,
                           "ses": ses, "eng": int(ses * rnd.uniform(0.45, 0.75)), "key": gconv})
    # 설정 변경 로그 예시. 실제 계정의 변경이 아니라 가상으로 쓴 노트다
    insight = ("# (가상 예시) 제외 키워드 추가와 입찰가 조정\n\n"
               "> 이 노트는 화면 예시를 위해 가상으로 작성했습니다. 실제 계정의 설정 변경이 아닙니다.\n\n"
               "## 한 줄 요약\n"
               "- **바뀐 것:** 정보성 검색어 2개를 제외 키워드로 추가, 가격 의도 그룹 입찰가 10% 인하\n"
               "- **이유:** 클릭은 나는데 전환이 없는 검색어에 광고비가 쓰임\n"
               "- **지켜볼 것:** 가격 의도 그룹의 CPC · CVR 변화\n\n"
               "## 무엇이 바뀌었나: 제외 키워드 추가\n"
               "- **변경:** \"예약 프로그램 무료 다운로드\", \"예약 시스템 개발 방법\"을 구문 제외 키워드로 등록\n"
               "- **이유:** 직접 만들 방법을 찾는 검색이라 서비스 가입으로 이어질 가능성이 낮음\n"
               "- **공부 포인트:** 제외 키워드는 유사 변형(띄어쓰기 · 오타)을 자동으로 막아 주지 않아 표기별로 따로 넣어야 함\n\n"
               "## 무엇이 바뀌었나: 입찰가 10% 인하\n"
               "- **이유:** 가격 의도 그룹의 CPA가 다른 그룹보다 높음\n"
               "- **학습 기간:** 입찰 전략을 바꾼 것이 아니라 금액만 조정해 학습이 처음부터 다시 시작되지는 않음 (추정)\n\n"
               "## 지켜볼 것\n- 가격 의도 그룹의 노출수가 크게 줄지 않는지\n- 검색어 보고서에 비슷한 정보성 검색어가 새로 생기는지\n")
    return {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "groups": groups, "queries": queries,
            "keywords": keywords, "terms": terms, "ads": ads,
            "insights": [{"date": DAYS[-7], "title": "(가상 예시) 제외 키워드 추가와 입찰가 조정", "md": insight}]}


META_ADS = ["SAMPLE_REVIEW_01", "SAMPLE_SCREEN_01", "SAMPLE_PRICE_01"]


def meta():
    start = DAYS[-30]
    daily, ga = [], []
    for d in DAYS[-30:]:
        for j, name in enumerate(META_ADS):
            w = (0.5, 0.35, 0.15)[j]
            spend = round(rnd.uniform(40, 70) * w, 2)
            imp = int(spend / rnd.uniform(0.015, 0.025))
            link = int(imp * rnd.uniform(0.02, 0.045))
            lpv = int(link * rnd.uniform(0.75, 0.9))
            res = sum(rnd.random() < 0.08 for _ in range(lpv))
            daily.append({"level": "ad", "name": name, "date": d, "start": d, "end": d, "status": "활성", "result_type": "맞춤 전환",
                          "res": res, "reach": int(imp / 1.3), "freq": 1.3, "budget": 0, "budget_type": "", "spend": spend, "cur": "USD",
                          "imp": imp, "link": link, "clk": int(link * 1.4), "lpv": lpv, "q_rank": "", "e_rank": "", "c_rank": "", "attr": ""})
            ses = int(lpv * rnd.uniform(1.0, 1.3))
            ga.append({"date": d, "campaign": "SAMPLE_Meta_KR_000000", "ad": name, "ses": ses, "eng": int(ses * rnd.uniform(0.4, 0.6)),
                       "key": 0, "new": int(ses * 0.8), "dur": ses * rnd.uniform(90, 180)})
    totals = [{"level": "ad", "name": n, "start": start, "end": DAYS[-1], "q_rank": q, "reach": 0, "spend": 0, "cur": "USD"}
              for n, q in zip(META_ADS, ["평균 이상", "평균", "판정 전"])]
    totals.append({"level": "adset", "name": "SAMPLE_ADSET", "start": start, "end": DAYS[-1], "reach": 48000, "spend": 0, "cur": "USD"})
    settings = {"source": "가상 예시입니다. 설정과 이유 모두 실제 계정이 아니라 화면 예시를 위해 작성했습니다.", "changes": [], "rows": [
        {"level": "캠페인", "item": "목표", "value": "판매", "why": "클릭이 아니라 사이트 안의 전환 행동을 할 사람을 찾도록 판매(전환) 목표를 씀"},
        {"level": "광고 세트", "item": "입찰 전략", "value": "최대 볼륨 (자동 입찰)", "why": "전환 기록이 쌓이기 전이라 목표 단가를 정할 근거가 없음"},
        {"level": "광고 세트", "item": "타겟", "value": "Advantage+ 타겟 · 나이 하한만 지정", "why": "나이 · 관심사는 힌트로만 주고 메타가 넓게 찾게 함"},
        {"level": "광고", "item": "URL 매개변수", "value": "utm_source=meta&utm_content={{ad.name}}", "why": "GA4에서 소재별로 나눠 보기 위한 표시"},
    ]}
    return {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "start": start, "daily": daily, "totals": totals,
            "ga": ga, "settings": settings}


if __name__ == "__main__":
    out = BASE / "sample" / "ads_sample.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(google(), ensure_ascii=False), encoding="utf-8")
    mout = BASE.parent / "MetaAdsDashboard" / "sample" / "meta_sample.json"
    mout.parent.mkdir(exist_ok=True)
    mout.write_text(json.dumps(meta(), ensure_ascii=False), encoding="utf-8")
    print(out, mout)
