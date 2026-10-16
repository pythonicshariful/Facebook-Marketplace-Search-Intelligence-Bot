# 🚗 Facebook Marketplace Search Intelligence Bot

A production-grade Python application for 24/7 automated monitoring of Facebook Marketplace listings (Vehicles, Electronics, Parts, and Products). Specifically engineered to discover **targeted deals, damaged vehicles, blown engines, non-running projects, salvage titles, chargers, accessories, or any keyword-filtered product** the instant they appear, delivering real-time alerts to **Telegram** and tracking all product URLs with detailed inspection.

---

## 📑 Table of Contents

1. [🌟 Features & Capabilities](#features)
2. [💻 System Requirements](#system-requirements)
3. [🐍 Step 1: Installing Python 3.13 (With PATH)](#install-python)
4. [📦 Step 2: Installing the Bot Project](#install-bot)
5. [🐵 Step 3: Installing Tampermonkey & Granting All Permissions](#install-tampermonkey)
6. [🚀 Step 4: Running the Application & Logging In](#running-the-app)
7. [🎛️ Detailed Guide to Every Dashboard Section](#dashboard-sections)
   - [1. 📊 Overview Dashboard](#section-overview)
   - [2. 📡 Live Monitoring & Tampermonkey Agent](#section-monitoring)
   - [3. 🔍 Search Manager (Queries, Conditions, Filters & Re-evaluate)](#section-searches)
   - [4. 📦 Product Listings & Canonical URLs](#section-listings)
   - [5. ✈️ Telegram Push Notifications (Setup & BotFather)](#section-telegram)
   - [6. 👥 Account Manager (Selenium Mode)](#section-accounts)
   - [7. 📜 Activity Logs](#section-logs)
   - [8. ⚙️ Application Settings & Backups](#section-settings)
8. [🧪 Verification & Testing](#testing)
9. [🔧 Troubleshooting & FAQ](#troubleshooting)

---

<a id="features"></a>
## 🌟 Features & Capabilities

- **🧩 Tampermonkey Browser Agent (100% Human-Safe):** Runs natively inside your standard logged-in Google Chrome, Edge, or Brave browser. Eliminates CAPTCHAs, bot blocks, and Selenium crashes.
- **🔍 Full Product Detail Inspection:** Automatically visits and inspects product detail pages in the background to capture **seller descriptions, exact conditions (New/Used), and seller names** that are not visible on search cards alone.
- **🎯 Precision Vehicle & Keyword Condition Filters:**
  - **Damaged / Wrecked** (*accident, collision, body damage, front/rear damage*)
  - **Blown Engine & Non-Running** (*blown engine, rod knock, bad motor, seized, won't start, head gasket*)
  - **Mechanic Special & Repairable** (*mechanic special, project car, needs work, fixer upper, as-is*)
  - **Salvage / Rebuilt Titles** (*salvage, rebuilt title, branded title, total loss, parts car*)
  - **Custom Include & Exclude Keywords** (*e.g., "128GB", "unlocked", "clean title", "Charger", "OEM"*)
- **⚡ Instant 1-Click Re-evaluation:** Whenever you update search keywords, price limits, or conditions, the bot can instantly re-evaluate hundreds of collected products and update your matched leads without re-scraping.
- **✈️ Real-Time Telegram Alerts:** Rich HTML cards sent to your phone/desktop with thumbnail images, prices, locations, match explanations, and one-tap Facebook links.
- **📋 Complete Product URL Registry:** Stores every unique product URL discovered with a 1-click **Copy URL** box and direct **Open FB ↗** launcher.
- **🖥️ Dark-Glass Responsive Dashboard:** Zero command-line knowledge needed once launched. Everything is controlled via an intuitive web interface.

---

<a id="system-requirements"></a>
## 💻 System Requirements

- **Operating System:** Windows 10 / 11, Windows Server (2016/2019/2022 VPS/RDP), macOS, or Linux.
- **Python:** Python 3.10, 3.11, 3.12, or **Python 3.13** (Recommended).
- **Web Browser:** Google Chrome, Microsoft Edge, Brave, or Mozilla Firefox.
- **Browser Extension:** Tampermonkey (Free).

---

<a id="install-python"></a>
## 🐍 Step 1: Installing Python 3.13 (With PATH)

To ensure the bot can run from your terminal or launcher scripts, Python must be installed with environment variables configured.

### Windows Installation

1. Go to the official Python download page:
   👉 **[https://www.python.org/downloads/](https://www.python.org/downloads/)**
2. Click **Download Python 3.13.x**.
3. Run the downloaded installer (`python-3.13.x-amd64.exe`).
4. ⚠️ **CRITICAL STEP:** On the very first screen of the installer, check the box:
   ```text
   ☑ Add python.exe to PATH
   ```
   *(If you skip this, Windows will not recognize `python` commands).*
5. Click **Install Now**.
6. When installation finishes, open **Command Prompt** (`cmd`) or **PowerShell** and verify:
   ```bash
   python --version
   ```
   *Expected output:* `Python 3.13.x`

---

<a id="install-bot"></a>
## 📦 Step 2: Installing the Bot Project

### 1. Download or Clone the Repository
Clone the repository with Git:
```bash
git clone https://github.com/pythonicshariful/Facebook-Marketplace-Search-Intelligence-Bot.git
cd Facebook-Marketplace-Search-Intelligence-Bot
```
*(Or download the ZIP file from GitHub and extract it to a folder of your choice).*

### 2. Set Up Virtual Environment & Dependencies

Open PowerShell or Command Prompt inside the project directory:

#### On Windows (PowerShell):
```powershell
# Create a virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install required dependencies
pip install -r requirements.txt
```

#### On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Initialize the Database & Create Admin User

Run the initialization scripts:
```powershell
python scripts/init_db.py
python scripts/create_user.py admin admin123
```
- **Default Username:** `admin`
- **Default Password:** `admin123` *(you can change this in Application Settings)*

---

<a id="install-tampermonkey"></a>
## 🐵 Step 3: Installing Tampermonkey & Granting All Permissions

The Tampermonkey Agent automates Marketplace searches right inside your personal browser window with zero risk of CAPTCHAs or bot bans.

### 1. Install the Tampermonkey Extension

Install Tampermonkey from the official store for your browser:
- **Google Chrome:** [Chrome Web Store - Tampermonkey](https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
- **Microsoft Edge:** [Microsoft Edge Add-ons - Tampermonkey](https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd)
- **Brave Browser:** Install via the Chrome Web Store link above.
- **Mozilla Firefox:** [Firefox Add-ons - Tampermonkey](https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/)

---

### 2. Grant Tampermonkey All Necessary Permissions

To allow Tampermonkey to communicate with the local bot dashboard and execute on Facebook Marketplace without pop-up warnings, grant the following permissions:

#### A. Enable Developer Mode (Chrome / Edge / Brave)
1. In your browser address bar, open:
   ```text
   chrome://extensions/   (or edge://extensions/)
   ```
2. In the top-right corner, toggle **Developer mode** to **ON** (Enabled).
   *(This allows extensions to run advanced userscripts without restriction).*

#### B. Allow File Access (Optional but Recommended)
1. On the `chrome://extensions/` page, find **Tampermonkey** and click **Details**.
2. Scroll down and turn **ON** the switch:
   ```text
   ☑ Allow access to file URLs
   ```

#### C. Grant Network Access (`@connect`)
1. Click the **Tampermonkey icon** in your browser extensions toolbar and click **Dashboard**.
2. Click the **Settings** tab at the top.
3. Under **General**, set **Config mode** to **Advanced**.
4. Scroll down to **Security** / **XHR Security** and ensure **Allowed domains** allows:
   - `127.0.0.1`
   - `localhost`
   - `facebook.com`
   - `www.facebook.com`

---

### 3. Install the Bot UserScript

1. Start the bot server (see [Step 4](#running-the-app)).
2. Open your dashboard at **[http://127.0.0.1:8080](http://127.0.0.1:8080)** and log in.
3. Go to **📡 Live Monitoring** in the sidebar.
4. Click the **➕ Install Tampermonkey Agent UserScript** button.
5. Tampermonkey will open an installation tab displaying `Facebook Marketplace Intelligence Bot (Tampermonkey Agent) v2.5.0`.
6. Click **Install**.
7. Now open **[https://www.facebook.com/marketplace](https://www.facebook.com/marketplace)** in a browser tab.
8. You will see a dark floating HUD widget in the bottom-right corner:
   ```text
   Marketplace Bot Agent [agent_xxxx]
   🟢 Connected & Ready
   Waiting for dashboard commands...
   ```
*(Keep this Facebook tab open. The bot will automatically control it whenever background searches are due or triggered!)*

---

<a id="running-the-app"></a>
## 🚀 Step 4: Running the Application & Logging In

### Start the Server

#### Method A: Double-Click Batch File (Windows)
Double-click:
👉 **`Start_Dashboard.bat`**
- Starts the production Waitress server at `http://127.0.0.1:8080`.
- Automatically opens your default web browser to the login page.

#### Method B: From PowerShell / Command Prompt
```powershell
.\.venv\Scripts\python.exe run.py
```

### Accessing the Dashboard
- **URL:** **[http://127.0.0.1:8080](http://127.0.0.1:8080)**
- **Username:** `admin`
- **Password:** `admin123`

---

<a id="dashboard-sections"></a>
## 🎛️ Detailed Guide to Every Dashboard Section

```
┌────────────────────────────────────────────────────────┐
│                   DASHBOARD SIDEBAR                    │
├────────────────────────────────────────────────────────┤
│  📊 Overview Dashboard                                 │
│  📡 Live Monitoring (Tampermonkey Controller)          │
│  🔍 Search Manager (Queries & Rules)                   │
│  📦 Product Listings (All Leads & URLs)                │
│  ✈️ Telegram Settings (Push Alerts)                    │
│  👥 Account Manager (Selenium Profiles)                │
│  📜 Activity Logs (System Audit)                       │
│  ⚙️ Application Settings (Intervals & Backups)         │
└────────────────────────────────────────────────────────┘
```

---

<a id="section-overview"></a>
### 1. 📊 Overview Dashboard
The Overview provides a high-level summary of your intelligence system:
- **Total Accounts Ready**: Number of authenticated Facebook profiles.
- **Active Search Rules**: How many continuous searches are currently scheduled.
- **Listings Discovered Today**: Count of unique product URLs scraped in the last 24 hours.
- **Telegram Alert Status**: Indicates whether Telegram Bot API alerts are armed and enabled.
- **Recent Executions Feed**: Live cards showing the latest search runs, unique listings collected, match counts, and timestamps.

---

<a id="section-monitoring"></a>
### 2. 📡 Live Monitoring & Tampermonkey Agent
This section acts as the mission control for browser automation:
- **Active Browser Agents Table**: Shows all connected browser tabs running the script, their unique `agent_id`, status (e.g. `idle`, `busy`), and last heartbeat.
- **Live Progress Reporting**: When a search runs, you will see real-time steps:
  1. *Navigating directly to Marketplace search URL*
  2. *Refining location and radius filter*
  3. *Applying price minimum & maximum*
  4. *Scrolling feed to lazy-load listings*
  5. *Extracting listing cards from page*
  6. *Inspecting product details (1/15): [Product Title]...*
  7. *Submitting listings with all product info to dashboard*
- **Agent Actions**:
  - **Install Script Button**: Re-downloads the latest agent script.
  - **Kill Switch / Pause**: Temporarily pause all browser automation without stopping the server.

---

<a id="section-searches"></a>
### 3. 🔍 Search Manager
The Search Manager lets you configure what the bot looks for:

#### Creating a New Search (`+ Custom Search`)
- **Search Name**: A friendly label (e.g., `iPhone 15 Pro - Portland` or `Damaged Honda Civics`).
- **Search Term / Query**: The keyword typed into Marketplace (e.g., `iPhone 15 Pro`, `Honda Civic`, `BMW 3 Series`).
- **Location & Radius**: Target city (e.g., `Portland, OR`) and radius in miles/kilometers (e.g., `25 miles`).
- **Price Range**: Optional Minimum and Maximum price bounds (e.g., `$500 - $2,000`).
- **Vehicle Condition Filter**: Choose from built-in presets:
  - *Any Condition*
  - *Damaged / Wrecked*
  - *Blown / Bad Engine*
  - *Not Running*
  - *Salvage / Rebuilt Title*
  - *Repairable / Needs Work*
- **Keywords to Include**: Comma-separated list of words that **must appear** in the title, full description, condition, location, or URL (e.g., `unlocked, 128GB, Charger, clean title`).
- **Keywords to Exclude**: Comma-separated list of negative words (e.g., `broken screen, iCloud locked, parts only`). Listings with these words are filtered out automatically.
- **Interval (Minutes)**: How often the bot checks for new listings (e.g., every `10` minutes).
- **Notify Telegram**: Toggle on/off push notifications for this specific search.

#### Search Table Actions
- **👁 Products**: Jump straight to all product URLs collected for this specific search.
- **▶ Run**: Immediately queue this search to run in your browser agent right now.
- **⏸ / ⏵**: Pause or resume automated scheduled runs.
- **⚡ Re-check / Re-evaluate**: Re-runs the filtering engine on all existing listings in the database using your current criteria and dispatches Telegram alerts for newly matched products.
- **✏️ Edit**: Modify search criteria, keywords, or price limits.
- **📋 Duplicate**: Clone an existing search rule.
- **✕ Delete**: Soft-delete a search while keeping historical product data.

---

<a id="section-listings"></a>
### 4. 📦 Product Listings & Canonical URLs
This is your comprehensive database of scraped listings:
- **Filter Pills**:
  - **🌐 All Products (N)**: Displays every unique product card found by the bot.
  - **✅ Matched Criteria (N)**: Shows only the listings that passed all inclusion keywords, condition filters, and price ranges.
  - **📋 Unmatched / Filtered Out (N)**: Listings that were rejected (with clear explanations like `excluded keyword 'broken'` or `price below min $500`).
- **Detailed Product Card Information**:
  - **Photo**: High-resolution listing image.
  - **Price**: Extracted price badge.
  - **Title**: Clean listing title.
  - **Location**: City and neighborhood.
  - **Condition**: Inspected condition tag (*New*, *Used - Like New*, *Used - Good*).
  - **Seller Name**: Detected seller username.
  - **Full Description Snippet**: Captured seller description.
  - **Match Status Reason**: Exact explanation why the listing matched (e.g., `include keyword 'Charger' found; price $1,500 in range`).
- **Product URL Tools**:
  - **Copy Box**: Pre-selected, clean canonical URL (`https://www.facebook.com/marketplace/item/<id>/`) with a 1-click **Copy** button.
  - **Open FB ↗ Button**: Opens the listing directly in Facebook Marketplace in a new tab.

---

<a id="section-telegram"></a>
### 5. ✈️ Telegram Push Notifications
Receive real-time mobile and desktop alerts the instant a deal matches.

#### How to Set Up Telegram Alerts in 2 Minutes:
1. **Get a Bot Token from @BotFather**:
   - Open Telegram and search for `@BotFather`.
   - Send `/newbot`.
   - Choose a name and username (e.g., `MyMarketplaceAlertBot`).
   - Copy the HTTP API token (e.g., `1234567890:ABCdef...`).
2. **Get your Chat ID from @userinfobot**:
   - Search for `@userinfobot` on Telegram.
   - Send `/start`.
   - It will reply with your numeric **Id** (e.g., `1523086010`).
3. **Configure in Dashboard**:
   - Open the dashboard and click **✈️ Telegram Settings**.
   - Check **☑ Enable Telegram Push Notifications**.
   - Paste your **Bot Token** and **Chat ID**.
   - Click **Save Telegram Settings**.
4. **Test Delivery**:
   - Click **🔔 Send Test Notification**.
   - Check Telegram—you will receive an instant test confirmation message!

---

<a id="section-accounts"></a>
### 6. 👥 Account Manager (Selenium Mode)
*Note: If you use the default Tampermonkey Agent mode, you do not need to configure Selenium accounts.*
- If running in headless/Selenium mode (`FMBOT_SCRAPER_MODE=selenium`), you can manage multiple isolated Chrome browser profiles, complete manual 2FA logins, and automatically rotate profiles between search cycles.

---

<a id="section-logs"></a>
### 7. 📜 Activity Logs
- Real-time audit trail of all background operations.
- Displays search execution summaries, Tampermonkey heartbeats, Telegram delivery successes/failures, and scheduler ticks.
- Automatically redacts sensitive passwords and bot tokens from all logs.

---

<a id="section-settings"></a>
### 8. ⚙️ Application Settings & Backups
- **Scraper Mode**: Switch between `Tampermonkey` (Recommended) and `Selenium`.
- **Interval Boundaries**: Enforce minimum search frequencies.
- **Deduplication Scope**: Choose between `global` (never alert for the same car across any search) or `per_search` (alert if it matches a different search).
- **Admin Password**: Change web dashboard login credentials.
- **Hot SQLite Backups**: Download a live, point-in-time copy of `app.db` without stopping background workers.

---

<a id="testing"></a>
## 🧪 Verification & Testing

The repository includes a comprehensive automated test suite covering deduplication, HTML parsing, price parsing, and filter rules:

```powershell
# Run the test suite using pytest
.\.venv\Scripts\pytest.exe -v
```

---

<a id="troubleshooting"></a>
## 🔧 Troubleshooting & FAQ

### 1. Tampermonkey HUD says "Connecting..." or shows Network Error
- **Cause:** The dashboard server is not running or port 8080 is blocked.
- **Solution:** Verify the server is running (`python run.py`). Ensure `http://127.0.0.1:8080` loads in your browser. In Tampermonkey settings, make sure `127.0.0.1` is permitted in XHR / `@connect`.

### 2. Matched Criteria is 0 but Listings Were Scraped
- **Cause:** The search keywords, price limits, or condition filters did not match the scraped cards, or criteria were updated after the scraping cycle ran.
- **Solution:** Open **Search Manager**, verify your keywords (e.g. change vehicle condition to *Any* if searching for non-vehicles), and click the **⚡ Re-check** button. It will immediately re-evaluate all products against your updated criteria.

### 3. Telegram Notifications Are Not Received
- **Cause:** `Enable Telegram Push Notifications` is unchecked, or the search has `Notify Telegram` disabled.
- **Solution:**
  1. Open **✈️ Telegram Settings**, check **Enable Telegram Push Notifications**, and click **Send Test Notification**.
  2. Open **🔍 Search Manager**, click **Edit** on your search, and ensure **Notify Telegram** is checked.

### 4. Facebook Changes Layout / Infinite Redirect
- **Solution:** The bot includes canonical search navigation (`v2.5.0` Agent) that automatically handles Facebook's internal city-slug redirects and preserves search result queries.

---

## 📄 License
This project is for personal search intelligence and educational automation purposes. Ensure compliance with Facebook's terms of service and acceptable use policies.