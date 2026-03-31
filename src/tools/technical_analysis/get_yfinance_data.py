import psycopg2
import yfinance as yf
from datetime import date

def normalize_ticker(ticker: str) -> str:
    if "." not in ticker:
        return f"{ticker}.NS"
    return ticker

def get_yfinance_data(ticker_symbol):
    try:
        ticker_symbol = normalize_ticker(ticker_symbol)
        only_ticker = ticker_symbol.split(".")[0]
        stock = yf.Ticker(ticker_symbol)
        info = stock.info

        if not info:
            print("❌ Empty info from yfinance")
            return None

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None:
            print("❌ Invalid ticker or no price")
            return None

        previous_close = (
            info.get("previousClose")
            or info.get("regularMarketPreviousClose")
            or current_price
        )

        p_change = info.get("regularMarketChangePercent")
        if p_change is None:
            p_change = (
                ((current_price - previous_close) / previous_close) * 100
                if previous_close else 0.0
            )

        stock_data = {
            "name": info.get("longName") or info.get("shortName") or ticker_symbol,
            "ticker": only_ticker,
            "price": float(current_price),
            "volume": float(info.get("volume") or info.get("regularMarketVolume") or 0),
            "percent_change": float(p_change),
            "open": float(info.get("open") or info.get("regularMarketOpen") or 0),
            "high": float(info.get("dayHigh") or info.get("regularMarketDayHigh") or 0),
            "low": float(info.get("dayLow") or info.get("regularMarketDayLow") or 0),
            "close": float(previous_close),
        }

        print(f"📊 Data Received: {stock_data}")

        # ---------------- DB INSERT ----------------
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        db_config = {
            "host": os.getenv("DB_HOST", "127.0.0.1"),
            "port": os.getenv("DB_PORT", "5433"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "12345"),
        }

        conn = None
        cur = None

        try:
            conn = psycopg2.connect(**db_config)
            conn.autocommit = False
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock (
                    stock_id SERIAL PRIMARY KEY,
                    name TEXT,
                    date DATE DEFAULT CURRENT_DATE,
                    ticker TEXT,
                    price FLOAT,
                    volume FLOAT,
                    percent_change FLOAT,
                    close FLOAT,
                    high FLOAT,
                    open FLOAT,
                    low FLOAT,
                    UNIQUE (ticker, date)
                );
            """)

            # Check if ticker already exists to update instead of insert
            cur.execute("SELECT stock_id FROM stock WHERE ticker = %s ORDER BY date DESC LIMIT 1", (stock_data["ticker"],))
            existing_stock = cur.fetchone()

            if existing_stock:
                cur.execute("""
                    UPDATE stock SET
                        price = %s,
                        volume = %s,
                        percent_change = %s,
                        close = %s,
                        high = %s,
                        open = %s,
                        low = %s,
                        date = %s
                    WHERE stock_id = %s
                """, (
                    stock_data["price"],
                    stock_data["volume"],
                    stock_data["percent_change"],
                    stock_data["close"],
                    stock_data["high"],
                    stock_data["open"],
                    stock_data["low"],
                    date.today(),
                    existing_stock[0]
                ))

                # Clean up any other duplicates for this ticker to prevent table growth
                # cur.execute("DELETE FROM stock WHERE ticker = %s AND stock_id != %s", (stock_data["ticker"], existing_stock[0]))
                
                conn.commit()
                print(f"🔄 Data for {stock_data['ticker']} updated in DB.")

            else:
                cur.execute("""
                    INSERT INTO stock (
                        name, ticker, price, volume, percent_change,
                        close, high, open, low, date
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    stock_data["name"],
                    stock_data["ticker"],
                    stock_data["price"],
                    stock_data["volume"],
                    stock_data["percent_change"],
                    stock_data["close"],
                    stock_data["high"],
                    stock_data["open"],
                    stock_data["low"],
                    date.today()
                ))
                
                conn.commit()
                print(f"💾 Data for {stock_data['ticker']} saved to DB.")

        except Exception as db_err:
            if conn:
                conn.rollback()
            print(f"❌ DB INSERT ERROR: {db_err}")

        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

        return {
            "status": "completed",
            "results": stock_data
        }

    except Exception as e:
        print(f"⚠️ yfinance internal error: {e}")
        return None
