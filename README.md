# 🚗 Facebook Marketplace Vehicle Search Intelligence Bot

A production-grade Python application for 24/7 automated monitoring of Facebook Marketplace vehicle listings. Specifically engineered to discover **damaged vehicles, cars with blown engines, non-running projects, salvage titles, and repairable mechanic specials** before others find them, sending instant real-time alerts to **Telegram**.

---

## 📑 Table of Contents

1. [Features & Capabilities](#features)
2. [System Requirements](#system-requirements)
3. [Installation Guide](#installation-guide)
4. [How to Run the Bot](#how-to-run)
5. [Quick-Start Tutorial (Step-by-Step)](#quick-start)
   - [Step 1: Sign in to Facebook Profile](#step-1-login)
   - [Step 2: Configure Telegram Alerts](#step-2-telegram)
   - [Step 3: Activate Vehicle Search Presets](#step-3-presets)
   - [Step 4: View Results & Receive Alerts](#step-4-monitoring)
6. [Dashboard UI Control Guide](#dashboard-ui)
7. [Testing & Verification](#testing)
8. [24/7 Windows RDP / VPS Deployment](#deployment)
9. [Configuration & Customization (.env)](#configuration)
10. [Troubleshooting & FAQ](#troubleshooting)

---

<a id="features"></a>
## 🌟 Features & Capabilities

- **🖥️ Easy & Modern Web Dashboard:** Sleek, responsive dark-glass UI with 8 dedicated control panels. No command-line commands required for daily operation.
- **👥 Multi-Account Chrome Profile Manager:** Each account gets its own isolated, persistent Chrome profile on disk (`data/browser_profiles/`).
- **🛡️ Secure Manual Login Flow:** Zero automated password entry or CAPTCHA bypass hacks. Operators click **Open Browser / Login**, log in manually in visible Chrome, and click **Confirm Login / Continue**.
- **🔒 Dual-Layer Profile Locking:** File locks and in-process locks strictly ensure that duplicate Chrome processes never corrupt a browser profile.
- **🧠 Auto Select Eligibility Engine:** Transparently picks the healthiest available account based on session readiness and rate-limit safety.
- **🎯 Precision Vehicle Condition Presets:**
  - **Damaged Cars** (*accident, front end, rear damage, dent, collision, body work*)
  - **Blown Engine & Non-Running** (*blown engine, knock, bad motor, seized, won't start, crank no start, head gasket*)
  - **Mechanic Special & Repairable** (*mechanic special, project, needs work, fixable, handyman, as-is*)
  - **Salvage Titles** (*salvage, rebuilt, certificates of destruction, flood, total loss*)
  - **Parts / Scrap Cars** (*for parts, part out, parting out, donor, scrap*)
- **🔍 Multi-Level Filtering:** Combines Marketplace search queries with application-level keyword inclusion/exclusion, radius limits, and min/max prices.
- **✈️ Instant Telegram Alerts:** Formatted vehicle cards with photos, prices, mileage, location, match reasons, and direct links sent instantly via Telegram Bot API (tokens stored Fernet-encrypted at rest).
- **🔄 Hot Backups & Resilience:** Live SQLite hot backups in WAL mode without pausing background search workers.

---

<a id="system-requirements"></a>
## 💻 System Requirements

- **Operating System:** Windows 10, Windows 11, or Windows Server 2016/2019/2022 (RDP/VPS compatible).
- **Python:** Python 3.10, 3.11, 3.12, or 3.13 installed and added to `PATH`.
- **Browser:** Google Chrome (standard installation).
- **Internet Connection:** Stable broadband or VPS network connection.

---

<a id="installation-guide"></a>
## 📦 Installation Guide

### Option A: Automatic 1-Click Setup (Recommended)

1. Open the project folder in Windows File Explorer:
   ```text
   g:\Personal\fver\Facebook Marketplace Search Intelligence Bot
   ```
2. Double-click the launcher batch file:
   👉 **`Start_Dashboard.bat`**

   *If `.venv` does not exist yet, the script automatically builds the virtual environment and installs all dependencies before launching the server!*

---

### Option B: Manual Setup via PowerShell

1. Open Windows PowerShell in the project directory:
   ```powershell
   cd "g:\Personal\fver\Facebook Marketplace Search Intelligence Bot"
   ```

2. Run the automated environment setup script:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "scripts\setup_venv.ps1"
   ```

3. Initialize the database and default admin user:
   ```powershell
   .\.venv\Scripts\python.exe scripts\init_db.py
   .\.venv\Scripts\python.exe scripts\create_user.py admin admin123
   ```

---

<a id="how-to-run"></a>
## 🚀 How to Run the Bot

### 1. Start the Server

#### Method 1: Double-Click Batch File (Easiest)
Double-click:
👉 **`Start_Dashboard.bat`**
- Automatically starts the Waitress production server at `http://127.0.0.1:8080`.
- Automatically opens your default web browser directly to the dashboard.

#### Method 2: From PowerShell
```powershell
.\.venv\Scripts\python.exe run.py
```

#### Method 3: 24/7 Auto-Restart Watchdog (For Servers/VPS)
```powershell
powershell -ExecutionPolicy Bypass -File "scripts\start_bot.ps1"
```

---

### 2. Log in to the Web Dashboard

Open your web browser and navigate to:
👉 **[http://127.0.0.1:8080](http://127.0.0.1:8080)**

Default login credentials:
- **Username:** `admin`
- **Password:** `admin123`

*(You can change your password anytime under **Application Settings** or via `.\.venv\Scripts\python.exe scripts\create_user.py admin YourNewPassword`)*

---

<a id="quick-start"></a>
## 📖 Quick-Start Tutorial (Step-by-Step)

Follow these 4 simple steps to have the bot monitoring and alerting you within 5 minutes:

<a id="step-1-login"></a>
### Step 1: Connect & Sign in to your Facebook Profile
1. In the left sidebar, click **👥 Account Manager**.
2. Click **+ Add Account**:
   - Enter a friendly **Display Name** (e.g. `My Main FB` or `Account 1`).
   - Click **Create Account**.
3. In the accounts table, locate your account and click **Open Browser / Login**.
4. A dedicated Chrome browser window will open on your desktop.
5. In the Chrome window, log in to Facebook manually (and complete two-factor authentication or any security prompts if requested).
6. Switch back to your dashboard and click **✓ Confirm Login / Continue**.
7. The badge will immediately update to green **Session Ready**!

---

<a id="step-2-telegram"></a>
### Step 2: Configure Telegram Push Notifications
1. In the sidebar, click **✈️ Telegram Settings**.
2. Check the box **Enable Telegram Push Notifications**.
3. Verify your **Bot Token** and **Chat ID**:
   - Your configured Bot Token: `8959712373:AA...` *(already stored Fernet-encrypted at rest)*.
   - Your destination Chat ID: `7809021498`.
4. Click **🔔 Send Test Notification**.
5. Check your Telegram app—you will receive an instant test card!
6. Click **Save Telegram Settings**.

---

<a id="step-3-presets"></a>
### Step 3: Load or Create Vehicle Search Presets
1. In the sidebar, click **🔍 Search Manager**.
2. To load pre-configured searches instantly, click:
   👉 **⚡ Load Default Presets**
   This populates:
   - **Damaged Cars Under $3,000** (Query: `damaged car`, Price: $100–$3,000, 10 min interval)
   - **Blown Engine & Non-Running** (Query: `blown engine`, Price: $100–$2,500, 10 min interval)
   - **Mechanic Special & Repairable** (Query: `mechanic special`, Price: $100–$3,500, 10 min interval)
3. You can also click **+ Create New Search** to define custom filters (e.g., *Honda Civic Salvage*, *Ford F-150 Bad Transmission*, location radius, and include/exclude terms).

---

<a id="step-4-monitoring"></a>
### Step 4: View Live Leads & Receive Telegram Alerts
1. In **Search Manager**, click **▶ Run** on any search to trigger a test cycle immediately.
2. In the sidebar, click **📡 Live Monitoring** to watch the background cycle execute in real time:
   - See the account selected, total listings parsed, and matching vehicles identified.
3. In the sidebar, click **🚙 Matched Listings**:
   - Browse vehicle cards with thumbnails, prices, mileage, location, and match reasoning.
   - Click **Open FB ↗** to open any vehicle directly on Facebook Marketplace.
4. Newly discovered matching vehicles are simultaneously dispatched to your Telegram chat!

---

<a id="dashboard-ui"></a>
## 🎛️ Dashboard UI Control Guide

The dashboard is structured into 8 intuitive sections accessible from the sidebar:

| Section | Key Controls & What It Does |
| :--- | :--- |
| **📊 Overview** | Live high-level status of the entire bot: total accounts ready, active searches, listings discovered today, Telegram status, and recent execution cards. |
| **👥 Account Manager** | Add Facebook accounts, launch Chrome with isolated persistent profiles, confirm manual logins, check profile lock status, and batch update with **💾 Save Accounts**. |
| **🔍 Search Manager** | Create, edit, pause (`⏸`), resume (`⏵`), duplicate (`📋`), delete (`🗑️`), or trigger immediate runs (`▶ Run`) for any vehicle monitoring rule. |
| **📡 Live Monitoring** | Real-time audit log of monitoring runs. Displays start times, account utilized, cars scraped, new leads discovered, and exact execution status. |
| **🚙 Matched Listings** | Visual leads gallery. Filter by search query or keyword, review match reasons (e.g. *blown engine*, *repairable*), view prices, and click **Open FB ↗**. |
| **✈️ Telegram Settings** | Enable/disable alerts, set bot tokens and destination chat IDs, toggle link previews, enable silent delivery, and test notifications. |
| **📜 Activity Logs** | Color-coded audit trail of application events, background scheduler cycles, and access warnings. Automatically redacts all sensitive credentials and tokens. |
| **⚙️ Application Settings** | Adjust minimum cycle intervals (down to 1 min), configure page request delays, manage web dashboard credentials, and download hot SQLite database backups. |

---

<a id="testing"></a>
## 🧪 Testing & Verification

### 1. Automated Test Suite (16/16 Unit Tests)
Run all unit tests using the 1-click batch script:
👉 **`Run_Tests.bat`**

Or in PowerShell:
```powershell
.\.venv\Scripts\pytest.exe -v
```

**Test Coverage Summary:**
- `test_dedup.py`: Stable Facebook item ID parsing and fallback SHA-256 fingerprint deduplication.
- `test_filtering.py`: Price extraction and keyword inclusion/exclusion matching.
- `test_extractor.py`: HTML DOM parsing against live Facebook Marketplace structure.
- `test_account_selector.py`: Multi-account health scoring, quota enforcement, and specific account routing.
- `test_page_state.py`: Detection of Facebook login challenges, checkpoints, and rate-limiting pages.
- `test_login_session.py`: Profile state transitions and manual login confirmation workflow.

---

<a id="deployment"></a>
## 🖥️ 24/7 Windows RDP / VPS Deployment

When running on a Windows VPS or Remote Desktop (RDP), Chrome automation requires an active interactive GUI desktop. If you close your Remote Desktop connection normally, Windows disconnects the GUI session, which can suspend browser rendering.

### 1. Disconnect RDP Without Suspending the GUI Desktop
Whenever disconnecting from your RDP session, do not click the 'X' button. Instead, open PowerShell or Command Prompt as Administrator and run:

```cmd
for /f "skip=1 tokens=3" %s in ('query user %USERNAME%') do tscon %s /dest:console
```

*This redirects your RDP session back to the local console, keeping Chrome running seamlessly in the background.*

---

### 2. Auto-Start on Windows Boot (Task Scheduler)
To ensure the bot automatically starts whenever the Windows server boots or reboots:

1. Open PowerShell as Administrator.
2. Run the provided task installer:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "scripts\install_startup_task.ps1"
   ```
3. This registers a scheduled task (`MarketplaceBot`) set to run at user logon with highest privileges.

---

<a id="configuration"></a>
## ⚙️ Configuration & Customization

The bot loads default environment variables from `.env`. You can customize them directly or edit them within the web dashboard under **Application Settings**:

```ini
# Application Server
FMBOT_HOST=127.0.0.1
FMBOT_PORT=8080
FMBOT_DEBUG=False

# Database
FMBOT_DATABASE_URL=sqlite:///data/app.db

# Storage Directories
FMBOT_PROFILES_DIR=data/browser_profiles
FMBOT_LOGS_DIR=logs
FMBOT_BACKUPS_DIR=backups

# Scheduler Defaults
FMBOT_DEFAULT_INTERVAL_MINUTES=10
FMBOT_MIN_INTERVAL_MINUTES=1

# Telegram Credentials (Stored encrypted in SQLite; .env serves as initial fallback)
FMBOT_TELEGRAM_BOT_TOKEN=8959712373:AAFPQhyIJaCYm2bn7zGi7oi5aV8XQfr8cqI
FMBOT_TELEGRAM_CHAT_ID=7809021498
```

---

<a id="troubleshooting"></a>
## ❓ Troubleshooting & FAQ

### 1. "Chrome failed to start" or "Profile is locked"
- **Cause:** Another Chrome process is already using that account's profile directory.
- **Solution:** 
  1. Check **Account Manager** in the dashboard to see if a browser session is marked as **Browser Open**.
  2. If Chrome was closed unexpectedly, open Task Manager and ensure no orphaned `chrome.exe` processes remain, or wait 15 seconds for the file lock to release automatically.

### 2. Facebook Displays a Checkpoint or CAPTCHA
- **Design Philosophy:** The bot intentionally **never** attempts automated bypass hacks or credential stuffing.
- **Solution:** 
  1. The bot automatically pauses that account and marks it as **Needs Attention**.
  2. Open **Account Manager**, click **Open Browser / Login**, resolve the checkpoint manually in the visible Chrome window, and click **Confirm Login / Continue**.

### 3. How do I change the monitoring frequency?
- Go to **Search Manager** -> click **✏️ Edit** on any search -> update the **Monitoring Interval (Minutes)** field -> click **Update Search Configuration**.
- If you want intervals shorter than 10 minutes (down to 1 minute), adjust **Minimum Polling Interval** in **Application Settings** first.

### 4. How do I backup my discovered listings and settings?
- Go to **Application Settings** and click **Create Hot Backup Now**.
- Backups are timestamped and stored safely in the `backups/` directory without interrupting live background searches.

---

## 🔒 Security & Privacy Notice

- **No Passwords Stored:** The bot never asks for, records, or stores your Facebook password.
- **Encrypted Secrets:** Telegram Bot Tokens are encrypted at rest using AES-128-CBC / HMAC (Fernet).
- **Log Redaction:** All bot tokens, chat IDs, cookies, and session strings are automatically filtered and redacted from all console and rotating file logs (`logs/fmbot.log`).

---

**Developed for Facebook Marketplace Search Intelligence.**  
*Happy vehicle hunting!* 🚗💨