<#
.SYNOPSIS
  Creates an immediate hot database & configuration backup.
#>
$ErrorActionPreference = "Stop"

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

.\.venv\Scripts\python.exe -c "from app.config import Config; from app.services.backup_service import create_backup; p = create_backup(Config()); print(f'Backup archive created at: {p}')"
