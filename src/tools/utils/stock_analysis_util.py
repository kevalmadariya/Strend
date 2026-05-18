import json
import os
import re
from datetime import datetime, timedelta, time
import yfinance as yf
import pytz  # make sure pytz is installed
import pandas as pd
import pytesseract
from PIL import Image
import io


def analyze_stock_data(
    json_data,
    date=None,
    ticker_column_names=None,
    high_column_names=None,
    low_column_names=None,
    price_column_names=None,
    add_exchange_suffix=True,
    exchange_suffix='.NS',
    generation_time=None,  # <-- NEW parameter
    slot=None              # <-- NEW parameter
):
    """
    ... (docstring unchanged, but mention generation_time as optional "HHMM" string)
    """

    # Set default column names
    if ticker_column_names is None:
        ticker_column_names = ["ticker", "Ticker", "symbol", "Symbol"]
    if high_column_names is None:
        high_column_names = ["today_high", "Today_High", "todayhigh", "high", "High","todayHigh"]
    if low_column_names is None:
        low_column_names = ["today_low", "Today_Low", "todaylow", "low", "Low"]
    if price_column_names is None:
        price_column_names = ["price", "Price", "close", "Close"]

    try:
        # Parse input data (unchanged)
        if isinstance(json_data, str) and not json_data.strip().startswith('{') and not json_data.strip().startswith('['):
            return {
                "status": "error",
                "error": "Direct table name lookup not supported in util function. Use parsed data instead."
            }
        else:
            data = json.loads(json_data) if isinstance(json_data, str) else json_data

        columns, rows = parse_excel_json(data)

        # Parse date
        if date:
            try:
                date_str = str(date).split('T')[0].split()[0]
                target_date = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                return {
                    "status": "error",
                    "error": f"Invalid date format: {date}. Use YYYY-MM-DD format."
                }
        else:
            target_date = datetime.now()
        ticker_data_map = {}

        # Set date range unchanged
        start_dt = target_date
        end_dt = target_date

        result_rows = []

        # Pre-process generation_time if provided
        gen_time_obj = None
        if generation_time:
            try:
                gen_time_obj = time(int(generation_time[:2]), int(generation_time[2:4]))
            except Exception:
                gen_time_obj = None  # fallback: treat as no time constraint

        # Locate the buyer_seller_details directory and corresponding slot folder dynamically
        current_dir = os.path.abspath(os.path.dirname(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
        buyer_seller_base = os.path.join(project_root, "buyer_seller_details")
        target_slot_folder = None
        if slot and os.path.exists(buyer_seller_base):
            for d in os.listdir(buyer_seller_base):
                if os.path.isdir(os.path.join(buyer_seller_base, d)) and slot in d:
                    target_slot_folder = os.path.join(buyer_seller_base, d)
                    break

        # Define expected OCR columns
        ocr_expected_cols = ['buy_order(%)', 'sell_order(%)', 'bid', 'ask']
        for i in range(1, 6):
            ocr_expected_cols.extend([f'bid_price_{i}', f'bid_qty_{i}', f'ask_price_{i}', f'ask_qty_{i}'])

        for idx, row in enumerate(rows):
            ticker = _find_column_value(row, ticker_column_names)

            if not ticker:
                # unchanged fallback
                result_row = row.copy()
                result_row["actual_high"] = None
                result_row["is_high"] = None
                result_row["actual_low"] = None
                result_row["is_low"] = None
                result_row["gain"] = None
                result_row["reverse_gain"] = None
                for col in ocr_expected_cols:
                    result_row[col] = None
                result_rows.append(result_row)
                continue

            try:
                ticker_symbol = ticker
                if add_exchange_suffix and not ticker_symbol.endswith('.NS') and not ticker_symbol.endswith('.BO'):
                    ticker_symbol += exchange_suffix

                # Download daily data (UNCHANGED)
                stocks = yf.download(
                    ticker_symbol,
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval='1d',
                    group_by='ticker',
                    auto_adjust=False,
                    progress=False
                )

                # Extract actual daily high and low (UNCHANGED)
                actual_high = None
                actual_low = None
                if not stocks.empty:
                    if 'High' in stocks.columns:
                        actual_high = float(stocks['High'].iloc[0])
                    else:
                        try:
                            actual_high = float(stocks[(ticker_symbol, 'High')].iloc[0])
                        except:
                            actual_high = None

                    if 'Low' in stocks.columns:
                        actual_low = float(stocks['Low'].iloc[0])
                    else:
                        try:
                            actual_low = float(stocks[(ticker_symbol, 'Low')].iloc[0])
                        except:
                            actual_low = None

                # -- Extract row values (UNCHANGED) --
                result_row = row.copy()
                result_row["actual_high"] = actual_high
                result_row["actual_low"] = actual_low
                result_row["future_high"] = None
                result_row["future_low"] = None
                
                price = _find_column_value(row, price_column_names)
                today_low = _find_column_value(row, low_column_names) or price
                today_high = _find_column_value(row, high_column_names) or price
                
                # Default (daily-based) calculations (preserve original)
                if today_high is not None and actual_high is not None:
                    try:
                        result_row["is_high"] = 1 if float(today_high) < actual_high else 0
                    except (ValueError, TypeError):
                        result_row["is_high"] = None
                else:
                    result_row["is_high"] = None

                if today_low is not None and actual_low is not None:
                    try:
                        result_row["is_low"] = 1 if float(today_low) > actual_low else 0
                    except (ValueError, TypeError):
                        result_row["is_low"] = None
                else:
                    result_row["is_low"] = None

                # Gain from daily high (UNCHANGED)
                if actual_high is not None and price is not None:
                    try:
                        if result_row["is_high"] == 1:
                            result_row["gain"] = round(actual_high - float(price), 2)
                        else:
                            result_row["gain"] = 0
                    except (ValueError, TypeError):
                        result_row["gain"] = 0
                else:
                    result_row["gain"] = 0

                # Reverse gain from daily low (UNCHANGED)
                if actual_low is not None and price is not None:
                    try:
                        if result_row["is_low"] == 1:
                            result_row["reverse_gain"] = round(float(price) - actual_low, 2)
                        else:
                            result_row["reverse_gain"] = 0
                    except (ValueError, TypeError):
                        result_row["reverse_gain"] = 0
                else:
                    result_row["reverse_gain"] = 0

                # -------------------------------------------------------
                # NEW: Fallback to intraday 15-min data if needed
                # -------------------------------------------------------
                if generation_time and gen_time_obj and not stocks.empty:
                    if True:
                        # Fetch intraday 15-minute bars
                        try:
                            intraday = yf.download(
                                ticker_symbol,
                                start=start_dt.strftime("%Y-%m-%d"),
                                end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                                interval='15m',
                                group_by='ticker',
                                auto_adjust=False,
                                progress=False
                            )

                            if not intraday.empty:
                                # Convert UTC timestamps to IST (Asia/Kolkata)
                                ist = pytz.timezone('Asia/Kolkata')
                                if intraday.index.tz is None:
                                    intraday.index = intraday.index.tz_localize('UTC')
                                intraday_ist = intraday.index.tz_convert(ist)

                                # Filter bars on target date and after generation_time
                                future_bars = intraday[(intraday_ist.date == start_dt.date()) & (intraday_ist.time > gen_time_obj)]

                                if not future_bars.empty:
                                    # Extract high and low columns (handle MultiIndex)
                                    try:
                                        future_high_vals = future_bars['High']
                                    except KeyError:
                                        future_high_vals = future_bars[(ticker_symbol, 'High')]
                                    try:
                                        future_low_vals = future_bars['Low']
                                    except KeyError:
                                        future_low_vals = future_bars[(ticker_symbol, 'Low')]

                                    future_high = float(future_high_vals.max())
                                    future_low = float(future_low_vals.min())

                                    result_row["future_high"] = future_high
                                    result_row["future_low"] = future_low

                                    if price is not None:
                                        result_row["gain"] = round(future_high - float(price), 2)
                                        result_row["reverse_gain"] = round(float(price) - future_low, 2)
                                        result_row["is_high"] = 1 if result_row["gain"] > 0 else 0
                                        result_row["is_low"] = 1 if result_row["reverse_gain"] > 0 else 0
                        except Exception as e:
                            # Intraday fetch failed -> keep daily-based result (no break)
                            pass

                # -------------------------------------------------------
                # NEW: Perform OCR if target_slot_folder is found
                # -------------------------------------------------------
                ocr_data = {}
                if target_slot_folder:
                    img_path = os.path.join(target_slot_folder, f"{ticker}.png")
                    if os.path.exists(img_path):
                        ocr_text = perform_ocr_on_image(img_path)
                        ocr_data = parse_market_depth_ocr(ocr_text)

                # Append OCR columns at the very end to guarantee they appear last
                for col in ocr_expected_cols:
                    result_row[col] = ocr_data.get(col, None)

                result_rows.append(result_row)

            except Exception as e:
                # unchanged error fallback
                result_row = row.copy()
                result_row["actual_high"] = None
                result_row["is_high"] = None
                result_row["actual_low"] = None
                result_row["is_low"] = None
                result_row["gain"] = 0
                result_row["reverse_gain"] = 0
                result_row["error"] = f"Failed to fetch data for {ticker}: {str(e)}"
                for col in ocr_expected_cols:
                    result_row[col] = None
                result_rows.append(result_row)

        # Sort (unchanged)
        if result_rows and "roc_diff" in result_rows[0]:
            result_rows.sort(key=lambda x: x.get("roc_diff", 0) or 0, reverse=True)

        return {
            "status": "success",
            "data": {
                "file": result_rows,
            }
        }

    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid JSON format: {str(e)}"}
    except Exception as e:
        return {"status": "error", "error": f"Analysis failed: {str(e)}"}

def _find_column_value(row, column_names):
    """
    Helper function to find a value in a row by checking multiple possible column names.
    
    Args:
        row (dict): Row data
        column_names (list): List of possible column names to check
    
    Returns:
        The value if found, None otherwise
    """
    for col_name in column_names:
        value = row.get(col_name)
        if value is not None:
            return value
    return None


def parse_excel_json(data):
    """
    Parse Excel JSON data into columns and rows.
    
    Args:
        data (dict): Data dictionary with 'file' key containing list of row dictionaries
    
    Returns:
        tuple: (columns, rows) where columns is a list of column names and rows is a list of dictionaries
    """
    if isinstance(data, dict) and "file" in data:
        rows = data["file"]
        if rows and isinstance(rows[0], dict):
            columns = list(rows[0].keys())
            return columns, rows
    
    # If data is directly a list
    if isinstance(data, list):
        rows = data
        if rows and isinstance(rows[0], dict):
            columns = list(rows[0].keys())
            return columns, rows
    
    # Fallback
    return [], []


def perform_ocr_on_image(image_path):
    """
    Utility function for OCR that takes an image path and returns the text as a string.
    """
    import sys
    import shutil
    
    # Configure pytesseract path on Windows if tesseract is not in system PATH
    if sys.platform.startswith('win') and not shutil.which("tesseract"):
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
        ]
        for p in common_paths:
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break

    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        print(f"OCR Error for {image_path}: {e}")
        return ""


def parse_market_depth_ocr(text):
    """
    Parses market depth text extracted via OCR and returns a structured dictionary.
    """
    data = {}
    if not text:
        return data
    
    # Extract Buy/Sell %
    buy_sell_match = re.search(r'([\d\.]+)%\s+([\d\.]+)%', text)
    if buy_sell_match:
        data['buy_order(%)'] = float(buy_sell_match.group(1))
        data['sell_order(%)'] = float(buy_sell_match.group(2))
        
    # Extract rows of bid/ask
    rows = re.findall(r'([\d,\.]+)\s+(\d+)\D*\s+([\d,\.]+)\s+(\d+)', text)
    for i, r in enumerate(rows[:5]):
        data[f'bid_price_{i+1}'] = float(r[0].replace(',', '')) if r[0] else None
        data[f'bid_qty_{i+1}'] = int(r[1]) if r[1] else None
        data[f'ask_price_{i+1}'] = float(r[2].replace(',', '')) if r[2] else None
        data[f'ask_qty_{i+1}'] = int(r[3]) if r[3] else None
        
    # Extract Totals
    totals = re.search(r'Bid Total\s+([\d,\.]+)\s+Ask Total\s+([\d,\.]+)', text)
    if totals:
        data['bid'] = int(totals.group(1).replace(',', ''))
        data['ask'] = int(totals.group(2).replace(',', ''))
        
    return data