"""구글 검색광고 성과 대시보드.

두 군데 숫자를 합쳐 dashboard.html 한 장을 만든다.
  1) 구글 애즈 보고서 CSV (fetch_csv.ps1이 매일 '어제' 기준으로 받아 data/csv/날짜/ 에 넣음)
     → 노출수 · 클릭수 · 광고비 · 전환수 · 품질평가점수 (애즈가 직접 집계한 값)
  2) GA4 Data API (애즈와 연결된 속성)
     → 광고 클릭 뒤 사이트에서의 세션 · 참여 · 주요 이벤트
구글 애즈 계정에는 API로 접속하지 않으므로 애즈 쪽 변경 내역에 아무것도 남지 않는다.

    python ads_dashboard.py          # 수집 + 대시보드 생성
    python ads_dashboard.py --open   # 생성 후 브라우저로 열기
    python ads_dashboard.py --demo   # 가짜 샘플 데이터(sample/)로 화면만 만들기 (키·계정 없이 실행)
"""
import csv
import datetime as dt
import json
import re
import sys
import webbrowser
from pathlib import Path

import adkit

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "ads.json"
CSV_DIR = BASE / "data" / "csv"
INSIGHT_DIR = BASE / "data" / "insights"  # 설정 변경 해설 노트 (insights.py가 만든다)
SAMPLE_FILE = BASE / "sample" / "ads_sample.json"
TEMPLATE = BASE / "template.html"
OUTPUT = BASE / "dashboard.html"

# GA4 지표: advertiserAd* 는 GA4에 연결된 애즈 계정의 광고 지표
METRICS_GROUP = ["advertiserAdImpressions", "advertiserAdClicks", "advertiserAdCost",
                 "sessions", "engagedSessions", "keyEvents"]
METRICS_QUERY = ["advertiserAdClicks", "advertiserAdCost", "sessions", "engagedSessions", "keyEvents"]


# ---------------------------------------------------------------- GA4

def collect_ga4(cfg):
    """최근 N일(기본 60일)을 매번 다시 받는다. 전환이 며칠 늦게 잡히는 것까지 반영하기 위해서."""
    client = adkit.ga4_client(cfg)
    end = dt.date.today()
    start = end - dt.timedelta(days=cfg["google"].get("days", 60))
    s, e = start.isoformat(), end.isoformat()
    only = adkit.ga4_filter("sessionGoogleAdsCampaignName", cfg["campaign_filter"])

    dims = ["date", "sessionGoogleAdsCampaignName", "sessionGoogleAdsAdGroupName"]
    groups = [r for r in adkit.ga4_report(client, cfg, dims, METRICS_GROUP, s, e, only) if r[1] != "(not set)"]
    # 검색어(sessionGoogleAdsQuery)는 클릭이 난 검색어만 잡힌다. 키워드 차원은 광고비 지표와 같이 못 씀(GA4 제약)
    queries = [r for r in adkit.ga4_report(client, cfg, dims + ["sessionGoogleAdsQuery"], METRICS_QUERY, s, e, only)
               if r[1] != "(not set)" and r[3] not in ("(not set)", "")]

    row = lambda r: {"date": adkit.ga_date(r[0]), "campaign": r[1], "adgroup": r[2]}
    return {
        "groups": [dict(row(r), imp=r[3], clk=r[4], cost=r[5], ses=r[6], eng=r[7], key=r[8]) for r in groups],
        "queries": [dict(row(r), query=r[3], clk=r[4], cost=r[5], ses=r[6], eng=r[7], key=r[8]) for r in queries],
    }


# ---------------------------------------------------------------- 구글 애즈 CSV

def read_ads_csv(path, campaign_filter):
    """구글 애즈 CSV: 1줄 보고서 이름, 2줄 기간, 3줄 머리글. (날짜, 머리글, 행 목록)을 돌려준다."""
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if len(rows) < 3:
        return None, [], []
    date = adkit.korean_date(rows[1][0] if rows[1] else "") or path.parent.name
    head = rows[2]
    out = [d for d in (dict(zip(head, r)) for r in rows[3:]) if campaign_filter in d.get("캠페인", "")]
    return date, head, out


def day_key(text):
    """'2026-11-13', '2026. 11. 13.', '2026년 11월 13일' 모두 'YYYY-MM-DD'로. 합계 줄 등은 None."""
    m = re.search(r"(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", text or "")
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def ad_name(row):
    """광고 이름은 최종 도착 URL 접미사의 utm_content 값으로 구분한다."""
    m = re.search(r"utm_content=([^&]+)", row.get("최종 도착 URL 접미사", ""))
    return m[1] if m else ""


