# Windows RDP / VPS 24/7 Deployment Guide

This guide details how to deploy and operate the **Facebook Marketplace Vehicle Search Intelligence Bot** on a Windows Computer, RDP, or VPS environment for reliable 24/7 monitoring.

---

## 1. Prerequisites

- **Windows 10/11 or Windows Server 2019/2022**
- **Python 3.12 or 3.13 (64-bit)**
- **Google Chrome** (Installed in default path: `C:\Program Files\Google\Chrome\Application\chrome.exe`)
- Standard administrative access.

---

## 2. Quick Setup

Open PowerShell as Administrator in the project directory:

```powershell
# 1. Run automated setup script
.\scripts\setup_venv.ps1

# 2. (Optional) Create custom admin user
.\.venv\Scripts\python.exe scripts\create_user.py myadmin MySecurePassword123 --role admin

# 3. Test launch
.\scripts\start_bot.ps1
```

Once running, navigate to:
**`http://127.0.0.1:8080`**

Log in with:
- **Username:** `admin` (or your custom user)
- **Password:** `admin123` (or your custom password)

---

## 3. Critical: Operating Browser Automation 24/7 on Windows RDP

### The "Session 0" Windows Service Limitation
Windows Services run in **Session 0**, which is isolated from the desktop GUI. If you run Chrome inside Session 0:
- You **cannot see Chrome windows** to log in manually.
- Chrome may encounter GPU/renderer hangs or fail to render Facebook authentication challenges.

### Recommended Solution: Scheduled Task at User Logon
The application provides `scripts/install_startup_task.ps1`. This registers a Windows Task Scheduler task that starts the bot automatically whenever the Windows user signs in.

```powershell
# Register the task
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup_task.ps1
```

### Keeping the GUI Active on RDP Disconnect
When you close a Windows Remote Desktop (RDP) window normally, Windows locks the desktop session. While headless Chrome can often continue, interactive tasks and certain Chrome operations require an active GUI buffer.

To disconnect from RDP **without** locking the desktop session, create a batch shortcut on the desktop with this command:

```cmd
%windir%\System32\tscon.exe %sessionname% /dest:console
```

Right-click this batch file and select **Run as administrator**. It will disconnect your remote session while transferring the desktop to the physical console, keeping all Chrome windows and automation active!

### Enabling Windows Auto-Logon
To ensure the bot starts automatically after an unexpected server reboot:
1. Press `Win + R`, type `netplwiz`, and uncheck *"Users must enter a user name and password to use this computer"*.
2. Or use Microsoft Sysinternals **Autologon**:
   https://learn.microsoft.com/en-us/sysinternals/downloads/autologon

---

## 4. Production Security & Network Configuration

1. **Firewall & Binding:**
   - Keep `FMBOT_HOST=127.0.0.1` in `.env`.
   - Never expose port 8080 directly to the public internet without a reverse proxy and SSL certificate.

2. **Reverse Proxy (Optional):**
   - If accessing the dashboard remotely from outside the RDP, use **Caddy**, **Nginx**, or **Cloudflare Tunnel** with HTTPS and password protection.
   - Set `FMBOT_SECURE_COOKIES=true` in `.env` when serving over HTTPS.

---

## 5. Automated Backups

Run manual backups at any time:
```powershell
powershell -File .\scripts\backup.ps1
```
Backups are hot-copied from the active SQLite database in WAL mode and packaged into `.zip` archives under `data/backups/`.
