"""메타(페이스북·인스타그램) 광고 성과 대시보드.

두 군데 숫자를 합쳐 dashboard.html 한 장을 만든다.
  1) 광고 관리자 '테이블 데이터 내보내기' CSV (fetch_meta.ps1이 매일 받아 data/csv/날짜/ 에 넣음)
     → 광고비 · 노출수 · 도달 · 링크 클릭 · LPV · 결과(맞춤 전환) · 품질 순위
  2) GA4 Data API (utm_source=meta 세션)
     → 광고 클릭 뒤 사이트에서의 세션 · 참여 · 주요 이벤트 (utm_content = 광고 이름)
광고 관리자에서는 내보내기만 하므로 광고 계정 활동 내역에 설정 변경이 남지 않는다.

    python meta_dashboard.py          # 수집 + 대시보드 생성
    python meta_dashboard.py --open   # 생성 후 브라우저로 열기
    python meta_dashboard.py --demo   # 가짜 샘플 데이터(sample/)로 화면만 만들기 (키·계정 없이 실행)
"""
import csv
import datetime as dt
import json
import sys
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "AdsDashboard"))  # 공통 도구(adkit)는 구글 대시보드 폴더에 있다
import adkit  # noqa: E402

DATA_FILE = BASE / "data" / "meta.json"
CSV_DIR = BASE / "data" / "csv"
SETTINGS_FILE = BASE / "data" / "settings.json"  # read_settings.py가 대량 내보내기에서 뽑은 설정 표
SAMPLE_FILE = BASE / "sample" / "meta_sample.json"
TEMPLATE = BASE / "template.html"
OUTPUT = BASE / "dashboard.html"

GA_METRICS = ["sessions", "engagedSessions", "keyEvents", "newUsers", "averageSessionDuration"]


def collect_ga4(cfg):
    """utm_source=meta 이고 캠페인 이름에 필터 글자가 든 세션을 날짜 · 광고(utm_content)별로."""
    client = adkit.ga4_client(cfg)
    flt = adkit.ga4_and(adkit.ga4_filter("sessionSource", "meta", exact=True),
                        adkit.ga4_filter("sessionCampaignName", cfg["campaign_filter"]))
    rows = adkit.ga4_report(client, cfg, ["date", "sessionCampaignName", "sessionManualAdContent"], GA_METRICS,
                            cfg["start_date"], "today", flt)
    # 평균 머문 시간은 합칠 수 없으니 '총 머문 시간'(평균 × 세션)으로 바꿔 두고 화면에서 다시 나눈다
    return [{"date": adkit.ga_date(d), "campaign": c, "ad": ad, "ses": ses, "eng": eng, "key": key, "new": new,
             "dur": avg * ses} for d, c, ad, ses, eng, key, new, avg in rows]


# ---------------------------------------------------------------- 광고 관리자 CSV

LEVELS = (("ad", "광고 이름"), ("adset", "광고 세트 이름"), ("campaign", "캠페인 이름"))


def read_report(path):
    """보고서 CSV 한 개 → (단계, 행 목록). 보고 시작=종료인 행은 하루치, 아니면 기간 합계."""
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None, []
    head = rows[0].keys()
    level, col = next(((lv, c) for lv, c in LEVELS if c in head), (None, None))
    if not level:
        return None, []
    spend_col = next((h for h in head if h.startswith("지출 금액")), "지출 금액 (USD)")  # 예: '지출 금액 (USD)'
    cur = spend_col.split("(")[-1].rstrip(")") if "(" in spend_col else ""
    n = lambda d, k: adkit.num(d.get(k))
    out = []
    for d in rows:
        if not d.get(col) or d.get("보고 시작", "").startswith("No data"):
            continue
        out.append({
            "level": level, "name": d[col], "start": d.get("보고 시작", ""), "end": d.get("보고 종료", ""),
            "status": d.get("광고 게재") or d.get("광고 세트 게재") or d.get("캠페인 게재", ""),
            "result_type": d.get("결과 표시 도구", ""), "res": n(d, "결과"),
            "reach": n(d, "도달"), "freq": n(d, "빈도"),
            "budget": n(d, "광고 세트 예산"), "budget_type": d.get("광고 세트 예산 유형", ""),
            "spend": n(d, spend_col), "cur": cur,
            "imp": n(d, "노출"), "link": n(d, "링크 클릭"), "clk": n(d, "클릭(전체)"), "lpv": n(d, "랜딩 페이지 조회"),
            "q_rank": d.get("품질 순위", ""), "e_rank": d.get("참여율 순위", ""), "c_rank": d.get("전환율 순위", ""),
            "attr": d.get("기여 설정", ""),
        })
    return level, out


def load_csv(start):
    """날짜 폴더마다 광고 · 광고 세트 · 캠페인 CSV를 읽는다.
    하루치(daily)는 (날짜, 단계, 이름)마다 마지막 파일 기준, 기간 합계(totals)는 가장 최근 파일 기준."""
    daily, totals = {}, {}
    for day in adkit.day_folders(CSV_DIR):
        for f in sorted(day.glob("*.csv"), key=lambda p: p.stat().st_mtime):
            try:
                level, rows = read_report(f)
            except (OSError, UnicodeDecodeError, csv.Error) as e:  # 깨진 파일 하나 때문에 전체가 멈추지 않게
                print(f"skip {f.name}: {e}")
                continue
            for r in rows:
                if r["start"] and r["start"] == r["end"]:
                    daily[(r["start"], level, r["name"])] = dict(r, date=r["start"])
                elif r["start"] >= start or r["end"] >= start:
                    totals[(level, r["name"])] = r
    return {"daily": sorted(daily.values(), key=lambda r: (r["date"], r["level"], r["name"])),
            "totals": list(totals.values())}


# ---------------------------------------------------------------- 실행

def collect(cfg):
    data = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "start": cfg["start_date"]}
    data.update(load_csv(cfg["start_date"]))
    try:
        data["ga"] = collect_ga4(cfg)
    except Exception as e:  # GA4가 막혀도 광고 관리자 숫자로는 그린다
        print(f"ga4 skipped: {e}")
        data["ga"] = []
    data["settings"] = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) if SETTINGS_FILE.exists() else {}
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def view_config(cfg):
    """화면에 필요한 설정만 넘긴다(계정 번호 · 키 경로는 HTML에 넣지 않는다)."""
    m = cfg["meta"]
    book = adkit.expand(m.get("book_pdf"))
    return {"brand": cfg["brand"], "ads": m.get("ads", {}),
            "bookPdf": book.as_uri() if book and book.exists() else ""}


def main():
    cfg = adkit.load_config()
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8")) if "--demo" in sys.argv else collect(cfg)
    adkit.render_html(TEMPLATE, OUTPUT, DATA=data, CONFIG=view_config(cfg))
    print(f"updated {data['updated']}  daily={len(data['daily'])}  totals={len(data['totals'])}  ga={len(data['ga'])}")
    if "--open" in sys.argv:
        webbrowser.open(OUTPUT.as_uri())


if __name__ == "__main__":
    main()
