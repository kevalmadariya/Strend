import json
from datetime import datetime, timedelta, time
import yfinance as yf
import pytz  # make sure pytz is installed
import pandas as pd


def analyze_stock_data(
    json_data,
    date=None,
    ticker_column_names=None,
    high_column_names=None,
    low_column_names=None,
    price_column_names=None,
    add_exchange_suffix=True,
    exchange_suffix='.NS',
    generation_time=None  # <-- NEW parameter
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