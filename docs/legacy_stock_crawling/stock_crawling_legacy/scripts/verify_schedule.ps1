<#
.SYNOPSIS
    Verify registered StockCrawling_* scheduled tasks.

.NOTES
    AC-2: query tasks with Get-ScheduledTask -TaskName "StockCrawling_*".
#>

Write-Host "=== StockCrawling scheduled task status ==="

$tasks = @(Get-ScheduledTask -TaskName "StockCrawling_*" -ErrorAction SilentlyContinue)

if ($tasks.Count -eq 0) {
    Write-Host "[NOT REGISTERED] No StockCrawling_* tasks found."
    Write-Host "Install: .\install_schedule.ps1"
    return
}

foreach ($task in $tasks) {
    $name = $task.TaskName
    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
    $nextRun = if ($info) { $info.NextRunTime } else { "unknown" }
    $lastRun = if ($info) { $info.LastRunTime } else { "none" }
    $lastResult = if ($info) { $info.LastTaskResult } else { "-" }
    Write-Host "[$name] registered"
    Write-Host "  State      : $($task.State)"
    Write-Host "  Next run   : $nextRun"
    Write-Host "  Last run   : $lastRun"
    Write-Host "  Last result: $lastResult (0=success)"
    Write-Host ""
}