def load_ads_csv(cfg):
    """날짜 폴더마다 키워드 · 검색어 · 광고 CSV를 읽는다. 같은 날짜·같은 표는 마지막 파일 기준."""
    kw, terms, ads = {}, {}, {}
    for day in adkit.day_folders(CSV_DIR):
        for f in day.glob("*.csv"):
            try:
                date, head, rows = read_ads_csv(f, cfg["campaign_filter"])
            except (OSError, UnicodeDecodeError, csv.Error) as e:  # 깨진 파일 하나 때문에 전체가 멈추지 않게
                print(f"skip {f.name}: {e}")
                continue
            if not rows or any("변경" in h for h in head):  # 변경 내역 CSV는 insights.py가 읽는다
                continue

            def base(d):
                # 광고 표에는 '클릭수' 열이 없어 '상호작용 수'로 대신한다
                return {"date": date, "campaign": d["캠페인"], "adgroup": d.get("광고그룹", ""),
                        "imp": adkit.num(d.get("노출수")), "clk": adkit.num(d.get("클릭수") or d.get("상호작용 수")),
                        "cost": adkit.num(d.get("비용")), "conv": adkit.num(d.get("전환수"))}

            # 빠진 날을 한 번에 받은 파일은 '일' 열로 나뉘어 있다 → 날짜별로 쪼갠다
            day_col = next((h for h in ("일", "날짜", "Day") if h in head), None)
            if day_col:
                by_day = {}
                for d in rows:
                    by_day.setdefault(day_key(d[day_col]), []).append(d)
                by_day.pop(None, None)
            else:
                by_day = {date: rows}
            for date, rows in by_day.items():
                if "검색어" in head:
                    terms[date] = [dict(base(d), term=d["검색어"], keyword=d.get("키워드", ""),
                                        match=d.get("검색 유형", "")) for d in rows]
                elif "키워드" in head:
                    kw[date] = [dict(base(d), keyword=d["키워드"], match=d.get("검색 유형", ""),
                                     qs=d.get("품질평가점수", "").strip()) for d in rows]
                elif "광고 효력" in head:
                    ads[date] = [dict(base(d), name=ad_name(d), strength=d.get("광고 효력", "")) for d in rows]
    flat = lambda m: [r for v in m.values() for r in v]
    return {"keywords": flat(kw), "terms": flat(terms), "ads": flat(ads)}


def load_insights():
    """data/insights/YYYY-MM-DD_제목.md 를 최신순으로. 제목은 파일 첫 줄의 '# 제목'."""
    notes = []
    for f in sorted(INSIGHT_DIR.glob("*.md"), reverse=True):
        text = f.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        notes.append({"date": f.name[:10], "title": first.lstrip("# ").strip() or f.stem, "md": text})
    return notes


# ---------------------------------------------------------------- 실행

def collect(cfg):
    data = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "groups": [], "queries": []}
    try:
        data.update(collect_ga4(cfg))
    except Exception as e:  # GA4가 막혀도 애즈 CSV 숫자로는 그린다
        print(f"ga4 skipped: {e}")
    data.update(load_ads_csv(cfg))
    # 검색어 표는 클릭이 없는 날 비어 있을 수 있어 키워드·광고 표만으로 빠진 날을 판단한다
    have = {r["date"] for r in data["keywords"]} & {r["date"] for r in data["ads"]}
    data["missing"] = adkit.missing_days(cfg["start_date"], have)
    data["insights"] = load_insights()
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def view_config(cfg):
    """화면에 필요한 설정만 넘긴다(키 경로 · 계정 번호 · 내부 URL은 HTML에 넣지 않는다)."""
    g = cfg["google"]
    return {"brand": cfg["brand"], "start": cfg["start_date"], "prefix": g.get("campaign_prefix", ""),
            "suffix": "_" + cfg["campaign_filter"], "adgroups": g.get("adgroups", {}), "adNotes": g.get("ad_notes", ""),
            "studyPage": g.get("study_page", "")}


def print_missing():
    """fetch_csv.ps1용: 빠진 날 중 가장 이른 날짜를 한 줄로(없으면 빈 줄)."""
    cfg = adkit.load_config()
    d = load_ads_csv(cfg)
    have = {r["date"] for r in d["keywords"]} & {r["date"] for r in d["ads"]}
    miss = adkit.missing_days(cfg["start_date"], have)
    print(miss[0] if miss else "")


def main():
    if "--missing" in sys.argv:
        return print_missing()
    cfg = adkit.load_config()
    demo = "--demo" in sys.argv
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8")) if demo else collect(cfg)
    adkit.render_html(TEMPLATE, OUTPUT, DATA=data, CONFIG=view_config(cfg))
    print(f"updated {data['updated']}  groups={len(data['groups'])}  keywords={len(data['keywords'])}")
    if "--open" in sys.argv:
        webbrowser.open(OUTPUT.as_uri())


if __name__ == "__main__":
    main()
