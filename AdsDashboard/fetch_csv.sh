#!/bin/bash
# macOS용: 구글 애즈 CSV 받기 → data/csv/날짜/ 로 옮기기 → 대시보드 갱신 (fetch_csv.ps1과 같은 순서)
# 브라우저 수집은 claude CLI + 크롬(Claude 확장)으로 한다. 수집이 실패해도 GA4 수집과 대시보드 갱신은 진행한다.
cd "$(dirname "$0")" || exit 1
BASE="$(pwd)"
mkdir -p logs
LOG="logs/fetch-$(date +%Y%m%d-%H%M).log"
log() { echo "$(date +%H:%M:%S) $*" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null; }

PY="$(command -v python3 || command -v python)"
YESTERDAY="$(date -v-1d +%Y-%m-%d)"
DOWNLOADS="$HOME/Downloads"
STAMP="$(mktemp)"  # 이 파일보다 새 CSV = 이번에 받은 파일
URL="$("$PY" -c "import adkit; print(adkit.load_config()['google']['ads_keywords_url'])")"

# 지난 실행이 실패해 빠진 날이 있으면 그날부터 어제까지 일별로 한 번에 받는다
FROM="$("$PY" ads_dashboard.py --missing)"
if [[ -n "$FROM" && "$FROM" < "$YESTERDAY" ]]; then
  RANGE="기간은 맞춤 '$FROM ~ $YESTERDAY'로 맞추고, 표 위 세그먼트 > 시간 > '일'을 켠 상태로"
  log "catch up from $FROM"
else
  RANGE="기간은 '어제'로 맞춘 뒤"
fi

PROMPT="크롬(Claude in Chrome 도구)으로만 작업한다. 새 탭 1개를 만들어 그 탭에서만 작업하고, 끝나면 그 탭을 닫는다.
READ-ONLY. 저장/적용/게시/수정, 열 변경, 필터 저장, 권장사항 적용 금지.
$URL
보기는 '모든 캠페인', $RANGE 아래 표를 각각 다운로드 > .csv (변경 내역은 세그먼트 없이):
1) 키워드 > 검색 키워드 표
2) 인사이트 및 보고서 > 검색어 표
3) 캠페인 > 광고 표
4) 변경 내역 표 (왼쪽 메뉴 검색창에 '변경 내역')
로그인 화면이 나오면 아무것도 입력하지 말고 멈춘 뒤 FAIL=LOGIN 이라고만 답한다.
크롬 확장이 연결되지 않았으면 FAIL=EXTENSION 이라고만 답한다.
보고(영어 표식만): 받은 표 번호를 OK=1,2,3,4 처럼, 실패는 FAIL=번호:이유."
log 'claude chrome start'
printf '%s' "$PROMPT" | claude -p --chrome --model sonnet --allowedTools 'mcp__claude-in-chrome__*' >> "$LOG" 2>&1

# 이번에 받은 CSV를 날짜 폴더로 옮긴다 (같은 표를 두 번 받아 붙은 ' (1)'은 떼서 하나로)
DEST="data/csv/$YESTERDAY"
mkdir -p "$DEST"
moved=0
while IFS= read -r -d '' f; do
  name="$(basename "$f" | sed -E 's/ \([0-9]+\)//')"
  mv -f "$f" "$DEST/$name" && log "moved $name" && moved=1
done < <(find "$DOWNLOADS" -maxdepth 1 -name '*.csv' -newer "$STAMP" -print0)
rm -f "$STAMP"
[[ $moved == 0 ]] && log 'no csv downloaded'

"$PY" insights.py >> "$LOG" 2>&1
"$PY" ads_dashboard.py >> "$LOG" 2>&1

LEFT="$("$PY" ads_dashboard.py --missing)"
if [[ -n "$LEFT" ]]; then
  log "still missing from $LEFT"
  notify '구글 광고 대시보드' "CSV 수집 실패: $LEFT 부터 빠져 있음"
fi
log 'done'
