# 메타 광고 관리자 CSV(어제, 광고·광고 세트) 받기 → data\csv\날짜\ 로 옮기기 → 대시보드 갱신
# 크롬 수집이 실패해도 GA4 수집과 대시보드 갱신은 진행한다.
$ErrorActionPreference = 'Continue'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $base 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$log = Join-Path $logDir "fetch-$stamp.log"
function Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Out-File $log -Append -Encoding utf8 }

# 수집이 멈췄으면 윈도우 알림을 띄운다 (스케줄러 결과는 실패해도 0이라 따로 알려야 한다)
function Notify($title, $text) {
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $n = New-Object System.Windows.Forms.NotifyIcon
  $n.Icon = [System.Drawing.SystemIcons]::Warning
  $n.Visible = $true
  $n.ShowBalloonTip(15000, $title, $text, 'Warning')
  Start-Sleep 16
  $n.Dispose()
}

$yesterday = (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
$downloads = Join-Path $env:USERPROFILE 'Downloads'
# 광고 계정 번호 등 회사 고유값은 config.json(구글 대시보드 폴더, 저장소에는 올리지 않음)에서 읽는다
$cfg = Get-Content (Join-Path $base '..\AdsDashboard\config.json') -Raw -Encoding utf8 | ConvertFrom-Json
$act = $cfg.meta.account_id
$campaignStart = $cfg.start_date
$filter = $cfg.campaign_filter
$start = Get-Date

# 1) 크롬이 꺼져 있으면 켠다 (Claude 확장이 붙을 시간을 준다)
$freeMb = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
Log "free=${freeMb}MB act=$act"
if (-not (Get-Process chrome -ErrorAction SilentlyContinue)) {
  Start-Process 'chrome.exe'
  Start-Sleep 20
}

# 2) claude CLI가 크롬(Claude 확장)으로 CSV만 받는다. 월요일엔 설정 내보내기도 받는다.
# 광고 관리자 URL의 date 끝 날짜는 포함되지 않아서, 어제까지 받으려면 끝을 오늘로 둔다.
$today = (Get-Date).ToString('yyyy-MM-dd')
$py = (Get-Command python).Source
# 지난 실행이 실패해 빠진 날이 있으면 그날부터 어제까지를 일별(time_breakdown=days_1)로 한 번에 받는다
$from = (& $py (Join-Path $base 'meta_dashboard.py') --missing | Out-String).Trim()
# 빠진 날이 없으면(오전에 이미 받았으면) 브라우저는 건너뛴다 → 하루 여러 번 돌려도 안전
$needFetch = [bool]$from
if (-not $from -or $from -ge $yesterday) { $from = $yesterday } else { Log "catch up from $from" }
$daily = "date=${from}_$today&insights_date=${from}_$today&time_breakdown=days_1"
$mgr = 'https://adsmanager.facebook.com/adsmanager/manage'
$settings = ''
if ((Get-Date).DayOfWeek -eq 'Monday') {
  $settings = "5) $mgr/campaigns?act=$act 에서 이름에 $filter 가 든 캠페인 체크 > 내보내기 > '대량 가져오기 형식으로 내보내기' > .csv"
}
$prompt = @"
크롬(Claude in Chrome 도구)으로만 작업한다. 새 탭 1개를 만들어 그 탭에서만 작업하고, 끝나면 그 탭을 닫는다.
읽기 전용: 저장/게시/수정, 게재 켜기·끄기, 열 변경 저장, 권장사항 적용 금지.
아래 주소를 차례로 열고, 계정이 '$($cfg.meta.account_name)'인지 확인한 뒤 표 위 내보내기(아래 화살표 아이콘) > '테이블 데이터 내보내기' > .csv 로 받는다. 표가 다 뜬 뒤 내보낸다.
1) $mgr/ads?act=$act&$daily
2) $mgr/adsets?act=$act&$daily
3) $mgr/ads?act=$act&date=${campaignStart}_$today&insights_date=${campaignStart}_$today
4) $mgr/adsets?act=$act&date=${campaignStart}_$today&insights_date=${campaignStart}_$today
$settings
로그인 화면이 나오면 아무것도 입력하지 말고 바로 멈춘 뒤 FAIL=LOGIN 이라고만 답한다.
크롬 확장이 연결되지 않았으면 FAIL=EXTENSION 이라고만 답한다.
보고(영어 표식만): 받은 표 번호를 OK=1,2,3,4 처럼, 실패는 FAIL=번호:이유.
"@
function Invoke-Chrome($f) {
  $job = Start-Job -ScriptBlock {
    param($f)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)  # 로그 한글 깨짐 방지
    Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue      # 다른 Claude 프로필이 잡혀 있으면 확장이 안 붙는다
    cmd /c "claude -p --chrome --model sonnet --allowedTools mcp__claude-in-chrome__* < `"$f`" 2>&1"
  } -ArgumentList $f
  if (Wait-Job $job -Timeout 1200) { $o = Receive-Job $job | Out-String } else { Stop-Job $job; $o = 'claude timeout (20m)' }
  Remove-Job $job -Force
  $o | Out-File $log -Append -Encoding utf8
  return $o
}
if ($needFetch) {
Log 'claude chrome start'
# PowerShell 파이프로 넘기면 한글이 '?'로 깨진다(11-18·11-20 실패) → UTF-8 파일로 쓰고 cmd 리디렉션으로 바이트 그대로 넘긴다
$promptFile = Join-Path $logDir "prompt-$stamp.txt"
[IO.File]::WriteAllText($promptFile, $prompt, [System.Text.UTF8Encoding]::new($false))
# 11-13~24 매일 FAIL=EXTENSION: 크롬을 막 켰을 때 확장이 늦게 붙는다 → 1분 간격 3번 시도
for ($try = 1; $try -le 3; $try++) {
  $out = Invoke-Chrome $promptFile
  if ($out -notmatch 'FAIL=EXTENSION') { break }
  Log "chrome extension not connected (try $try)"
  Start-Sleep 60
}
Remove-Item $promptFile -ErrorAction SilentlyContinue
# 그래도 확장이 안 붙으면 Aside 브라우저로 같은 표를 받는다 (Aside에 페이스북 로그인이 돼 있어야 함)
if ($out -match 'FAIL=EXTENSION') {
  Log 'fallback: aside'
  $aside = Join-Path $env:LOCALAPPDATA 'Aside\CLI\current\aside.exe'
  $ap = $prompt -replace '크롬\(Claude in Chrome 도구\)으로만 작업한다\. 새 탭 1개를 만들어 그 탭에서만 작업하고, 끝나면 그 탭을 닫는다\.', 'READ-ONLY. 탭 1개만 사용, 하위 에이전트 금지, 끝나면 탭을 닫는다. 파일은 Downloads 폴더에 저장.'
  $ap = $ap -replace '(?m)^크롬 확장이 연결되지 않았으면.*$', ''
  $job = Start-Job -ScriptBlock { param($exe, $p) & $exe exec --effort low -s fast $p 2>&1 } -ArgumentList $aside, $ap
  if (Wait-Job $job -Timeout 1200) { Receive-Job $job | Out-String | Out-File $log -Append -Encoding utf8 } else { Stop-Job $job; Log 'aside timeout (20m)' }
  Remove-Job $job -Force
}

# 3) 이번에 받은 메타 CSV를 날짜 폴더로 옮긴다 (설정 내보내기는 data\settings\)
$dest = Join-Path $base "data\csv\$yesterday"
New-Item -ItemType Directory -Force $dest, (Join-Path $base 'data\settings') | Out-Null
$files = Get-ChildItem $downloads -File | Where-Object { $_.LastWriteTime -ge $start -and $_.Extension -in '.csv', '.xlsx' }
foreach ($f in $files) {
  # 설정 내보내기는 UTF-16(BOM) 탭 구분, 보고서는 UTF-8(BOM). BOM이 있어 인코딩을 지정하지 않아도 읽힌다.
  $head = Get-Content $f.FullName -TotalCount 1 -ErrorAction SilentlyContinue
  if ($head -match 'Campaign ID') {
    Move-Item $f.FullName (Join-Path $base "data\settings\bulk_$yesterday$($f.Extension)") -Force
    Log "settings $($f.Name)"
  } elseif ($head -match '\((USD|KRW)\)') {
    Move-Item $f.FullName (Join-Path $dest ($f.Name -replace ' \(\d+\)', '')) -Force  # 같은 표를 두 번 받으면 하나로
    Log "moved $($f.Name)"
  }
}
if (-not $files) { Log 'no csv downloaded' }
} else { Log 'nothing missing, skip browser' }

# 4) 설정 표 → 대시보드(GA4 포함)
& $py (Join-Path $base 'read_settings.py') 2>&1 | Out-File $log -Append -Encoding utf8
& $py (Join-Path $base 'meta_dashboard.py') 2>&1 | Out-File $log -Append -Encoding utf8
$left = (& $py (Join-Path $base 'meta_dashboard.py') --missing | Out-String).Trim()
if ($left) { Log "still missing from $left"; Notify '메타 광고 대시보드' "CSV 수집 실패: $left 부터 빠져 있음. 로그 $log" }
Log 'done'
