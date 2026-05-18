import asyncio
import os
import sys
import re
import json
from pathlib import Path
from playwright.async_api import async_playwright

# Ensure Proactor on Windows is used (copied from chart_capture.py)
if os.getenv("ENVIRONMENT_OS", sys.platform) == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Import helpers from news_scraper to avoid duplication and maintain consistency
from src.tools.utils.news_scraper import (
    dismiss_overlays,
    _resolve_search_input,
    _STOCK_URL_KEYWORDS,
)

def _project_root() -> Path:
    # File lives at src/tools/utils/market_depth_capture.py -> 4 levels up to root
    return Path(__file__).resolve().parent.parent.parent.parent

def _cache_file() -> Path:
    return _project_root() / "cache" / "strategy" / "ticker_mapping.json"

def safe_print(message: str):
    """Safely prints message avoiding Windows unicode/charmap encode errors."""
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            # Fallback: encode/decode to clean up non-representable chars
            print(message.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
        except Exception:
            # Fallback to ascii representation
            print(message.encode('ascii', errors='replace').decode('ascii'))

async def _find_market_depth_section(page):
    """
    Locate the Market Depth container using resilient content-based heuristics.
    """
    # Strategy 1: Find heading matching "Market depth" (case-insensitive) and return parent
    try:
        headings = page.locator("h1, h2, h3, h4, h5, h6")
        count = await headings.count()
        for i in range(count):
            h = headings.nth(i)
            text = (await h.inner_text()).strip()
            if re.search(r"market\s*depth", text, re.IGNORECASE):
                # The parent div wraps the heading and the depth table
                parent = h.locator("xpath=..")
                if await parent.is_visible():
                    safe_print("  [Depth Capture] Found section via Strategy 1 (heading match)")
                    return parent
    except Exception as e:
        safe_print(f"  [Depth Capture] Strategy 1 failed: {e}")

    # Strategy 2: Find stable id anchor "#stkLASection"
    try:
        section = page.locator("#stkLASection")
        if await section.count() > 0 and await section.first.is_visible():
            safe_print("  [Depth Capture] Found section via Strategy 2 (#stkLASection id)")
            return section.first
    except Exception as e:
        safe_print(f"  [Depth Capture] Strategy 2 failed: {e}")

    # Strategy 3: Find elements containing both "Bid Price" and "Ask Price"
    try:
        xpath = "//div[.//*[contains(text(),'Bid Price')] and .//*[contains(text(),'Ask Price')]]"
        candidates = page.locator(xpath)
        count = await candidates.count()
        for i in range(count):
            candidate = candidates.nth(i)
            if await candidate.is_visible():
                safe_print("  [Depth Capture] Found section via Strategy 3 (Bid/Ask text matching)")
                return candidate
    except Exception as e:
        safe_print(f"  [Depth Capture] Strategy 3 failed: {e}")

    return None

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
                        If None, the function checks the news_scraper cache or searches via UI.

    Returns:
        Absolute path to the saved PNG on success, or None on failure.
    """
    safe_print(f"\n[Depth Capture] Starting market depth capture for: {ticker} (Slot: {slot_label})")

    # Resolve URL
    resolved_url = stock_page_url
    if not resolved_url:
        cache_path = _cache_file()
        if cache_path.exists():
            try:
                ticker_mapping = json.loads(cache_path.read_text())
                resolved_url = ticker_mapping.get(ticker)
                if resolved_url:
                    safe_print(f"  [Depth Capture] Resolved URL from cache: {resolved_url}")
            except Exception as e:
                safe_print(f"  [Depth Capture] Failed to read cache file: {e}")

    # Clean the URL to point to the main stock page (strip /market-news or similar suffix)
    if resolved_url:
        resolved_url = re.sub(r"/(market-)?news/?$", "", resolved_url.strip()).rstrip("/")

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
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Navigate to page
            if resolved_url:
                safe_print(f"  [Depth Capture] Navigating directly to: {resolved_url}")
                await page.goto(resolved_url, timeout=40000)
            else:
                safe_print("  [Depth Capture] URL not cached. Executing UI search...")
                await page.goto("https://groww.in/", timeout=40000)
                await dismiss_overlays(page)

                inp = await _resolve_search_input(page)
                if not inp:
                    safe_print("  [Depth Capture] Search input not found.")
                    return None

                await inp.wait_for(state="visible", timeout=8000)
                await inp.fill("")
                await inp.type(ticker, delay=150)
                await page.wait_for_timeout(1500)
                await page.keyboard.press("Enter")

                # Wait for stock page URL pattern
                stock_found = False
                for pat in ["**/stocks/**", "**/equities/**", "**/stock/**", "**/shares/**"]:
                    try:
                        await page.wait_for_url(pat, timeout=5000)
                        stock_found = True
                        break
                    except Exception:
                        continue

                if not stock_found:
                    safe_print(f"  [Depth Capture] Did not reach stock page. Current URL: {page.url}")
                    return None

                # Clean resolved url
                resolved_url = page.url
                resolved_url = re.sub(r"/(market-)?news/?$", "", resolved_url.strip()).rstrip("/")
                if resolved_url != page.url:
                    await page.goto(resolved_url, timeout=30000)
                
                #cache it for future use
                new_resolved_url = resolved_url + "/market-news"
                cache_path.write_text(json.dumps({ticker: new_resolved_url}))

            await dismiss_overlays(page)
            # Extra wait for the market depth section/lazy elements to load
            await page.wait_for_timeout(3000)

            # Locate container
            container = await _find_market_depth_section(page)
            if not container:
                safe_print(f"  [Depth Capture] Could not locate Market Depth section for {ticker}")
                return None

            # Scroll and capture
            await container.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)  # let animations settle

            img_bytes = await container.screenshot(type="png")

            # Save to disk
            output_dir = _project_root() / "buyer_seller_details" / slot_label
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{ticker}.png"
            output_path.write_bytes(img_bytes)

            safe_print(f"  [Depth Capture] Saved screenshot to: {output_path}")
            return str(output_path)

        except Exception as e:
            safe_print(f"  [Depth Capture] Exception during capture for {ticker}: {e}")
            return None
        finally:
            await browser.close()
