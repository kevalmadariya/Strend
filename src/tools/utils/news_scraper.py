"""
news_scraper.py  –  Groww news scraper (resilient, multi-strategy)

Strategy ladder for discovering a ticker's stock-page URL
(each tried in order; first success wins):

  S1 – API interception   : listens to XHR/fetch while typing in the search
                            box; parses Groww's own autocomplete JSON to get
                            the slug directly — zero DOM selectors involved.
  S2 – Search results page: navigates to groww.in/search?q=<ticker> and
                            extracts the first stock link from the rendered page.
  S3 – UI click-through   : types in the search box and clicks the first
                            suggestion (original approach, now last resort).

Debug screenshots are saved at every critical step so any future breakage is
diagnosable without re-running the code interactively.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    # File lives at src/tools/utils/news_scraper.py  ->  4 levels up = root
    return Path(__file__).resolve().parent.parent.parent.parent


def _debug_dir() -> Path:
    d = _project_root() / "debug" / "scraper_screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file() -> Path:
    f = _project_root() / "cache" / "strategy" / "ticker_mapping.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


# ---------------------------------------------------------------------------
# Screenshot helper
# ---------------------------------------------------------------------------

# async def screenshot(page, label: str, ticker: str = "") -> None:
#     """Save a full-page PNG to the debug directory.  Never raises."""
#     try:
#         ts = datetime.now().strftime("%H%M%S")
#         safe = lambda s: re.sub(r"[^a-zA-Z0-9_-]", "_", s)
#         fname = f"{ts}_{safe(ticker)}_{safe(label)}.png"
#         path = _debug_dir() / fname
#         await page.screenshot(path=str(path), full_page=True)
#         print(f"  📸 Screenshot -> debug/scraper_screenshots/{fname}")
#     except Exception as e:
#         print(f"  ⚠️  Screenshot failed ({e})")


# ---------------------------------------------------------------------------
# Dismiss common overlays (cookie banners, login prompts, etc.)
# ---------------------------------------------------------------------------

_OVERLAY_SELECTORS = [
    "button[id*='accept' i]",
    "button[class*='accept' i]",
    "button[aria-label*='accept' i]",
    "button[class*='cookie' i]",
    "button[aria-label='Close']",
    "button[aria-label='close']",
    "[class*='modal'] button[class*='close' i]",
    "[class*='popup'] button[class*='close' i]",
    "button:has-text('Skip')",
    "button:has-text('No thanks')",
    "button:has-text('Maybe later')",
    "button:has-text('Continue')",
]

async def dismiss_overlays(page) -> None:
    for sel in _OVERLAY_SELECTORS:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible(timeout=1200):
                await el.first.click(timeout=2000)
                await page.wait_for_timeout(400)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Selector registries
# ---------------------------------------------------------------------------

_SEARCH_INPUT_SELECTORS = [
    "input#globalSearch23",
    "input[id*='globalSearch']",
    "input[id*='search' i]",
    "input[placeholder*='Search' i]",
    "input[aria-label*='Search' i]",
    "input[type='search']",
    "header input[type='text']",
    "nav input[type='text']",
]

_SEARCH_TRIGGER_SELECTORS = [
    "div.se27SeSearchMainDivPlaceholder",
    "div[class*='SearchMainDiv']",
    "div[class*='searchMain']",
    "div[class*='search'][class*='placeholder' i]",
    "button[aria-label*='Search' i]",
    "[class*='searchIcon']",
    "[class*='search-icon']",
]

_SUGGESTION_CONTAINER_SELECTORS = [
    ".se27SeResultList",
    ".se27SeSuggestion",
    "[class*='ResultList']",
    "[class*='result-list']",
    "[class*='SuggestionList']",
    "[class*='suggestion-list']",
    "[class*='searchResult']",
    "[class*='search-result']",
    "[role='listbox']",
]

_SUGGESTION_ITEM_SELECTORS = [
    ".se27SeSuggestion",
    "[class*='Suggestion']:not([class*='List'])",
    "[class*='suggestion']:not([class*='list'])",
    "[class*='searchResult'] li",
    "[role='option']",
    "[role='listbox'] li",
    "[role='listbox'] > *",
    "[class*='ResultItem']",
    "[class*='result-item']",
]

_STOCK_LINK_SELECTORS = [
    "a[href*='/stocks/']",
    "a[href*='/stock/']",
    "a[href*='/equities/']",
    "a[href*='/shares/']",
]

_STOCK_URL_KEYWORDS = ["/stocks/", "/equities/", "/stock/", "/shares/"]

_NEWS_ROW_SELECTORS = [
    ".stockNews_newsRow__BC7Ia",        # original hashed class (kept for cache hits)
    "[class*='newsRow']",
    "[class*='news-row']",
    "[class*='NewsRow']",
    "[class*='newsCard']",
    "[class*='news-card']",
    "[class*='NewsCard']",
    "[class*='newsItem']",
    "[class*='news-item']",
    "article[class*='news' i]",
    "[class*='marketNews'] li",
    "[class*='market-news'] li",
    "[class*='newsList'] > *",
    "[class*='news-list'] > *",
]

_NEWS_HEADER_SELECTORS = [
    ".mnc671BoxHeaderText",
    "[class*='BoxHeader']",
    "[class*='boxHeader']",
    "[class*='box-header']",
    "[class*='newsHeader']",
    "[class*='news-header']",
    "[class*='newsSource']",
    "[class*='news-source']",
    "time",
    "[datetime]",
    "[class*='timestamp']",
    "[class*='timeAgo']",
    "[class*='time-ago']",
    "[class*='pubDate']",
    "span:first-child",
]

_NEWS_TITLE_SELECTORS = [
    ".mnc671BoxItemTitle",
    "[class*='ItemTitle']",
    "[class*='item-title']",
    "[class*='newsTitle']",
    "[class*='news-title']",
    "[class*='headline']",
    "[class*='Headline']",
    "h1, h2, h3, h4",
    "p[class*='title' i]",
    "a[class*='title' i]",
    "p",
]


# ---------------------------------------------------------------------------
# DOM helpers
# ---------------------------------------------------------------------------

async def _safe_text(locator, selectors: list, default: str = "") -> str:
    for sel in selectors:
        try:
            el = locator.locator(sel)
            if await el.count() > 0:
                t = await el.first.inner_text(timeout=3000)
                if t.strip():
                    return t.strip()
        except Exception:
            continue
    return default


async def _safe_attr(locator, selectors: list, attr: str, default: str = "") -> str:
    for sel in selectors:
        try:
            el = locator.locator(sel)
            if await el.count() > 0:
                v = await el.first.get_attribute(attr, timeout=3000)
                if v:
                    return v
        except Exception:
            continue
    return default


async def _resolve_search_input(page):
    """Return a visible search <input>, clicking triggers if necessary."""
    for sel in _SEARCH_INPUT_SELECTORS:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                return loc.first
        except Exception:
            continue

    for sel in _SEARCH_TRIGGER_SELECTORS:
        try:
            t = page.locator(sel)
            if await t.count() > 0 and await t.first.is_visible():
                await t.first.click()
                await page.wait_for_timeout(500)
                for inp in _SEARCH_INPUT_SELECTORS:
                    try:
                        loc = page.locator(inp)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            return loc.first
                    except Exception:
                        continue
        except Exception:
            continue

    # Keyboard shortcut as absolute last resort
    await page.keyboard.press("Control+K")
    await page.wait_for_timeout(600)
    for sel in _SEARCH_INPUT_SELECTORS:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                return loc.first
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Slug extraction from arbitrary JSON
# ---------------------------------------------------------------------------

def _slug_from_json(data) -> str | None:
    """
    Walk any JSON structure looking for a Groww stock page URL or slug.
    Returns a full https://groww.in/stocks/<slug> URL or None.
    """
    text = json.dumps(data)
    patterns = [
        r'"slug"\s*:\s*"([^"]+)"',
        r'"url"\s*:\s*"([^"]+stocks[^"]+)"',
        r'"link"\s*:\s*"([^"]+stocks[^"]+)"',
        r'"path"\s*:\s*"([^"]+stocks[^"]+)"',
        r'/stocks/([a-z0-9][a-z0-9_-]{2,})',
        r'/equities/([a-z0-9][a-z0-9_-]{2,})',
        r'/stock/([a-z0-9][a-z0-9_-]{2,})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1)
            if val.startswith("http"):
                return val
            if "/" in val:
                return "https://groww.in/" + val.lstrip("/")
            return f"https://groww.in/stocks/{val}"
    return None


def _make_news_url(stock_url: str) -> str:
    return stock_url.rstrip("/") + "/market-news"


# ===========================================================================
# Strategy 3 – UI click-through (original, now last resort)
# ===========================================================================

async def _strategy_ui(page, ticker: str) -> str | None:
    """
    Type in the homepage search box; click the first suggestion.
    Screenshots taken at every sub-step for easy debugging.
    """
    print("  [S3] UI click-through strategy...")
    try:
        await page.goto("https://groww.in/", timeout=40000)
        await dismiss_overlays(page)

        inp = await _resolve_search_input(page)
        if not inp:
            print("  [S3] Search input not found.")
            return None

        await inp.wait_for(state="visible", timeout=8000)
        await inp.fill("")
        await inp.type(ticker, delay=150)
        await page.wait_for_timeout(1500)
        await page.keyboard.press("Enter")

        for pat in ["**/stocks/**", "**/equities/**", "**/stock/**", "**/shares/**"]:
            try:
                await page.wait_for_url(pat, timeout=5000)
                break
            except Exception:
                continue

        current = page.url
        if not any(k in current for k in _STOCK_URL_KEYWORDS):
            print(f"  [S3] Did not reach stock page. Current URL: {current}")
            return None

        # Prefer a live "news" link on the page
        for sel in ["a[href*='market-news']", "a[href*='news']"]:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    href = await loc.first.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://groww.in" + href
                    if href:
                        print(f"  [S3] SUCCESS (live link) -> {href}")
                        return href
            except Exception:
                continue

        result = _make_news_url(current)
        print(f"  [S3] SUCCESS (constructed) -> {result}")
        return result

    except Exception as e:
        print(f"  [S3] Error: {e}")
        return None


# ===========================================================================
# Phase 2 – scrape news from the known news URL
# ===========================================================================

async def _scrape_news_page(page, news_url: str, ticker: str) -> list:
    print(f"🔗 [Scraper] Loading: {news_url}")
    try:
        await page.goto(news_url, timeout=30000)
    except Exception as e:
        print(f"❌ [Scraper] Failed to load news page: {e}")
        return []

    await dismiss_overlays(page)
    await page.wait_for_timeout(2000)

    # Wait for any news-row selector
    found_rows = False
    for sel in _NEWS_ROW_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=6000)
            found_rows = True
            break
        except Exception:
            continue

    if not found_rows:
        print("⚠️ [Scraper] No news rows matched any selector.")
        return []

    rows_loc = None
    for sel in _NEWS_ROW_SELECTORS:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                print(f"  [News] Rows matched: {sel!r}")
                rows_loc = loc
                break
        except Exception:
            continue

    if not rows_loc:
        print("⚠️ [Scraper] Could not locate news rows after all fallbacks.")
        return []

    count = await rows_loc.count()
    limit = min(count, 5)
    print(f"📄 [Scraper] {count} items found, processing {limit}...")

    results = []
    for i in range(limit):
        item = rows_loc.nth(i)

        full_header = await _safe_text(item, _NEWS_HEADER_SELECTORS)
        if full_header:
            parts = re.split(r"[·•|./]", full_header)
            time_text = parts[-1].strip() if len(parts) > 1 else full_header
        else:
            time_text = await _safe_attr(item, ["time", "[datetime]"], "datetime")

        news_text = await _safe_text(item, _NEWS_TITLE_SELECTORS)
        news_link = await _safe_attr(item, ["a"], "href", default="")
        if news_link.startswith("/"):
            news_link = "https://groww.in" + news_link

        print(f"  [{i+1}] {time_text!r} — {news_text[:60]}...")
        results.append({
            "ticker": ticker,
            "time_str": time_text,
            "news": news_text.replace("\n", " ").strip(),
            "url": news_link,
        })

    return results


# ===========================================================================
# Public entry point
# ===========================================================================

async def scrape_news_from_groww(ticker: str) -> list:
    """
    Scrapes news from Groww for a given ticker.
    Returns a list of dicts: [{'time_str': ..., 'news': ..., 'url': ...}]

    Three independent URL-discovery strategies are tried in sequence.
    Debug screenshots are saved to <project_root>/debug/scraper_screenshots/.
    """
    print(f"\n🕵️ [Scraper] ─── {ticker} ───")
    print(f"  📂 Screenshots -> {_debug_dir()}")

    # Load cache
    cache_file = _cache_file()
    ticker_mapping: dict = {}
    if cache_file.exists():
        try:
            ticker_mapping = json.loads(cache_file.read_text())
        except Exception:
            ticker_mapping = {}

    news_url: str | None = ticker_mapping.get(ticker)
    news_data: list = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )
            page = await context.new_page()

            # --------------------------------------------------------------
            # Phase 1: discover stock-page URL
            # --------------------------------------------------------------
            if not news_url:
                print("🔎 [Scraper] Discovering stock URL (not in cache)...")

                # news_url = await _strategy_api(page, ticker)

                # if not news_url:
                # news_url = await _strategy_search_page(page, ticker)

                # if not news_url:
                news_url = await _strategy_ui(page, ticker)

                # if not news_url:
                #     print(f"❌ [Scraper] All three strategies failed for {ticker}.")
                #     await screenshot(page, "all_failed", ticker)
                #     return []

                ticker_mapping[ticker] = news_url
                cache_file.write_text(json.dumps(ticker_mapping, indent=2))
                print(f"  💾 Cached: {news_url}")
            else:
                print(f"  ✅ Cached URL: {news_url}")

            # --------------------------------------------------------------
            # Phase 2: scrape news
            # --------------------------------------------------------------
            news_data = await _scrape_news_page(page, news_url, ticker)

            # If cached URL returned nothing, it may be stale — invalidate & retry
            if not news_data and ticker in ticker_mapping:
                print("⚠️ [Scraper] Cached URL yielded no news — invalidating & retrying...")
                old_url = ticker_mapping.pop(ticker)
                cache_file.write_text(json.dumps(ticker_mapping, indent=2))

                # new_url = await _strategy_api(page, ticker)
                # if not new_url:
                #     new_url = await _strategy_search_page(page, ticker)
                # if not new_url:
                new_url = await _strategy_ui(page, ticker)

                if new_url and new_url != old_url:
                    ticker_mapping[ticker] = new_url
                    cache_file.write_text(json.dumps(ticker_mapping, indent=2))
                    news_data = await _scrape_news_page(page, new_url, ticker)

        except Exception as e:
            print(f"❌ [Scraper] Fatal: {e}")
        finally:
            await browser.close()

    print(f"✅ [Scraper] Done — {len(news_data)} item(s) for {ticker}")
    return news_data