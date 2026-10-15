# Platform Constraints & Known Limitations

1. **Facebook Detection & Access Challenges:**
   No browser automation tool can guarantee immunity from Facebook's security checks. This bot respects platform restrictions: when a checkpoint, CAPTCHA, or restriction appears, the search is **paused** and the account is flagged. The operator must resolve the challenge manually.

2. **Monitoring Intervals:**
   Do not configure extremely aggressive polling intervals (e.g. 30 seconds). The application defaults to a **10-minute minimum interval** (configurable in Application Settings) to operate reliably.

3. **URL Parameter Limitations:**
   Facebook does not support URL parameters for complex filters like "blown engine" or "salvage". These filters are applied **application-side** by the bot after extracting visible listing titles and descriptions.

4. **Multi-Process Profile Access:**
   Chrome prohibits two instances from accessing the same `--user-data-dir` simultaneously. The bot enforces strict two-layer file and thread locks.
