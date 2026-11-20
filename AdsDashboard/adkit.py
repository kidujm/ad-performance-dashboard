"""구글·메타 광고 대시보드가 같이 쓰는 도구 모음.

- 설정(config.json) 읽기
- GA4 Data API 호출(페이지 넘김 포함)
- 숫자·날짜 변환, 날짜 폴더 순회
- template.html에 데이터와 공통 CSS·JS를 끼워 한 장짜리 HTML 만들기

회사마다 달라지는 값(GA4 속성 번호, 계정 번호, 캠페인 이름 규칙 등)은 전부 config.json에 두고
코드에는 넣지 않는다. config.json은 .gitignore 대상이고, 저장소에는 config.example.json만 올린다.
"""
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
EXAMPLE_FILE = HERE / "config.example.json"


def load_config():
    """config.json을 읽는다. 없으면 예시 설정으로 돌아가 데모 모드에서도 화면이 뜨게 한다."""
    path = CONFIG_FILE if CONFIG_FILE.exists() else EXAMPLE_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def expand(path):
    """'~/...' 형태의 경로를 실제 경로로 바꾼다."""
    return Path(os.path.expanduser(path)) if path else None


def num(v):
    """CSV 칸의 '1,234' · '12.3%' · '--' 같은 글자를 숫자로. 못 읽으면 0."""
    v = (v or "").replace(",", "").replace("%", "").strip()
    try:
        return float(v)
    except ValueError:
        return 0.0


def ga_date(yyyymmdd):
    """GA4가 주는 '20261120'을 '2026-11-20'으로."""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def korean_date(text):
    """'2026년 11월 3일' 같은 글자에서 'YYYY-MM-DD'를 뽑는다. 없으면 None."""
    m = re.search(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일", text or "")
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def missing_days(start, have):
    """캠페인 시작일부터 어제까지 중 CSV가 없는 날짜 목록. 수집이 멈춘 걸 알아채고 따라잡는 데 쓴다."""
    import datetime as dt
    day, last = dt.date.fromisoformat(start), dt.date.today() - dt.timedelta(days=1)
    out = []
    while day <= last:
        if day.isoformat() not in have:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def day_folders(root):
    """data/csv/YYYY-MM-DD/ 폴더를 날짜순으로. 같은 날짜를 다시 받으면 뒤에 읽은 값이 이긴다."""
    return sorted(p for p in Path(root).glob("*") if p.is_dir())


# ---------------------------------------------------------------- GA4

def ga4_client(cfg):
    """서비스 계정 키 파일로 GA4 Data API 클라이언트를 만든다. 키 경로는 config에서만 읽는다."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient  # GA4를 안 쓰는 데모 모드에선 import 안 함
    key = expand(cfg.get("ga4_key_file"))
    if key:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    return BetaAnalyticsDataClient()


def ga4_filter(field, value, exact=False):
    """문자열 필터 하나. exact=False면 '포함' 조건."""
    from google.analytics.data_v1beta.types import Filter, FilterExpression
    mt = Filter.StringFilter.MatchType.EXACT if exact else Filter.StringFilter.MatchType.CONTAINS
    return FilterExpression(filter=Filter(field_name=field, string_filter=Filter.StringFilter(match_type=mt, value=value)))


def ga4_and(*exprs):
    from google.analytics.data_v1beta.types import FilterExpression, FilterExpressionList
    return FilterExpression(and_group=FilterExpressionList(expressions=list(exprs)))


def ga4_report(client, cfg, dims, metrics, start, end, dim_filter):
    """GA4 보고서를 끝까지(페이지 넘김) 받아 [차원값..., 지표값...] 행 목록으로 돌려준다."""
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
    rows, offset = [], 0
    while True:
        res = client.run_report(RunReportRequest(
            property=f"properties/{cfg['ga4_property_id']}",
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimension_filter=dim_filter,
            limit=100000, offset=offset,
        ))
        for r in res.rows:
            rows.append([v.value for v in r.dimension_values] + [float(v.value) for v in r.metric_values])
        offset += len(res.rows)
        if not res.rows or offset >= res.row_count:
            return rows


# ---------------------------------------------------------------- HTML

def render_html(template, output, **blocks):
    """template.html의 자리표시자를 채워 output에 쓴다.

    /*__COMMON_CSS__*/ · /*__COMMON_JS__*/ 는 adkit.css · adkit.js 내용으로,
    /*__이름__*/null 은 blocks[이름]을 JSON으로 바꿔 넣는다(예: DATA, CONFIG).
    결과는 외부 파일 없이 혼자 열리는 HTML 한 장이다(CDN 라이브러리만 사용).
    """
    html = Path(template).read_text(encoding="utf-8")
    html = html.replace("/*__COMMON_CSS__*/", (HERE / "adkit.css").read_text(encoding="utf-8"))
    html = html.replace("/*__COMMON_JS__*/", (HERE / "adkit.js").read_text(encoding="utf-8"))
    for name, value in blocks.items():
        # </script> 가 데이터 안에 있어도 스크립트가 끊기지 않게 '<' 를 이스케이프한다
        html = html.replace(f"/*__{name}__*/null", json.dumps(value, ensure_ascii=False).replace("<", "\\u003c"))
    Path(output).write_text(html, encoding="utf-8")
