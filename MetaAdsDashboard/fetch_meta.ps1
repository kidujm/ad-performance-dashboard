# 메타 광고 관리자 CSV(어제, 광고·광고 세트) 받기 → data\csv\날짜\ 로 옮기기 → 대시보드 갱신
# 크롬 수집이 실패해도 GA4 수집과 대시보드 갱신은 진행한다.
$ErrorActionPreference = 'Continue'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $base 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$log = Join-Path $logDir "fetch-$stamp.log"
function Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Out-File $log -Append -Encoding utf8 }

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
$mgr = 'https://adsmanager.facebook.com/adsmanager/manage'
$settings = ''
if ((Get-Date).DayOfWeek -eq 'Monday') {
  $settings = "5) $mgr/campaigns?act=$act 에서 이름에 $filter 가 든 캠페인 체크 > 내보내기 > '대량 가져오기 형식으로 내보내기' > .csv"
}
$prompt = @"
크롬(Claude in Chrome 도구)으로만 작업한다. 새 탭 1개를 만들어 그 탭에서만 작업하고, 끝나면 그 탭을 닫는다.
읽기 전용: 저장/게시/수정, 게재 켜기·끄기, 열 변경 저장, 권장사항 적용 금지.
아래 주소를 차례로 열고, 계정이 '$($cfg.meta.account_name)'인지 확인한 뒤 표 위 내보내기(아래 화살표 아이콘) > '테이블 데이터 내보내기' > .csv 로 받는다. 표가 다 뜬 뒤 내보낸다.
1) $mgr/ads?act=$act&date=${yesterday}_$today&insights_date=${yesterday}_$today
2) $mgr/adsets?act=$act&date=${yesterday}_$today&insights_date=${yesterday}_$today
3) $mgr/ads?act=$act&date=${campaignStart}_$today&insights_date=${campaignStart}_$today
4) $mgr/adsets?act=$act&date=${campaignStart}_$today&insights_date=${campaignStart}_$today
$settings
로그인 화면이 나오면 아무것도 입력하지 말고 바로 멈춘 뒤 FAIL=LOGIN 이라고만 답한다.
크롬 확장이 연결되지 않았으면 FAIL=EXTENSION 이라고만 답한다.
보고(영어 표식만): 받은 표 번호를 OK=1,2,3,4 처럼, 실패는 FAIL=번호:이유.
"@
Log 'claude chrome start'
$job = Start-Job -ScriptBlock {
  param($p)
  $p | & claude -p --chrome --model sonnet --allowedTools 'mcp__claude-in-chrome__*' 2>&1
} -ArgumentList $prompt
if (Wait-Job $job -Timeout 1200) { Receive-Job $job | Out-String | Out-File $log -Append -Encoding utf8 } else { Stop-Job $job; Log 'claude timeout (20m)' }
Remove-Job $job -Force

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

# 4) 설정 표 → 대시보드(GA4 포함)
$py = (Get-Command python).Source
& $py (Join-Path $base 'read_settings.py') 2>&1 | Out-File $log -Append -Encoding utf8
& $py (Join-Path $base 'meta_dashboard.py') 2>&1 | Out-File $log -Append -Encoding utf8
Log 'done'
