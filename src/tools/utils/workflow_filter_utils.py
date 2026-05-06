"""
Workflow Filter Utilities
=========================
Generic filter engine for the workflow pipeline.
Supports filtering stock data by volume, price, %change, and
technical/fundamental indicators using operator-based rules.
"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("workflow_filter_utils")


# ---------------------------------------------------------------------------
# Operator helpers
# ---------------------------------------------------------------------------

OPERATOR_MAP = {
    "greater": lambda a, b: a > b,
    "greater_equal": lambda a, b: a >= b,
    "less": lambda a, b: a < b,
    "less_equal": lambda a, b: a <= b,
    "equals": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
}


def _parse_number(value) -> float:
    """Safely parse a formatted number string (handles commas, spaces, etc.)."""
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(value))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def _apply_operator(field_value: float, operator: str, target_value: float) -> bool:
    """Apply comparison operator."""
    op_func = OPERATOR_MAP.get(operator)
    if not op_func:
        logger.warning(f"⚠️ Unknown operator '{operator}', defaulting to 'greater'")
        op_func = OPERATOR_MAP["greater"]
    return op_func(field_value, target_value)


# ---------------------------------------------------------------------------
# Stock-level filter (volume, price, %change)
# ---------------------------------------------------------------------------

# Map user-facing field names to the keys in stock dicts
STOCK_FIELD_MAP = {
    "volume": "volume",
    "vol": "volume",
    "min_price": "price",
    "max_price": "price",
    "price": "price",
    "percent_change": "percent_change",
    "%chg": "percent_change",
    "chg": "percent_change",
}


def apply_stock_filters(stocks: List[Dict], filters: List[Dict]) -> List[Dict]:
    """
    Filter a list of stock dicts based on operator rules.

    Each filter: {"field": "volume", "operator": "greater", "value": 50000}

    Supported fields: volume, min_price, max_price, price, percent_change / %chg
    """
    if not filters:
        return stocks

    logger.info(f"🔍 Applying {len(filters)} stock filter(s) to {len(stocks)} stocks...")

    result = []
    for stock in stocks:
        passed = True
        for f in filters:
            field = f.get("field", "").lower().strip()
            operator = f.get("operator", "greater").lower().strip()
            value = float(f.get("value", 0))

            stock_key = STOCK_FIELD_MAP.get(field, field)
            stock_val = _parse_number(stock.get(stock_key, 0))

            if not _apply_operator(stock_val, operator, value):
                passed = False
                break

        if passed:
            result.append(stock)

    logger.info(f"✅ Stock filters: {len(result)}/{len(stocks)} passed")
    return result


# ---------------------------------------------------------------------------
# Technical Analysis filter (trend, macd, rsi_value, adx)
# ---------------------------------------------------------------------------

TECH_FIELD_MAP = {
    "trend": "trend",
    "macd": "macd",
    "macd_signal": "macd_signal",
    "macd_hist": "macd_hist",
    "rsi_value": "rsi",
    "rsi": "rsi",
    "adx": "adx",
}


def apply_technical_filters(stocks: List[Dict], filters: List[Dict]) -> List[Dict]:
    """
    Filter stocks based on their technical analysis data.

    Each stock dict should have 'trend' and/or 'indicators' keys
    (populated by a prior technical_analysis step).

    Each filter: {"field": "rsi_value", "operator": "greater", "value": 50}
    """
    if not filters:
        return stocks

    logger.info(f"🔍 Applying {len(filters)} technical filter(s) to {len(stocks)} stocks...")

    result = []
    for stock in stocks:
        passed = True
        indicators = stock.get("indicators", {})

        for f in filters:
            field = f.get("field", "").lower().strip()
            operator = f.get("operator", "greater").lower().strip()
            value = float(f.get("value", 0))

            mapped = TECH_FIELD_MAP.get(field, field)

            if mapped == "trend":
                stock_val = float(stock.get("trend", 0))
            else:
                stock_val = float(indicators.get(mapped, 0))

            if not _apply_operator(stock_val, operator, value):
                passed = False
                break

        if passed:
            result.append(stock)

    logger.info(f"✅ Technical filters: {len(result)}/{len(stocks)} passed")
    return result


# ---------------------------------------------------------------------------
# Fundamental Analysis filter (score)
# ---------------------------------------------------------------------------

def apply_fundamental_filters(stocks: List[Dict], filters: List[Dict]) -> List[Dict]:
    """
    Filter stocks based on fundamental analysis score.

    Each stock dict should have 'fundamental_score' key
    (populated by a prior fundamental_analysis step).

    Each filter: {"field": "score", "operator": "greater", "value": 60}
    """
    if not filters:
        return stocks

    logger.info(f"🔍 Applying {len(filters)} fundamental filter(s) to {len(stocks)} stocks...")

    result = []
    for stock in stocks:
        passed = True
        fund_data = stock.get("fundamental_data", {})

        for f in filters:
            field = f.get("field", "").lower().strip()
            operator = f.get("operator", "greater").lower().strip()
            value = float(f.get("value", 0))

            if field in ("score", "score_percentage"):
                stock_val = float(fund_data.get("score_percentage", 0))
            elif field == "rating":
                # Skip string comparison for operator-based filters
                continue
            else:
                stock_val = float(fund_data.get(field, 0))

            if not _apply_operator(stock_val, operator, value):
                passed = False
                break

        if passed:
            result.append(stock)

    logger.info(f"✅ Fundamental filters: {len(result)}/{len(stocks)} passed")
    return result


# ---------------------------------------------------------------------------
# News Analysis filter (recent)
# ---------------------------------------------------------------------------

def apply_news_filters(stocks: List[Dict], filters: List[Dict]) -> List[Dict]:
    """
    Filter stocks based on news analysis.

    Each stock dict should have 'news' key (populated by a prior news_analysis step).

    Filter: {"field": "recent", "operator": "equals", "value": true}
    """
    if not filters:
        return stocks

    logger.info(f"🔍 Applying {len(filters)} news filter(s) to {len(stocks)} stocks...")

    result = []
    for stock in stocks:
        passed = True
        for f in filters:
            field = f.get("field", "").lower().strip()

            if field == "recent":
                has_recent = stock.get("has_recent_news", False)
                expected = bool(f.get("value", True))
                if has_recent != expected:
                    passed = False
                    break
            elif field == "count":
                news_count = len(stock.get("news", []))
                operator = f.get("operator", "greater").lower().strip()
                value = float(f.get("value", 0))
                if not _apply_operator(news_count, operator, value):
                    passed = False
                    break

        if passed:
            result.append(stock)

    logger.info(f"✅ News filters: {len(result)}/{len(stocks)} passed")
    return result
