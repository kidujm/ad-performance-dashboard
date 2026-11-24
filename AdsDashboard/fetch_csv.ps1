# 구글 애즈 CSV(어제 기준) 받기 → data\csv\날짜\ 로 옮기기 → 대시보드 갱신
# Aside가 실패해도 GA4 수집과 대시보드 갱신은 진행한다.
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
$aside = Join-Path $env:LOCALAPPDATA 'Aside\CLI\current\aside.exe'
$asideApp = 'C:\Program Files\Aside\Application\Aside.exe'
$start = Get-Date
# 계정 주소 등 회사 고유값은 config.json에서 읽는다 (저장소에는 올리지 않는 파일)
$cfg = Get-Content (Join-Path $base 'config.json') -Raw -Encoding utf8 | ConvertFrom-Json
$py = (Get-Command python).Source

# 지난 실행이 실패해 빠진 날이 있으면 그날부터 어제까지 일별로 한 번에 받는다
$from = (& $py (Join-Path $base 'ads_dashboard.py') --missing | Out-String).Trim()
# 빠진 날이 없으면(오전에 이미 받았으면) 브라우저는 건너뛰고 GA4·대시보드만 갱신한다 → 하루 여러 번 돌려도 안전
$needFetch = [bool]$from
if ($from -and $from -lt $yesterday) {
  # 구글 애즈는 기간이 14일을 넘으면 '일' 세그먼트가 꺼져 합계만 받아진다(11-24 사고) → 7일 단위로 나눠 받는다
  $chunks = @(); $d = [datetime]$from
  while ($d -le [datetime]$yesterday) {
    $e = $d.AddDays(6); if ($e -gt [datetime]$yesterday) { $e = [datetime]$yesterday }
    $chunks += "'$($d.ToString('yyyy-MM-dd')) ~ $($e.ToString('yyyy-MM-dd'))'"; $d = $e.AddDays(1)
  }
  $range = "기간을 맞춤 " + ($chunks -join ', ') + " 로 하나씩 바꿔 가며, 기간마다 표 위 세그먼트 > 시간 > '일'을 켠 상태로(표에 '일' 열이 생긴 것 확인)"
  Log "catch up from $from ($($chunks.Count) chunks)"
} else {
  $range = "기간은 '어제'로 맞춘 뒤"
}

# 1) 메모리 정리: Aside가 무거우면 껐다 켠다
if ($needFetch) {
$asideMb = [int]((Get-Process Aside -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
$freeMb = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
Log "free=${freeMb}MB aside=${asideMb}MB"
if ($asideMb -gt 3000) {
  Get-Process Aside -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
  Start-Sleep 8
  $asideMb = 0
}
if ($asideMb -eq 0) {
  Start-Process $asideApp
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep 3
    if ((& $aside session list 2>&1 | Out-String) -notmatch "isn't running") { break }
  }
}

# 2) Aside에 CSV 다운로드만 시킨다 (읽기 전용·가벼운 모드)
$prompt = @"
READ-ONLY. 탭 1개만 사용. 하위 에이전트 금지. 전체 스냅샷·스크린샷 금지, 버튼은 글자로 찾기.
저장/적용/게시/수정, 열 변경, 필터 저장, 권장사항 적용 금지.
$($cfg.google.ads_keywords_url)
보기는 '모든 캠페인', $range 아래 표를 각각 다운로드 > .csv (변경 내역은 세그먼트 없이):
1) 키워드 > 검색 키워드 표
2) 인사이트 및 보고서 > 검색어 표
3) 캠페인 > 광고 표
4) 변경 내역 표 (왼쪽 메뉴 검색창에 '변경 내역')
보고: 저장한 파일 경로와 실패 항목만 짧게.
"@
Log 'aside start'
for ($try = 1; $try -le 6; $try++) {
  $job = Start-Job -ScriptBlock { param($exe, $p) & $exe exec --effort low -s fast $p 2>&1 } -ArgumentList $aside, $prompt
  if (Wait-Job $job -Timeout 1200) { $out = Receive-Job $job | Out-String; $out | Out-File $log -Append -Encoding utf8 } else { Stop-Job $job; $out = ''; Log 'aside timeout (20m)' }
  Remove-Job $job -Force
  # 방금 켠 Aside는 브라우저 프로필이 붙을 때까지 시간이 걸린다
  if (($out -replace '\s', '') -notmatch 'notconnectedtothedaemon') { break }
  Log "aside profile not connected (try $try)"
  Start-Sleep 20
}

# 3) 이번에 받은 CSV를 검사해 기간 시작일 폴더로 옮긴다. 날짜 구분 없는 합계·차트 파일은 data\_rejected 로 뺀다
$since = ([DateTimeOffset]$start).ToUnixTimeSeconds()
& $py (Join-Path $base 'ads_dashboard.py') --ingest $since $yesterday 2>&1 | Out-File $log -Append -Encoding utf8
} else { Log 'nothing missing, skip browser' }

# 4) 새 설정 변경이 있으면 해설 노트 생성 (없으면 바로 끝남)
& $py (Join-Path $base 'insights.py') 2>&1 | Out-File $log -Append -Encoding utf8

# 5) GA4 수집 + 대시보드 갱신
& $py (Join-Path $base 'ads_dashboard.py') 2>&1 | Out-File $log -Append -Encoding utf8
$left = (& $py (Join-Path $base 'ads_dashboard.py') --missing | Out-String).Trim()
if ($left) { Log "still missing from $left"; Notify '구글 광고 대시보드' "CSV 수집 실패: $left 부터 빠져 있음. 로그 $log" }
Log 'done'
