"""광고 관리자 '대량 가져오기 형식' 내보내기(data/settings/bulk_*.csv) → data/settings.json.

가장 최근 파일의 설정을 사람이 읽는 표(단계 · 항목 · 지금 설정 · 왜)로 바꾼다.
'왜'는 대행사에게 들은 것이 아니라 메타 권장 방식에 비춘 해석이다. 지난 파일과 달라진 항목은 changes 에 남긴다.

    python read_settings.py
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "AdsDashboard"))  # 공통 도구(adkit)
import adkit  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
SET_DIR = BASE / "data" / "settings"
OUT = BASE / "data" / "settings.json"
CFG = adkit.load_config()
CAMPAIGN_FILTER = CFG["campaign_filter"]


def read_bulk(path):
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    first = text.split("\n", 1)[0]
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t" if first.count("\t") > first.count(",") else ","))
    return [r for r in rows if CAMPAIGN_FILTER in r.get("Campaign Name", "")]


OBJECTIVE = {"Outcome Sales": "판매", "Outcome Leads": "잠재 고객", "Outcome Traffic": "트래픽",
             "Outcome Engagement": "참여", "Outcome Awareness": "인지도", "Outcome App Promotion": "앱 홍보"}
BID = {"Highest volume or value": "최대 볼륨 (자동 입찰)", "Cost per result goal": "결과당 비용 목표", "Bid cap": "입찰 한도"}
GOAL = {"OFFSITE_CONVERSIONS": "전환 수 최대화", "LANDING_PAGE_VIEWS": "랜딩 페이지 조회 최대화",
        "LINK_CLICKS": "링크 클릭 최대화", "VALUE": "전환 가치 최대화"}
IG_POS = {"stream": "피드", "story": "스토리", "reels": "릴스", "explore": "탐색 탭"}
CTA = {"LEARN_MORE": "더 알아보기", "SIGN_UP": "가입하기", "SHOP_NOW": "지금 구매하기"}


def _ymd(s):
    m, d, y = (s.split(" ")[0].split("/") + ["", "", ""])[:3]
    return f"{y}-{m}-{d}" if y else s


def interests(r):
    try:
        return [i["name"].split("(")[0] for g in json.loads(r.get("Flexible Inclusions") or "[]")
                for i in g.get("interests", [])]
    except ValueError:
        return []


def rows_of(bulk):
    c = bulk[0]
    adv = c.get("Advantage Audience") == "1"
    ints = interests(c)
    places = [p.strip() for p in c.get("Publisher Platforms", "").split(",") if p.strip()]
    pos = []
    if "facebook" in places:
        pos.append("페이스북 " + ", ".join({"feed": "피드"}.get(p.strip(), p.strip()) for p in c.get("Facebook Positions", "").split(",") if p.strip()))
    if "instagram" in places:
        pos.append("인스타그램 " + ", ".join(IG_POS.get(p.strip(), p.strip()) for p in c.get("Instagram Positions", "").split(",") if p.strip()))
    if "threads" in places:
        pos.append("스레드")
    budget = c.get("Ad Set Daily Budget") or "0"
    cbo = bool(c.get("Campaign Daily Budget") or c.get("Campaign Lifetime Budget"))

    R = lambda level, item, value, why: {"level": level, "item": item, "value": value, "why": why}
    out = [
        R("캠페인", "목표", OBJECTIVE.get(c.get("Campaign Objective"), c.get("Campaign Objective", "")),
          "트래픽 목표는 '클릭 잘하는 사람'을 찾고, 판매 목표는 '사이트에서 전환까지 하는 사람'을 찾음. 원하는 결과가 사이트 안 행동이라 판매(전환)로 둠"),
        R("캠페인", "예산 위치", "캠페인 예산 사용" if cbo else "광고 세트 예산 (캠페인 예산 끔)",
          "광고 세트가 하나뿐이면 캠페인 예산을 켤 이유가 없음. 세트를 늘릴 때 다시 볼 항목"),
        R("캠페인", "시작일 · 이름 규칙", f"{_ymd(c.get('Campaign Start Time', ''))} · 이름 끝 _{CAMPAIGN_FILTER}",
          "구글 캠페인과 같은 이름 규칙(끝 날짜 = 시작일). 두 매체를 같은 날 켜서 비교하기 쉬움"),
        R("광고 세트", "전환 위치", {"WEBSITE": "웹사이트"}.get(c.get("Destination Type"), c.get("Destination Type", "")),
          "사이트 안 행동이 목적이라 웹사이트"),
        R("광고 세트", "성과 목표 · 전환 이벤트",
          f"{GOAL.get(c.get('Optimization Goal'), c.get('Optimization Goal', ''))} · 맞춤 전환 {c.get('Optimized Custom Conversion ID', '').replace('cc:', '')}",
          "메타는 여기 고른 이벤트를 한 사람을 닮은 사람에게 광고를 보냄. 가입보다 실제 행동에 가까운 이벤트를 맞춤 전환으로 만들어 지정"),
        R("광고 세트", "입찰 전략", BID.get(c.get("Ad Set Bid Strategy"), c.get("Ad Set Bid Strategy", "")),
          "전환 기록이 거의 없는 새 세트라 목표 단가를 정할 근거가 없음. 먼저 자동 입찰로 단가 범위를 알아냄"),
        R("광고 세트", "과금", {"IMPRESSIONS": "노출 1,000회당"}.get(c.get("Billing Event"), c.get("Billing Event", "")),
          "전환 최적화는 노출 과금만 가능. 클릭이 없어도 보이면 돈이 나감"),
        R("광고 세트", "일일 예산", f"${budget}",
          "학습 기간을 넘으려면 7일 안에 결과 약 50개가 필요. 일일 예산은 '목표 결과당 비용 × 50 ÷ 7'을 기준으로 잡음"),
        R("광고 세트", "지역", f"{c.get('Countries', '')} · 사는 곳 + 최근 위치 + 자주 가는 곳",
          "서비스 지역에 맞춤. 위치 유형은 기본값(넓게)"),
        R("광고 세트", "타겟", ("Advantage+ 타겟 켬 · " if adv else "직접 타겟 · ")
          + f"나이 {c.get('Age Min', '')}세 이상(제안 {c.get('Age Range', '').replace(', ', '~')}세) · 관심사 제안 {len(ints)}개",
          f"Advantage+ 타겟은 나이·관심사를 '힌트'로만 쓰고 메타가 더 넓게 찾음. {c.get('Age Min', '')}세 미만은 확실히 빼고(하한선), 나머지는 메타에게 맡김"),
        R("광고 세트", "관심사 힌트", ", ".join(ints),
          "힌트라서 이 안에만 나가는 건 아님"),
        R("광고 세트", "게재 위치", " / ".join(pos) + " · 오디언스 네트워크·메신저 제외",
          "자동 게재 위치 대신 직접 고름. 사이트로 나가는 클릭 질이 낮은 외부 앱(오디언스 네트워크)·메신저를 뺌"),
        R("광고 세트", "기기", c.get("Device Platforms", "").replace("mobile", "모바일").replace("desktop", "데스크톱"),
          "모바일에서 보고 PC로 이어서 행동하는 경우가 있어 둘 다"),
    ]
    for a in bulk:
        kind = "영상 (릴스·스토리용 세로 영상 따로)" if a.get("Video ID") else "이미지"
        out.append(R("광고", a.get("Ad Name", ""), f"{kind} · 제목 「{a.get('Title', '')}」",
                     f"본문: {a.get('Body', '')}"))
    a = bulk[0]
    out += [
        R("광고", "버튼 · 도착 주소", f"{CTA.get(a.get('Call to Action'), a.get('Call to Action', ''))} · {a.get('Link', '')}",
          "가입 페이지보다 바로 써 볼 수 있는 페이지로 보냄. '구매' 같은 강한 버튼 대신 부담 적은 버튼"),
        R("광고", "자동 소재 보정", "끔 (문구 사람별 최적화 끔, Advantage+ 크리에이티브 끔)",
          "소재끼리 그대로 비교하려고 메타가 문구·이미지를 바꾸지 않게 함"),
        R("광고", "URL 매개변수", a.get("URL Tags", ""),
          "{{ad.name}}은 클릭 때 광고 이름으로 바뀜. GA4에서 소재별로 나눠 보는 근거"),
    ]
    return out


def main():
    files = sorted(SET_DIR.glob("bulk_*.csv"))
    if not files:
        print("no settings file")
        return
    cur = read_bulk(files[-1])
    if not cur:
        print(f"no {CAMPAIGN_FILTER} campaign in {files[-1].name}")
        return
    rows = rows_of(cur)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    before = {(r["level"], r["item"]): r["value"] for r in old.get("rows", [])}
    changes = old.get("changes", [])
    if before:
        date = files[-1].stem.replace("bulk_", "")
        for r in rows:
            v = before.get((r["level"], r["item"]))
            if v is not None and v != r["value"]:
                changes.append({"date": date, "item": f"{r['level']} · {r['item']}", "before": v, "after": r["value"]})
    data = {"source": f"출처: 광고 관리자 설정 내보내기 {files[-1].stem.replace('bulk_', '')} 기준. '왜'는 메타 권장 방식에 비춘 해석(대행사 확인 전).",
            "rows": rows, "changes": changes}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"settings rows={len(rows)} changes={len(changes)}")


if __name__ == "__main__":
    main()
