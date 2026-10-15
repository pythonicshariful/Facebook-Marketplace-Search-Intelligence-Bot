# Facebook Marketplace Vehicle Search Intelligence Bot

A production-oriented Python application for monitoring Facebook Marketplace vehicle listings, specifically designed for finding **damaged vehicles, vehicles with blown engines, non-running cars, salvage titles, and repairable vehicles**.

---

## Features

- **Responsive Web Dashboard:** Modern dark theme interface featuring 8 specialized sections:
  1. **Overview:** Real-time statistics, discovered vehicle counts, today's listings, and job statuses.
  2. **Multi-Account Manager:** Independent persistent Chrome browser profiles (`data/browser_profiles/`), one-click visible manual login, session verification, lock protection, and prominent **Save Accounts** validation.
  3. **Search Manager:** Flexible vehicle monitoring rules with make/model, price limits, radius, include/exclude keywords, damage/condition presets, and account assignment.
  4. **Live Monitoring:** Real-time inspectability of background tasks, open Chrome sessions, and search execution cycles.
  5. **Matched Listings:** Clean searchable vehicle cards and tables with thumbnails, price badges, match reasons, and Facebook direct links.
  6. **Telegram Settings:** Instant push notifications with Telegram Bot API, secure Fernet token encryption at rest, and live test notification trigger.
  7. **Activity Logs:** Audit logs with redaction of sensitive credentials, log level/category filters, and raw log file downloads.
  8. **Application Settings:** Configurable minimum polling intervals, browser timeouts, concurrency limits, and hot SQLite backups.
- **Intelligent Account Selection (Auto Select):** Transparent eligibility scoring engine based on account health, session readiness, and daily load balancing. Never rotates to evade security challenges.
- **Strict Profile Locking:** Two-tier file and in-process locks preventing concurrent Chrome instances from corrupting profiles.
- **Zero-Evasion & Security First:** No credential harvesting or scraping hacks. When a checkpoint or CAPTCHA appears, the bot pauses and invites the operator to resolve it manually in the visible browser window.
- **Reliable Windows Operation:** Built for Windows RDP/VPS deployment with auto-recovery loops, hot SQLite WAL backups, and logon task scheduling.

---

## Quickstart

### 1. Installation
In PowerShell:
```powershell
.\scripts\setup_venv.ps1
```

### 2. Run the Bot
```powershell
.\scripts\start_bot.ps1
```

Visit the dashboard in your browser:
**`http://127.0.0.1:8080`**

- **Default user:** `admin`
- **Default password:** `admin123`

*(Change passwords anytime via `.\.venv\Scripts\python.exe scripts\create_user.py admin NewPassword`)*

---

## Running the Automated Test Suite

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## Documentation

- [Deployment Guide (Windows RDP / 24/7 VPS)](docs/DEPLOYMENT.md)
- [Selectors & Site Update Guide](docs/SELECTORS.md)
- [Troubleshooting & Recovery](docs/TROUBLESHOOTING.md)
- [Platform Constraints & Limitations](docs/LIMITATIONS.md)
