// ==UserScript==
// @name         Facebook Marketplace Intelligence Bot (Tampermonkey Agent)
// @namespace    https://github.com/pythonicshariful/Facebook-Marketplace-Search-Intelligence-Bot
// @version      2.5.0
// @description  Automates Facebook Marketplace search, location, radius, price filtering and data collection controlled by the Flask Dashboard via API.
// @author       Pythonic Shariful
// @match        https://www.facebook.com/marketplace*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      127.0.0.1
// @connect      localhost
// @connect      facebook.com
// @connect      www.facebook.com
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // Template variables dynamically replaced by server, or fallbacks for manual installation
  const API_BASE = "%%API_BASE%%".startsWith("%%") ? "http://127.0.0.1:8080/api/tm" : "%%API_BASE%%";
  const API_TOKEN = "%%API_TOKEN%%".startsWith("%%") ? "fb-marketplace-tm-token-secret" : "%%API_TOKEN%%";

  // Persistent Agent Identification
  let AGENT_ID = GM_getValue("fmb_agent_id", null);
  if (!AGENT_ID) {
    AGENT_ID = "agent_" + Math.random().toString(36).substring(2, 10);
    GM_setValue("fmb_agent_id", AGENT_ID);
  }

  let isExecuting = false;
  let heartbeatTimer = null;
  let pollTimer = null;

  // -------------------------------------------------------------------------
  // HUD Status Display (Floating Widget on Facebook Marketplace)
  // -------------------------------------------------------------------------
  let hudContainer = null;
  let hudStatusText = null;
  let hudDetailsText = null;

  function createHUD() {
    if (document.getElementById("fmb-agent-hud")) return;
    hudContainer = document.createElement("div");
    hudContainer.id = "fmb-agent-hud";
    hudContainer.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 999999;
      background: rgba(15, 23, 42, 0.94);
      color: #f8fafc;
      border: 1px solid rgba(59, 130, 246, 0.5);
      border-radius: 12px;
      padding: 12px 16px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
      min-width: 280px;
      max-width: 380px;
      backdrop-filter: blur(8px);
      pointer-events: auto;
      transition: all 0.2s ease;
    `;

    hudContainer.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span id="fmb-status-dot" style="width: 10px; height: 10px; border-radius: 50%; background: #22c55e; display: inline-block; box-shadow: 0 0 8px #22c55e;"></span>
          <strong style="color: #60a5fa; font-size: 13px;">Marketplace Bot Agent</strong>
        </div>
        <span style="font-size: 11px; color: #94a3b8;">${AGENT_ID}</span>
      </div>
      <div id="fmb-status-msg" style="font-weight: 500; color: #e2e8f0; margin-bottom: 4px;">Connected & Idle</div>
      <div id="fmb-status-sub" style="font-size: 11px; color: #94a3b8; word-break: break-all;">Listening for search jobs...</div>
    `;

    document.body.appendChild(hudContainer);
    hudStatusText = document.getElementById("fmb-status-msg");
    hudDetailsText = document.getElementById("fmb-status-sub");
  }

  function updateHUD(status, detail, isBusy = false) {
    if (!hudStatusText) createHUD();
    if (hudStatusText) hudStatusText.textContent = status;
    if (hudDetailsText) hudDetailsText.textContent = detail;
    const dot = document.getElementById("fmb-status-dot");
    if (dot) {
      dot.style.background = isBusy ? "#f59e0b" : "#22c55e";
      dot.style.boxShadow = isBusy ? "0 0 8px #f59e0b" : "0 0 8px #22c55e";
    }
  }

  // -------------------------------------------------------------------------
  // Network Utilities (GM_xmlhttpRequest with Bearer Auth)
  // -------------------------------------------------------------------------
  function apiRequest(endpoint, method = "GET", data = null) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        url: `${API_BASE}${endpoint}`,
        method: method,
        headers: {
          "Authorization": `Bearer ${API_TOKEN}`,
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        data: data ? JSON.stringify(data) : null,
        timeout: 25000,
        onload: function (response) {
          try {
            const json = JSON.parse(response.responseText);
            if (response.status >= 200 && response.status < 300) {
              resolve(json);
            } else {
              reject(new Error(json.error || `HTTP ${response.status}`));
            }
          } catch (e) {
            reject(new Error(`Failed to parse API response (${response.status})`));
          }
        },
        onerror: function (err) {
          reject(new Error("Network error connecting to Dashboard API. Is the dashboard running?"));
        },
        ontimeout: function () {
          reject(new Error("Dashboard API request timed out"));
        },
      });
    });
  }

  // -------------------------------------------------------------------------
  // DOM Manipulation Helpers for React UI
  // -------------------------------------------------------------------------
  const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

  function setReactInputValue(input, value) {
    if (!input) return;
    input.focus();
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(input, value);
    } else {
      input.value = value;
    }
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function simulateEnterKey(element) {
    if (!element) return;
    const options = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
    element.dispatchEvent(new KeyboardEvent('keydown', options));
    element.dispatchEvent(new KeyboardEvent('keypress', options));
    element.dispatchEvent(new KeyboardEvent('keyup', options));
  }

  function simulateClick(element) {
    if (!element) return;
    try {
      element.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    } catch (e) { }

    const opts = { bubbles: true, cancelable: true, composed: true };

    // Pointer events (React 18 / modern Facebook)
    try {
      if (typeof PointerEvent === 'function') {
        element.dispatchEvent(new PointerEvent('pointerdown', opts));
        element.dispatchEvent(new PointerEvent('pointerup', opts));
      }
    } catch (e) { }

    // Mouse events (never pass `view: window` because in Tampermonkey sandbox `window` is a Proxy that fails WebIDL conversion to Window)
    try {
      element.dispatchEvent(new MouseEvent('mouseenter', opts));
      element.dispatchEvent(new MouseEvent('mouseover', opts));
      element.dispatchEvent(new MouseEvent('mousedown', opts));
      element.dispatchEvent(new MouseEvent('mouseup', opts));
      element.dispatchEvent(new MouseEvent('click', opts));
    } catch (e) { }

    // Native click
    try {
      if (typeof element.click === 'function') {
        element.click();
      }
    } catch (e) { }
  }

  function waitForElement(selectorOrFn, timeout = 12000, interval = 200) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      const timer = setInterval(() => {
        let el = null;
        if (typeof selectorOrFn === "function") {
          try { el = selectorOrFn(); } catch (e) { }
        } else {
          el = document.querySelector(selectorOrFn);
        }

        if (el) {
          clearInterval(timer);
          resolve(el);
          return;
        }

        if (Date.now() - startTime > timeout) {
          clearInterval(timer);
          reject(new Error(`Timed out waiting for element: ${selectorOrFn}`));
        }
      }, interval);
    });
  }

  function getLoggedInUser() {
    try {
      const profileLink = document.querySelector('a[href*="/me/"], a[aria-label*="Your profile"], a[href^="/profile.php"]');
      if (profileLink) {
        return profileLink.getAttribute("aria-label") || "Active User";
      }
    } catch (e) { }
    return null;
  }

  // -------------------------------------------------------------------------
  // Heartbeat & Job Polling Loop
  // -------------------------------------------------------------------------
  async function sendHeartbeat() {
    try {
      const res = await apiRequest("/heartbeat", "POST", {
        agent_id: AGENT_ID,
        fb_user: getLoggedInUser(),
        current_url: window.location.href,
      });
      if (res && res.paused) {
        updateHUD("Agent Paused", "Dashboard has paused searches.");
      }
    } catch (e) {
      console.warn("[FMBot] Heartbeat warning:", e.message);
    }
  }

  async function pollForNextJob() {
    if (isExecuting) return;

    // Check if on Marketplace page
    if (!window.location.pathname.startsWith("/marketplace")) {
      updateHUD("Idle", "Navigate to /marketplace to begin automation.");
      return;
    }

    try {
      const res = await apiRequest(`/next-job?agent_id=${AGENT_ID}`, "GET");
      if (res && res.job) {
        isExecuting = true;
        await executeJob(res.job);
        isExecuting = false;
      }
    } catch (e) {
      console.warn("[FMBot] Poll error:", e.message);
    }
  }

  // -------------------------------------------------------------------------
  // Core Automation Workflow (Steps 1 to 10)
  // -------------------------------------------------------------------------
  async function executeJob(job) {
    console.log("[FMBot] Starting Job #" + job.job_id, job);
    updateHUD(`Running Job #${job.job_id}`, `Search: ${job.search_name}`, true);

    const reportProgress = async (step) => {
      console.log(`[FMBot] Step: ${step}`);
      updateHUD(`Job #${job.job_id}`, step, true);
      try {
        await apiRequest(`/jobs/${job.job_id}/progress`, "POST", { step });
      } catch (e) { }
    };

    try {
      await reportProgress("Initializing search parameters");

      // 1. Direct Search URL Navigation or Query Input
      // If a pre-built target_url is provided, navigate directly to it so Facebook loads actual search results.
      if (job.target_url) {
        const urlParams = new URLSearchParams(window.location.search);
        const currentQuery = (urlParams.get("query") || "").trim().toLowerCase();
        const targetQuery = (job.search_terms || "").trim().toLowerCase();

        // Check if current page is already showing this search query results
        const onSearchPage = window.location.pathname.includes("/search") && 
          (!targetQuery || currentQuery === targetQuery || currentQuery.includes(targetQuery) || targetQuery.includes(currentQuery));

        if (!onSearchPage) {
          await reportProgress(`Navigating directly to Marketplace search URL: "${job.search_terms}"`);
          window.location.href = job.target_url;
          return; // Browser navigates to search page; pollForNextJob resumes this claimed job
        }
      } else if (job.search_terms) {
        await reportProgress(`Typing search term: "${job.search_terms}"`);
        const searchInput = await waitForElement(
          'input[aria-label="Search Marketplace"], input[placeholder="Search Marketplace"]',
          10000
        );

        searchInput.click();
        await sleep(300);
        setReactInputValue(searchInput, job.search_terms);
        await sleep(500);
        simulateEnterKey(searchInput);

        // Wait for search results container to appear
        await sleep(3500);
      }

      // 2. Open Location Dialog (Optional refinement)
      if (job.location) {
        try {
          await reportProgress(`Opening location filter for: "${job.location}"`);

          // Look for the Location button under #seo_filters or by aria-label
          const locationButton = await waitForElement(() => {
            return (
              document.querySelector('#seo_filters div[role="button"][aria-label^="Location:"]') ||
              document.querySelector('#seo_filters div[role="button"]') ||
              Array.from(document.querySelectorAll('div[role="button"]')).find(b =>
                b.getAttribute("aria-label")?.includes("Location:") ||
                (b.textContent.includes("Within") && b.textContent.includes("km"))
              )
            );
          }, 6000);

          locationButton.click();

          // 3. Wait for "Change location" Dialog
          await reportProgress("Waiting for Change Location modal");
          const modal = await waitForElement(
            'div[aria-label="Change location"][role="dialog"], div[role="dialog"][aria-label="Change location"]',
            6000
          );
          await sleep(700);

          // 4. Clear existing value and type new location
          await reportProgress(`Entering location: ${job.location}`);

          const locationInput = await waitForElement(() => {
            return modal.querySelector('input[aria-label="Location"]');
          }, 5000);

          if (locationInput) {
            locationInput.click();
            await sleep(200);
            locationInput.focus();
            await sleep(100);

            // Force-set empty value via React's native setter
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
            if (nativeSetter) {
              nativeSetter.call(locationInput, '');
            } else {
              locationInput.value = '';
            }
            locationInput.dispatchEvent(new Event('input', { bubbles: true }));
            await sleep(150);

            if (nativeSetter) {
              nativeSetter.call(locationInput, job.location);
            } else {
              locationInput.value = job.location;
            }
            locationInput.dispatchEvent(new Event('input', { bubbles: true }));
            locationInput.dispatchEvent(new Event('change', { bubbles: true }));
            await sleep(1800);

            // 5. Select First Autocomplete Suggestion
            await reportProgress("Selecting location suggestion");
            const firstLi = await waitForElement(() => {
              const globalLi = document.querySelector('ul[role="listbox"] li[role="option"]');
              if (globalLi) return globalLi;
              return modal.querySelector('ul[role="listbox"] li[role="option"]');
            }, 6000);

            if (firstLi) {
              const clickTarget = firstLi.querySelector('div[aria-describedby]') || firstLi.querySelector('div[role="none"]') || firstLi;
              simulateClick(clickTarget);
              if (clickTarget !== firstLi) {
                simulateClick(firstLi);
              }
              await sleep(1000);
            }

            // 6. Select Radius from the Radius combobox
            const targetRadiusLabel = job.radius_label || `${job.radius_km || 5} kilometers`;
            await reportProgress(`Setting radius: ${targetRadiusLabel}`);

            const radiusTrigger = await waitForElement(() => {
              return (
                modal.querySelector('label[role="combobox"][aria-haspopup="listbox"]') ||
                modal.querySelector('label[role="combobox"]') ||
                Array.from(modal.querySelectorAll('label')).find(l =>
                  l.getAttribute('role') === 'combobox' ||
                  l.textContent.includes('Radius')
                )
              );
            }, 5000);

            if (radiusTrigger) {
              simulateClick(radiusTrigger);
              await sleep(800);

              const targetKm = parseInt(job.radius_km, 10) || 5;
              const radiusOption = await waitForElement(() => {
                const allOptions = Array.from(document.querySelectorAll('div[role="option"], [role="option"]'))
                  .filter(el => /\d+\s*kilometer|\d+\s*km/i.test(el.textContent));

                if (!allOptions.length) return null;

                const exactMatch = allOptions.find(opt =>
                  opt.textContent.trim().toLowerCase() === targetRadiusLabel.toLowerCase()
                );
                if (exactMatch) return exactMatch;

                const kmMatch = allOptions.find(opt => {
                  const m = opt.textContent.match(/(\d+)\s*kilometer/i) || opt.textContent.match(/(\d+)/);
                  return m && parseInt(m[1], 10) === targetKm;
                });
                if (kmMatch) return kmMatch;

                let bestOption = null;
                let minDiff = Infinity;
                for (const opt of allOptions) {
                  const m = opt.textContent.match(/(\d+)\s*kilometer/i) || opt.textContent.match(/(\d+)/);
                  if (m) {
                    const optKm = parseInt(m[1], 10);
                    const diff = Math.abs(optKm - targetKm);
                    if (diff < minDiff) {
                      minDiff = diff;
                      bestOption = opt;
                    }
                  }
                }
                return bestOption || allOptions[0];
              }, 5000);

              if (radiusOption) {
                simulateClick(radiusOption);
                await sleep(600);
              }
            }

            // 7b. Click Apply Button
            await reportProgress("Applying location and radius");
            const applyBtn = await waitForElement(() => {
              const inModal = modal.querySelector('div[aria-label="Apply"][role="button"]');
              if (inModal) return inModal;
              return (
                document.querySelector('div[aria-label="Apply"][role="button"]') ||
                Array.from(document.querySelectorAll('div[role="button"]')).find(b =>
                  b.getAttribute('aria-label') === 'Apply' ||
                  b.textContent.trim() === 'Apply'
                )
              );
            }, 5000);

            if (applyBtn) {
              simulateClick(applyBtn);
              await sleep(2500);
            }
          }
        } catch (locErr) {
          console.warn("[FMBot] Location filter refinement notice:", locErr.message);
          await reportProgress("Proceeding with active search results");
        }
      }


      // 8. Min and Max Price Filters
      if (job.min_price != null || job.max_price != null) {
        await reportProgress(`Applying price range: $${job.min_price || 0} - $${job.max_price || 'Any'}`);

        const minInput = document.querySelector('input[aria-label="Minimum Range"], input[placeholder="Min"]');
        const maxInput = document.querySelector('input[aria-label="Maximum Range"], input[placeholder="Max"]');

        if (minInput && job.min_price != null) {
          minInput.click();
          setReactInputValue(minInput, String(job.min_price));
          await sleep(300);
          simulateEnterKey(minInput);
        }

        if (maxInput && job.max_price != null) {
          maxInput.click();
          setReactInputValue(maxInput, String(job.max_price));
          await sleep(300);
          simulateEnterKey(maxInput);
        }

        await sleep(3000);
      }

      // 9. Scroll to Trigger Dynamic Lazy-Loading of Listings
      await reportProgress("Scrolling feed to load listings...");
      for (let i = 0; i < 3; i++) {
        window.scrollBy({ top: 900, behavior: "smooth" });
        await sleep(1500);
      }

      // 10. Extract Scraped Listing Cards & HTML
      await reportProgress("Extracting listing cards from page...");
      const extractedListings = scrapeListingCards();
      console.log(`[FMBot] Scraped ${extractedListings.length} listing cards.`);

      // 11. Inspect product details for each listing (description, condition, seller)
      const cache = job.memorized_cache || {};
      const toFetch = [];
      for (const item of extractedListings) {
        if (cache[item.url] && (cache[item.url].description || cache[item.url].seller_name || cache[item.url].condition)) {
          item.description = cache[item.url].description || null;
          item.condition = cache[item.url].condition || item.condition || null;
          item.seller_name = cache[item.url].seller_name || null;
        } else {
          toFetch.push(item);
        }
      }

      // Check product details for up to 15 items per batch
      const inspectList = toFetch.slice(0, 15);
      if (inspectList.length > 0) {
        await reportProgress(`Checking all available info for ${inspectList.length} products...`);
        for (let i = 0; i < inspectList.length; i++) {
          const item = inspectList[i];
          const shortTitle = item.title ? item.title.substring(0, 24) : "Item";
          await reportProgress(`Inspecting details (${i + 1}/${inspectList.length}): ${shortTitle}...`);
          try {
            const details = await fetchListingDetails(item.url);
            if (details.description) item.description = details.description;
            if (details.condition) item.condition = details.condition;
            if (details.seller_name) item.seller_name = details.seller_name;
          } catch (e) {
            console.warn("[FMBot] Detail inspect error for:", item.url, e);
          }
          await sleep(250);
        }
      }

      // Also capture main feed HTML so Python's robust BeautifulSoup extractor can parse full cards
      const mainElement = document.querySelector('div[role="main"]') || document.body;
      const mainHtml = mainElement ? mainElement.innerHTML : "";

      await reportProgress(`Submitting ${extractedListings.length} listings with all product info to dashboard`);
      await apiRequest(`/jobs/${job.job_id}/result`, "POST", {
        url: window.location.href,
        page_state: "success",
        html: mainHtml,
        listings: extractedListings,
      });

      updateHUD("Success", `Job #${job.job_id} done (${extractedListings.length} listings collected).`);
      await sleep(2000);
    } catch (err) {
      console.error("[FMBot] Job failed:", err);
      updateHUD("Job Error", err.message);
      try {
        await apiRequest(`/jobs/${job.job_id}/fail`, "POST", {
          error: err.message,
          step: hudStatusText ? hudStatusText.textContent : "execution",
        });
      } catch (e) { }
    }
  }

  // -------------------------------------------------------------------------
  // Marketplace Card Scraper Helper
  // -------------------------------------------------------------------------
  function scrapeListingCards() {
    const cards = [];
    const anchors = Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]'));
    const seenUrls = new Set();
    const PRICE_RE = /^(?:[A-Z]{1,4}\$|[A-Z]{3}|US\$|CA\$|BDT|USD|EUR|GBP|[$€£₹৳])\s?[\d.,]+\s?[KkMm]?$|^free$/i;

    for (const a of anchors) {
      try {
        const href = a.getAttribute("href");
        if (!href) continue;

        const match = href.match(/\/marketplace\/item\/(\d+)/);
        const fbItemId = match ? match[1] : null;
        const fullUrl = a.href.split("?")[0]; // Canonical clean URL

        if (seenUrls.has(fullUrl)) continue;
        seenUrls.add(fullUrl);

        // 1. Check aria-label first (Facebook standard: "Title, Price, Location")
        const ariaLabel = (a.getAttribute("aria-label") || "").trim();
        let title = null;
        let priceText = null;
        let location = null;

        if (ariaLabel) {
          const parts = ariaLabel.split(",").map(p => p.trim()).filter(Boolean);
          if (parts.length > 0) {
            title = parts[0];
          }
          for (const p of parts.slice(1)) {
            if (!priceText && PRICE_RE.test(p)) {
              priceText = p;
            } else if (!location) {
              location = p;
            }
          }
        }

        // 2. Gather text lines from card spans
        const textLines = Array.from(a.querySelectorAll("span"))
          .map(s => s.textContent.trim())
          .filter(t => t.length > 0);

        for (const line of textLines) {
          if (!priceText && PRICE_RE.test(line)) {
            priceText = line;
            continue;
          }
          if (!title && line.length > 3 && !line.includes("·") && line !== priceText && !PRICE_RE.test(line)) {
            title = line;
            continue;
          }
          if (title && !location && line.length > 2 && line !== title && line !== priceText && !PRICE_RE.test(line)) {
            location = line;
          }
        }

        const img = a.querySelector("img");
        const imgSrc = img ? (img.getAttribute("src") || "") : null;
        const imgAlt = img ? (img.getAttribute("alt") || "") : null;

        if (imgAlt && (!title || title.length < 3 || PRICE_RE.test(title))) {
          title = imgAlt;
        }

        if (title || fbItemId) {
          cards.push({
            fb_item_id: fbItemId,
            url: fullUrl,
            title: title || "Marketplace Listing",
            price_text: priceText,
            location: location,
            image_url: imgSrc,
          });
        }
      } catch (e) {
        console.warn("[FMBot] Error parsing card:", e);
      }
    }

    return cards;
  }

  // -------------------------------------------------------------------------
  // Product Detail Parser & Background Fetcher
  // -------------------------------------------------------------------------
  function parseListingDetailHtml(html) {
    const details = {
      description: null,
      condition: null,
      seller_name: null,
    };
    if (!html) return details;

    try {
      // 1. JSON-LD scripts (Product schema)
      const jsonLdRegex = /<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi;
      let match;
      while ((match = jsonLdRegex.exec(html)) !== null) {
        try {
          const data = JSON.parse(match[1]);
          if (data && (data["@type"] === "Product" || data.description || data.offers)) {
            if (data.description && !details.description) {
              details.description = data.description;
            }
            if (data.itemCondition && !details.condition) {
              const c = String(data.itemCondition).split("/").pop().replace("Condition", "");
              details.condition = c;
            }
            if (data.seller && data.seller.name && !details.seller_name) {
              details.seller_name = data.seller.name;
            }
          }
        } catch (e) {}
      }

      // 2. OpenGraph meta description: contains full product description
      if (!details.description) {
        const ogMatch = html.match(/<meta\s+(?:property|name)=["'](?:og:description|description)["']\s+content=["'](.*?)["']/i);
        if (ogMatch && ogMatch[1]) {
          const parser = new DOMParser();
          const doc = parser.parseFromString(ogMatch[1], "text/html");
          details.description = doc.body.textContent || ogMatch[1];
        }
      }

      // 3. Condition from text patterns
      if (!details.condition) {
        const condMatch = html.match(/(?:Condition|condition)[:\s]+(?:<[^>]+>)?\s*(New|Used\s*-\s*Like\s*New|Used\s*-\s*Good|Used\s*-\s*Fair|Used)/i);
        if (condMatch) {
          details.condition = condMatch[1].trim();
        }
      }

      // 4. Seller name from GraphQL / Relay or meta
      if (!details.seller_name) {
        const sellerMatch = html.match(/"seller":\{"__typename":"User","name":"([^"]+)"/i) ||
                            html.match(/"marketplace_listing_seller":\{"name":"([^"]+)"/i) ||
                            html.match(/"seller_name":"([^"]+)"/i);
        if (sellerMatch) {
          details.seller_name = sellerMatch[1];
        }
      }
    } catch (err) {
      console.warn("[FMBot] Error parsing listing details:", err);
    }

    return details;
  }

  function fetchListingDetails(url) {
    return new Promise((resolve) => {
      GM_xmlhttpRequest({
        url: url,
        method: "GET",
        headers: {
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout: 8000,
        onload: function (resp) {
          if (resp.status >= 200 && resp.status < 300) {
            resolve(parseListingDetailHtml(resp.responseText));
          } else {
            resolve({});
          }
        },
        onerror: function () {
          resolve({});
        },
        ontimeout: function () {
          resolve({});
        },
      });
    });
  }

  // -------------------------------------------------------------------------
  // Initialization
  // -------------------------------------------------------------------------
  function init() {
    createHUD();
    updateHUD("Connected & Ready", "Waiting for dashboard commands...");

    // Periodic heartbeat every 15 seconds
    sendHeartbeat();
    heartbeatTimer = setInterval(sendHeartbeat, 15000);

    // Poll for jobs every 5 seconds
    pollTimer = setInterval(pollForNextJob, 5000);
  }

  // Run on load
  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(init, 1500);
  } else {
    window.addEventListener("DOMContentLoaded", () => setTimeout(init, 1500));
  }
})();
