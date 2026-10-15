# Marketplace Selectors & Update Guide

All website-specific selectors, URL parameters, and page classification markers are isolated in:
**`app/services/selectors.py`** and **`app/services/page_state.py`**

---

## 1. Verified Live Selectors & XPaths (Inspected via Live Browser)

| Field | Live CSS Selector | Live XPath Expression | Description |
|---|---|---|---|
| **Listing Card Link** | `a[href*="/marketplace/item/"]` | `//a[contains(@href, '/marketplace/item/')]` | Primary item link containing the numeric Facebook item ID |
| **Listing Image** | `a[href*="/marketplace/item/"] img` | `//a[contains(@href, '/marketplace/item/')]//img` | Vehicle thumbnail image (`src` and `alt`) |
| **Price Text** | `a[href*="/marketplace/item/"] span[dir="auto"]` | `//a[contains(@href, '/marketplace/item/')]//span[@dir='auto'][starts-with(normalize-space(text()), '$') or normalize-space(text())='FREE']` | Formatted price string (e.g. `$1,400`, `FREE`, `$2,000`) |
| **Title Text** | `a[href*="/marketplace/item/"] span[dir="auto"]` | `//a[contains(@href, '/marketplace/item/')]//span[@dir='auto'][not(starts-with(normalize-space(text()), '$'))]` | Vehicle year, make, model and summary line |
| **Location / City** | `a[href*="/marketplace/item/"] span.xsag5q8` | `//a[contains(@href, '/marketplace/item/')]//span[contains(@class, 'xsag5q8')]` | City, State or Location description |

---

## 2. Design Strategy

Facebook Marketplace uses dynamic, obfuscated CSS classes (such as `x1lliihq`, `x1iorvi4`, `x193iq5w`) that change between Facebook code updates.

To make this bot resilient against frequent site updates:
1. **Semantic Anchor Matching:** We anchor on URLs matching `a[href*="/marketplace/item/"]` rather than obfuscated class names.
2. **Text Heuristics:** Price lines, mileage lines, and location lines inside each listing card are matched via regular expressions (`PRICE_LINE_RE`, `MILEAGE_LINE_RE`, `LOCATION_LINE_RE`).
3. **OpenGraph Metadata:** Listing details use standard `meta[property="og:title"]` and `meta[property="og:description"]` tags.

---

## 2. When Facebook Updates its Interface

If Facebook changes its markup and searches return zero results:

1. Open the account in visible mode via **Account Manager → Open Browser / Login**.
2. Navigate to Facebook Marketplace and perform a search.
3. Open Chrome DevTools (`F12`):
   - Right-click a listing card and inspect the HTML.
   - Confirm whether the anchor tag still links to `/marketplace/item/<numeric_id>`.
   - Confirm the container containing listing prices.
4. Update the selectors in `app/services/selectors.py`.
5. Run the offline test suite:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_extractor.py
   ```
