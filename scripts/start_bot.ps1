<#
.SYNOPSIS
  Windows launch script with auto-recovery loop for 24/7 RDP/VPS operation.
#>
$ErrorActionPreference = "Continue"

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

Write-Host "Starting Marketplace Vehicle Search Intelligence Bot..." -ForegroundColor Cyan

# Loop ensures automatic restart if Waitress encounters an unexpected error
while ($true) {
    if (Test-Path ".venv\Scripts\python.exe") {
        Write-Host "Launching Waitress WSGI server..." -ForegroundColor Green
        & ".\.venv\Scripts\python.exe" "run.py"
    } else {
        Write-Error ".venv not found. Please run scripts\setup_venv.ps1 first."
        break
    }

    $exitCode = $LASTEXITCODE
    Write-Warning "Bot process stopped with exit code $exitCode."
    
    if ($exitCode -eq 0) {
        Write-Host "Clean exit requested. Stopping monitor."
        break
    }

    Write-Host "Restarting process in 10 seconds (Press Ctrl+C to abort)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
