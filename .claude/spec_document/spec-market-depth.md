# Spec: Market Depth Screenshot Capture

## Problem Statement
After the strategy scheduler sends email alerts for filtered stocks, there is no visual record of the buyer/seller trading map (Market Depth) at the time of alert. A screenshot of the "Market depth" section on each stock's Groww page must be captured and stored per-slot, enabling post-hoc review of bid/ask distribution at alert time.

## Goal
Create a reusable utility function that navigates to a stock's Groww page, locates the **Market depth** section using generic (UI-change-resilient) identification, captures a screenshot of that section, and saves it as `{TICKER}.png` in a slot-specific directory.

---

## File to Create

### `src/tools/utils/market_depth_capture.py`

**Location:** `c:\General\Strend\src\tools\utils\market_depth_capture.py`

#### Dependencies
- `playwright.async_api` (already used by `news_scraper.py`, `chart_capture.py`)
- `pathlib.Path`
- `asyncio`, `os`, `sys`, `re`
- Reuse helpers from `news_scraper.py`: `dismiss_overlays`, `_resolve_search_input`, `_STOCK_URL_KEYWORDS`

#### Public Function Signature
```python
async def capture_market_depth(
    ticker: str,
    slot_label: str,
    stock_page_url: str | None = None,
) -> str | None:
    """
    Capture a screenshot of the Market Depth section for a stock on Groww.

    Args:
        ticker:         NSE ticker symbol (e.g. "RELIANCE", "SCI").
        slot_label:     Schedule slot identifier (e.g. "slot_1_0934").
                        Used to build the output sub-directory.
        stock_page_url: Optional pre-known Groww stock page URL.
                        If None, the function discovers it via UI search.

    Returns:
        Absolute path to the saved PNG on success, or None on failure.
    """
```

#### Output Path Convention
```
<project_root>/buyer_seller_details/<slot_label>/<TICKER>.png
```
Example: `c:\General\Strend\buyer_seller_details\slot_1_0934\SCI.png`

- The directory is auto-created via `Path.mkdir(parents=True, exist_ok=True)`.
- Each new run for the same slot+ticker **overwrites** the previous image (latest snapshot only).

---

## Implementation Details

### Phase 1 — Browser Setup
Reuse the same Playwright launch pattern established in `news_scraper.py` (ref: lines 471-483):

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        viewport={"width": 1280, "height": 900},
    )
    page = await context.new_page()
```

### Phase 2 — Navigate to Stock Page
Two paths:

| Condition | Action |
|---|---|
| `stock_page_url` is provided | `page.goto(stock_page_url)` directly |
| `stock_page_url` is `None` | Use the same UI-search strategy as `_strategy_ui` in `news_scraper.py` (ref: lines 313-366): goto `https://groww.in/`, dismiss overlays, fill search, press Enter, wait for stock URL pattern |

After navigation, strip any trailing path segments (e.g. `/market-news`) to land on the **main stock page** where the Market Depth widget lives.

### Phase 3 — Locate the Market Depth Section (Generic Strategy)

> **Critical Requirement:** Do NOT rely on hashed/dynamic CSS class names (e.g. `stockMarketDepth_customHeader__kd9Dz`). These change on every Groww deployment.

**Identification strategy — text-content-based heading search:**

```python
async def _find_market_depth_section(page) -> Locator | None:
    """
    Locate the Market Depth container using content-based heuristics.

    Strategy (ordered by reliability):
      1. Find an <h2> (or any heading h1-h6) whose visible text matches
         "Market depth" (case-insensitive).  Then return the nearest
         ancestor container — the heading's parent <div> that wraps the
         full depth table.
      2. Find the element with id="stkLASection" (Groww's stable section
         anchor id).  This id has remained stable across deployments.
      3. Fallback: search for any element containing both "Bid Price"
         AND "Ask Price" text, then walk up to the enclosing section.
    """
```

**Implementation pseudocode:**
```python
# --- Strategy 1: heading text match ---
headings = page.locator("h1, h2, h3, h4, h5, h6")
count = await headings.count()
for i in range(count):
    text = (await headings.nth(i).inner_text()).strip()
    if re.search(r"market\s*depth", text, re.IGNORECASE):
        # The parent div wrapping the heading + depth table
        container = headings.nth(i).locator("xpath=..")
        return container

# --- Strategy 2: stable id anchor ---
section = page.locator("#stkLASection")
if await section.count() > 0:
    return section.first

# --- Strategy 3: bid/ask text presence ---
# Use XPath to find any div containing both "Bid Price" and "Ask Price"
xpath = (
    "//div[.//*[contains(text(),'Bid Price')] "
    "and .//*[contains(text(),'Ask Price')]]"
)
candidates = page.locator(xpath)
if await candidates.count() > 0:
    # Pick the outermost match (largest bounding box)
    return candidates.first

return None
```

