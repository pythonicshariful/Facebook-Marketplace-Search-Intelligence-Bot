# Troubleshooting & Recovery Procedures

### 1. "Profile is in use by another task" / Profile Lock Error
**Cause:** A Chrome window using the account's persistent profile directory is currently open.
**Resolution:**
- If you opened Chrome via **Open Browser / Login**, finish your manual login and click **Close** in the dashboard.
- If Chrome was opened externally or crashed, verify in Windows Task Manager that no stray `chrome.exe` processes are holding files in `data/browser_profiles/<account_id>/`.
- The bot stores file locks in `data/locks/`. Locks are automatically released when Chrome closes.

---

### 2. "Needs Attention: Security Checkpoint / CAPTCHA"
**Cause:** Facebook detected new access or unusual activity and presented an identity verification challenge.
**Resolution:**
- Go to **Account Manager**. The account will show **Needs Attention**.
- Click **Open Browser / Login**. Chrome will open with that profile.
- Complete the security verification manually (SMS code, email approval, or CAPTCHA).
- Once you see Marketplace accessible, click **Confirm Login**. The status will return to **Session Ready**, and searches will resume.

---

### 3. "Search Waiting for Account"
**Cause:** The search is assigned to a specific account that is currently disabled, busy, or needs attention.
**Behavior:** The bot will **never** silently move a search to another account to evade a restriction.
**Resolution:** Check the account's status in **Account Manager** and resolve any login requirement or reassign the search to another ready profile.

---

### 4. Chrome / ChromeDriver Version Mismatches
**Resolution:**
The application uses **Selenium Manager** (bundled in Selenium 4.27+). It automatically inspects your installed Google Chrome version and downloads the exact matching ChromeDriver in the background. You do not need to install or update ChromeDriver manually.
