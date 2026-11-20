"""구글 애즈 변경 내역 CSV에서 새 설정 변경을 찾아, 왜 그렇게 바꿨는지 해설 노트를 만든다.

fetch_csv.ps1이 대시보드 갱신 전에 부른다. 새 변경이 없으면 아무것도 하지 않는다(토큰 0).
해설은 claude CLI(헤드리스, 웹 검색 허용)가 쓰고 data/insights/날짜_설정변경.md 로 저장된다.

    python insights.py            # 새 변경이 있으면 노트 생성
    python insights.py --dry-run  # claude 호출 없이 새 변경만 출력
"""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import adkit

sys.stdout.reconfigure(encoding="utf-8")

CFG = adkit.load_config()
CAMPAIGN_FILTER = CFG["campaign_filter"]
BASE = Path(__file__).resolve().parent
CSV_DIR = BASE / "data" / "csv"
INSIGHT_DIR = BASE / "data" / "insights"
SEEN_FILE = INSIGHT_DIR / "_seen.json"
# claude CLI 위치: PATH에서 먼저 찾고, 없으면 npm 전역 설치 경로
CLAUDE = shutil.which("claude") or str(Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
STRUCTURE_NOTE = INSIGHT_DIR / f"{CFG['start_date']}_구조분석.md"
BASELINE = CFG["start_date"]  # 이 날까지의 변경(처음 세팅)은 구조분석 노트가 다룬다
MAX_ROWS = 60  # 한 번에 해설할 변경 수 상한 (토큰 절약)

PROMPT = """너는 구글 광고를 공부하는 마케팅 담당자를 돕는 선생님이다. 광고 대행사가 {brand} 구글 검색 광고의 설정을 아래처럼 바꿨다.
각 변경마다 "대행사가 왜 이렇게 바꿨을까"를 구글 공식 도움말(support.google.com/google-ads)과 업계 글을 웹에서 찾아 근거로 설명해라.

출력 규칙:
- 마크다운만 출력한다. 첫 줄은 "# " 로 시작하는 제목 한 줄(예: # 10/20 설정 변경: 예산 증액과 키워드 추가).
- 제목 바로 다음에 "## 한 줄 요약" 소제목과 아래 3줄을 정확히 이 형식으로 쓴다(각 40자 안팎, 요약 표에 들어간다):
  - **바뀐 것:** ...
  - **이유:** ...
  - **지켜볼 것:** ...
- 변경마다 "## 무엇이 바뀌었나: ..." 소제목, 그 아래 굵은 항목명 + 짧은 불릿으로 이유·근거 링크·공부 포인트를 쓴다.
- 근거가 업계 관행이면 [업계 관행](링크), 공식이면 [구글 도움말](링크)로 표시한다. 링크는 실제로 찾은 것만 쓴다.
- 추정이면 "(추정)"이라고 밝힌다. 이 변경이 학습 기간을 다시 시작시키는지 꼭 짚는다.
- 마지막에 "## 지켜볼 것" 으로 앞으로 며칠 동안 대시보드에서 볼 숫자를 2~3개 적는다.
- 존댓말(합니다·입니다). 엠대시(—) 금지. 과장·홍보 문구 금지. 줄글보다 목록.
- 설정을 바꾸라고 권하지 않는다. 이유를 이해하는 게 목적이다.

지금까지의 계정 구조 요약은 아래 노트에 있다:
---
{structure}
---

이번에 새로 생긴 변경 내역(CSV 행, 사용자 열은 지움):
{changes}
"""


def read_changes():
    """모든 날짜 폴더의 변경 내역 CSV에서 대상 캠페인 행을 (날짜, 행 dict)로."""
    out = []
    for day in sorted(p for p in CSV_DIR.glob("*") if p.is_dir()):
        for f in day.glob("*.csv"):
            try:
                with f.open(encoding="utf-8-sig") as fh:
                    rows = list(csv.reader(fh))
            except (OSError, UnicodeDecodeError, csv.Error) as e:  # 깨진 파일 하나 때문에 전체가 멈추지 않게
                print(f"skip {f.name}: {e}")
                continue
            if len(rows) < 4 or not any("변경" in h for h in rows[2]):
                continue
            head = rows[2]
            keep = [i for i, h in enumerate(head) if "사용자" not in h]  # 담당자 이메일은 밖으로 안 보낸다
            for r in rows[3:]:
                if any(CAMPAIGN_FILTER in c for c in r):
                    d = {head[i]: re.sub(r"\S+@\S+", "(이메일)", r[i]) for i in keep if i < len(r)}
                    out.append((day.name, d))
    return out


def key(row):
    return hashlib.sha1(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    INSIGHT_DIR.mkdir(parents=True, exist_ok=True)
    seen = set(json.loads(SEEN_FILE.read_text(encoding="utf-8"))) if SEEN_FILE.exists() else set()
    new = [(d, r) for d, r in read_changes() if d > BASELINE and key(r) not in seen][:MAX_ROWS]
    if not new:
        print("no new changes")
        return
    date = max(d for d, _ in new)
    changes = "\n".join(json.dumps(r, ensure_ascii=False) for _, r in new)
    print(f"{len(new)} new changes (latest {date})")
    if "--dry-run" in sys.argv:
        print(changes)
        return

    structure = STRUCTURE_NOTE.read_text(encoding="utf-8") if STRUCTURE_NOTE.exists() else "(없음)"
    env = dict(os.environ, DISABLE_OMC="1")
    res = subprocess.run([str(CLAUDE), "-p", "--model", "sonnet", "--allowedTools", "WebSearch,WebFetch"],
                         input=PROMPT.format(brand=CFG["brand"], structure=structure, changes=changes),
                         capture_output=True, text=True, encoding="utf-8", timeout=900, env=env)
    md = res.stdout.strip()
    if res.returncode or not md.startswith("#"):
        print(f"claude failed ({res.returncode}): {res.stderr[-500:] or md[:500]}")
        return  # seen에 안 넣었으니 다음 실행 때 다시 시도한다
    md = md.replace("—", ",")
    out = INSIGHT_DIR / f"{date}_설정변경.md"
    n = 2
    while out.exists():
        out = INSIGHT_DIR / f"{date}_설정변경_{n}.md"
        n += 1
    out.write_text(md + "\n", encoding="utf-8")
    SEEN_FILE.write_text(json.dumps(sorted(seen | {key(r) for _, r in new})), encoding="utf-8")
    print(f"wrote {out.name}")


if __name__ == "__main__":
    main()
