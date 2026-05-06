from typing import List, Dict
import os
from dotenv import load_dotenv

load_dotenv()

def filter_stocks(stocks_data: List[Dict]) -> List[Dict]:
    """
    Filters stocks based on criteria stored in environment variables or defaults.
    Default: Trend == 1 (Bullish) AND Price < 3000.
    """
    print(f"🔍 [Filtering Utils] Filtering {len(stocks_data)} stocks...")
    
    # Get criteria from Env
    max_price = float(os.getenv("FILTER_MAX_PRICE", "3000.0"))
    required_trend = int(os.getenv("FILTER_REQUIRED_TREND", "1"))
    
    filtered = []
    
    try:
        for stock in stocks_data:
            ticker = stock.get("ticker", "Unknown")
            
            # 1. Check Trend
            trend = stock.get("trend")
            if trend != required_trend:
                # print(f"   Skipping {ticker}: Trend {trend} != {required_trend}")
                continue
            
            # 2. Check Price
            price_raw = stock.get("price", 0.0)
            price = 0.0
            
            # Handle string prices like "1,200.50"
            if isinstance(price_raw, str):
                try:
                    price = float(price_raw.replace(",", "").strip())
                except ValueError:
                    print(f"⚠️ [Filtering Utils] Could not parse price for {ticker}: {price_raw}")
                    continue
            elif isinstance(price_raw, (int, float)):
                price = float(price_raw)
                
            if price >= max_price:
                # print(f"   Skipping {ticker}: Price {price} >= {max_price}")
                continue
                
            # If passed all checks
            filtered.append(stock)
            
        print(f"✅ [Filtering Utils] Filtered down to {len(filtered)} stocks.")
        return filtered

    except Exception as e:
        print(f"❌ [Filtering Utils] Error during filtering: {e}")
        return []
