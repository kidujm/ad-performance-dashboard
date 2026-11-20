#!/bin/bash
# macOS용: 메타 광고 관리자 CSV 받기 → data/csv/날짜/ 로 옮기기 → 대시보드 갱신 (fetch_meta.ps1과 같은 순서)
# 크롬 수집이 실패해도 GA4 수집과 대시보드 갱신은 진행한다.
cd "$(dirname "$0")" || exit 1
mkdir -p logs data/settings
LOG="logs/fetch-$(date +%Y%m%d-%H%M).log"
log() { echo "$(date +%H:%M:%S) $*" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null; }

PY="$(command -v python3 || command -v python)"
YESTERDAY="$(date -v-1d +%Y-%m-%d)"
TODAY="$(date +%Y-%m-%d)"
DOWNLOADS="$HOME/Downloads"
STAMP="$(mktemp)"
# 광고 계정 번호 등 회사 고유값은 config.json(구글 대시보드 폴더, 저장소에는 올리지 않음)에서 읽는다
read -r ACT START FILTER < <("$PY" -c "
import sys; sys.path.insert(0, '../AdsDashboard'); import adkit
c = adkit.load_config(); print(c['meta']['account_id'], c['start_date'], c['campaign_filter'])")
ACCOUNT="$("$PY" -c "import sys; sys.path.insert(0, '../AdsDashboard'); import adkit; print(adkit.load_config()['meta']['account_name'])")"

# 지난 실행이 실패해 빠진 날이 있으면 그날부터 어제까지를 일별(time_breakdown=days_1)로 한 번에 받는다
FROM="$("$PY" meta_dashboard.py --missing)"
if [[ -z "$FROM" || ! "$FROM" < "$YESTERDAY" ]]; then FROM="$YESTERDAY"; else log "catch up from $FROM"; fi
# 광고 관리자 URL의 date 끝 날짜는 포함되지 않아서, 어제까지 받으려면 끝을 오늘로 둔다
DAILY="date=${FROM}_$TODAY&insights_date=${FROM}_$TODAY&time_breakdown=days_1"
TOTAL="date=${START}_$TODAY&insights_date=${START}_$TODAY"
MGR='https://adsmanager.facebook.com/adsmanager/manage'
SETTINGS=''
[[ "$(date +%u)" == 1 ]] && SETTINGS="5) $MGR/campaigns?act=$ACT 에서 이름에 $FILTER 가 든 캠페인 체크 > 내보내기 > '대량 가져오기 형식으로 내보내기' > .csv"

PROMPT="크롬(Claude in Chrome 도구)으로만 작업한다. 새 탭 1개를 만들어 그 탭에서만 작업하고, 끝나면 그 탭을 닫는다.
읽기 전용: 저장/게시/수정, 게재 켜기·끄기, 열 변경 저장, 권장사항 적용 금지.
아래 주소를 차례로 열고, 계정이 '$ACCOUNT'인지 확인한 뒤 표 위 내보내기(아래 화살표 아이콘) > '테이블 데이터 내보내기' > .csv 로 받는다. 표가 다 뜬 뒤 내보낸다.
1) $MGR/ads?act=$ACT&$DAILY
2) $MGR/adsets?act=$ACT&$DAILY
3) $MGR/ads?act=$ACT&$TOTAL
4) $MGR/adsets?act=$ACT&$TOTAL
$SETTINGS
로그인 화면이 나오면 아무것도 입력하지 말고 바로 멈춘 뒤 FAIL=LOGIN 이라고만 답한다.
크롬 확장이 연결되지 않았으면 FAIL=EXTENSION 이라고만 답한다.
보고(영어 표식만): 받은 표 번호를 OK=1,2,3,4 처럼, 실패는 FAIL=번호:이유."
log 'claude chrome start'
printf '%s' "$PROMPT" | claude -p --chrome --model sonnet --allowedTools 'mcp__claude-in-chrome__*' >> "$LOG" 2>&1

# 설정 내보내기(UTF-16, 'Campaign ID' 머리글)는 data/settings/, 보고서(통화 표시 머리글)는 날짜 폴더로
DEST="data/csv/$YESTERDAY"
mkdir -p "$DEST"
moved=0
while IFS= read -r -d '' f; do
  head="$(iconv -f UTF-16 -t UTF-8 "$f" 2>/dev/null | head -1)"
  [[ -z "$head" || "$head" != *"Campaign ID"* ]] && head="$(head -1 "$f")"
  if [[ "$head" == *"Campaign ID"* ]]; then
    ext="${f##*.}"; mv -f "$f" "data/settings/bulk_$YESTERDAY.$ext"; log "settings $(basename "$f")"; moved=1
  elif [[ "$head" =~ \((USD|KRW)\) ]]; then
    name="$(basename "$f" | sed -E 's/ \([0-9]+\)//')"
    mv -f "$f" "$DEST/$name"; log "moved $name"; moved=1
  fi
done < <(find "$DOWNLOADS" -maxdepth 1 \( -name '*.csv' -o -name '*.xlsx' \) -newer "$STAMP" -print0)
rm -f "$STAMP"
[[ $moved == 0 ]] && log 'no csv downloaded'

"$PY" read_settings.py >> "$LOG" 2>&1
"$PY" meta_dashboard.py >> "$LOG" 2>&1

LEFT="$("$PY" meta_dashboard.py --missing)"
if [[ -n "$LEFT" ]]; then
  log "still missing from $LEFT"
  notify '메타 광고 대시보드' "CSV 수집 실패: $LEFT 부터 빠져 있음"
fi
log 'done'
