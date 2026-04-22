<#
.SYNOPSIS
    StockCrawling KR/US 자동 실행 태스크를 Windows Task Scheduler에 등록한다.

.NOTES
    관리자 권한(Run as Administrator)으로 실행해야 합니다.
    공휴일에도 실행됩니다 — 한국/미국 영업일 캘린더 연동 없음.
#>

param(
    [switch]$Force  # 기존 태스크 강제 덮어쓰기
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir   = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$PythonExe    = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}
$LogRoot      = Join-Path $ProjectDir "logs"
$LogDir       = Join-Path $LogRoot "crawling"

# 로그 디렉토리 생성
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "[설정] 로그 디렉토리 생성: $LogDir"
}

function Register-StockTask {
    param(
        [string]$TaskName,
        [string]$TriggerTime,
        [string]$Mode
    )

    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing -and -not $Force) {
        Write-Warning "태스크 '$TaskName' 이(가) 이미 등록되어 있습니다."
        Write-Warning "-Force 옵션을 추가하면 덮어씁니다: .\install_schedule.ps1 -Force"
        return
    }

    if ($existing -and $Force) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[설정] 기존 태스크 '$TaskName' 제거 완료"
    }

    # 로그 파일명에 실행 시점 날짜 동적 포함 — PowerShell이 직접 날짜를 계산
    $InnerCmd = "Set-Location '$ProjectDir'; " +
        "New-Item -ItemType Directory -Force -Path '$LogDir' | Out-Null; " +
        '$d = Get-Date -Format yyyyMMdd; ' +
        "& `"$PythonExe`" -m src.crawling.run_daily --mode $Mode *> `"$LogDir\run_daily_${Mode}_`$d.log`""

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -NoProfile -Command `"$InnerCmd`"" `
        -WorkingDirectory $ProjectDir

    $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime

    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "주식 쉐도잉 파이프라인 자동 실행 — $TriggerTime KST" | Out-Null

    Write-Host "[완료] '$TaskName' 등록 성공 (실행 시각: $TriggerTime KST)"
}

Write-Host "=== StockCrawling Task Scheduler 등록 ==="
Register-StockTask -TaskName "StockCrawling_KR_Daily" -TriggerTime "15:40" -Mode "kr"
Register-StockTask -TaskName "StockCrawling_US_Daily" -TriggerTime "06:10" -Mode "us"
Write-Host ""
Write-Host "등록 확인: .\verify_schedule.ps1"
