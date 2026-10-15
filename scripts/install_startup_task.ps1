<#
.SYNOPSIS
  Installs a Windows Task Scheduler task to run start_bot.ps1 at user logon.
#>
$ErrorActionPreference = "Stop"

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskName = "FMBot_Marketplace_Intelligence"

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Minimized -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\start_bot.ps1`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 365) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Write-Host "Registering Scheduled Task '$TaskName' to start at user logon..." -ForegroundColor Cyan

# Unregister if already present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Runs Facebook Marketplace Vehicle Search Bot at Windows Logon"

Write-Host "Scheduled task successfully installed!" -ForegroundColor Green
Write-Host "The bot will start automatically when this Windows user logs on."
