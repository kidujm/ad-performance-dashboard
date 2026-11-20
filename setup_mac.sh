#!/bin/bash
# macOS 설치: 실행 권한을 주고, 매일 09:00(구글)·09:20(메타) 자동 수집을 launchd에 등록한다.
#   bash setup_mac.sh            등록
#   bash setup_mac.sh --remove   해제
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS"
chmod +x AdsDashboard/*.sh MetaAdsDashboard/*.sh AdsDashboard/*.command MetaAdsDashboard/*.command

job() {  # 이름, 스크립트, 시, 분
  local plist="$AGENTS/local.addashboard.$1.plist"
  launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
  [[ "$REMOVE" == 1 ]] && { echo "removed $1"; return; }
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.addashboard.$1</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>"$ROOT/$2"</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$3</integer><key>Minute</key><integer>$4</integer></dict>
  <key>StandardErrorPath</key><string>$ROOT/$(dirname "$2")/logs/launchd.err</string>
</dict></plist>
EOF
  mkdir -p "$ROOT/$(dirname "$2")/logs"
  launchctl load "$plist"
  echo "scheduled $1 at $(printf '%02d:%02d' "$3" "$4")"
}

REMOVE=0; [[ "$1" == "--remove" ]] && REMOVE=1
job google AdsDashboard/fetch_csv.sh 9 0
job meta MetaAdsDashboard/fetch_meta.sh 9 20
