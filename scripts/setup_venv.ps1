<#
.SYNOPSIS
  Sets up the Python 3.13 virtual environment, generates .env with secure keys, and installs dependencies.
#>
$ErrorActionPreference = "Stop"

Write-Host "=== Setting up Facebook Marketplace Intelligence Bot ===" -ForegroundColor Cyan

# 1. Check Python version
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $py) {
    Write-Error "Python is not found on PATH. Please install Python 3.12 or 3.13."
}

# 2. Create virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Yellow
    py -3.13 -m venv .venv
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

# 3. Upgrade pip and install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -q

# 4. Generate .env if missing
if (-not (Test-Path ".env")) {
    Write-Host "Generating .env configuration with secure keys..." -ForegroundColor Yellow
    $secretKey = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")
    $fernetKey = .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    
    $envContent = @"
SECRET_KEY=$secretKey
FMBOT_FERNET_KEY=$fernetKey
FMBOT_HOST=127.0.0.1
FMBOT_PORT=8080
FMBOT_LOG_LEVEL=INFO
FMBOT_SCHEDULER_ENABLED=true
FMBOT_SCHEDULER_TICK_SECONDS=15
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"@
    Set-Content -Path ".env" -Value $envContent -Encoding UTF8
    Write-Host "Generated new .env with randomized keys." -ForegroundColor Green
} else {
    Write-Host ".env already present." -ForegroundColor Green
}

# 5. Initialize database
Write-Host "Initialising database schema..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe scripts\init_db.py

Write-Host "`nSetup complete! You can start the bot using: .\scripts\start_bot.ps1" -ForegroundColor Green