### Phase 4 — Scroll into View & Screenshot
```python
if container:
    await container.scroll_into_view_if_needed()
    await page.wait_for_timeout(800)  # let animations settle
    img_bytes = await container.screenshot(type="png")
```

### Phase 5 — Save to Disk
```python
output_dir = _project_root() / "buyer_seller_details" / slot_label
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / f"{ticker}.png"
output_path.write_bytes(img_bytes)
```

### Error Handling
- Wrap all Playwright operations in try/except; log failures via `print()` (consistent with `news_scraper.py` style).
- On any failure return `None` — the caller must tolerate missing screenshots.
- Close browser in a `finally` block.

### Windows Event Loop
Include the Proactor policy guard at module top (ref: `chart_capture.py` line 10-11):
```python
if os.getenv("ENVIRONMENT_OS", sys.platform) == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

---

## File to Modify

### `src/cron_jobs/strategy_schedular.py`

**Location:** `c:\General\Strend\src\cron_jobs\strategy_schedular.py`

#### Import Addition (top of file, near line 46-48)
```python
from src.tools.utils.market_depth_capture import capture_market_depth
```

#### Integration Point — After Step 6 (Email), Before Step 7 (Notifications)
Insert a new **Step 6.5** between lines 507 and 511:

```python
# -----------------------------------------------------------------
# Step 6.5: Capture Market Depth screenshots for each stock
# -----------------------------------------------------------------
logger.info(f"📸 Capturing Market Depth screenshots for {len(stocks_with_recent_news)} stock(s)...")
for stock in stocks_with_recent_news:
    ticker = stock.get("ticker", "")
    if not ticker:
        continue
    try:
        # Build the stock page URL from cache if available
        stock_url = None  # let the capture function discover it
        saved_path = await capture_market_depth(
            ticker=ticker,
            slot_label=slot_label,
            stock_page_url=stock_url,
        )
        if saved_path:
            logger.info(f"  ✅ {ticker} depth screenshot -> {saved_path}")
        else:
            logger.warning(f"  ⚠️ {ticker} depth screenshot failed")
    except Exception as e:
        logger.warning(f"  ⚠️ Market depth capture error for {ticker}: {e}")
```

> **Optimisation note:** If the ticker→URL cache from `news_scraper.py` (`cache/strategy/ticker_mapping.json`) is available, pass the stock page URL (strip `/market-news` suffix) to `capture_market_depth` to skip redundant UI navigation.

---

## Output Directory Structure
```
buyer_seller_details/
├── slot_1_0934/
│   ├── RELIANCE.png
│   ├── SCI.png
│   └── INFY.png
├── slot_2_0951/
│   ├── TCS.png
│   └── HDFCBANK.png
├── slot_3_1005/
│   └── ...
└── slot_4_1030/
    └── ...
```

## Cache / Cleanup Policy
- Screenshots are **not** auto-cleaned (unlike Excel cache). They accumulate per slot per day.
- The caller may add cleanup logic in `clean_old_cache()` if disk space becomes a concern — but this is **out of scope** for this spec.

---

## Constraints
- **No static CSS classes** — all element identification uses text content, stable IDs, or semantic HTML attributes.
- **Headless mode** — must work without a visible browser window (server/cron environment).
- **Timeout budget** — each stock capture should complete within 30 seconds (navigation + screenshot).
- **Graceful degradation** — a failed capture must never crash the scheduler; it logs a warning and moves on.
- **Image format** — PNG (lossless, ensures text in depth table remains readable).

## Acceptance Criteria
1. **AC1** — Running `await capture_market_depth("RELIANCE", "slot_1_0934")` produces a PNG at `buyer_seller_details/slot_1_0934/RELIANCE.png` containing the Market Depth section (buy orders + sell orders table).
2. **AC2** — The locator strategy works even if Groww changes its CSS class hashes (tested by verifying Strategy 1/2/3 fallback chain).
3. **AC3** — After `send_mail()` completes in `strategy_schedular.py`, the scheduler captures depth screenshots for every filtered stock before broadcasting notifications.
4. **AC4** — A Playwright/network failure for one ticker does not prevent capture of the remaining tickers.
5. **AC5** — The function returns `None` on failure and the scheduler logs a warning without crashing.
