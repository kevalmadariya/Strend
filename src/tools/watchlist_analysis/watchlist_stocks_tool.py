import json
from typing import List, Optional
from datetime import date
from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from ..base import DynamicTool, ToolParam

def makeTool(router):
    
    def func(unique_id):
        
        async def manage_watchlist_stocks(action: str, tickers: List[str] = [], watchlist_name: Optional[str] = None):
            """
            Manage stocks in a watchlist: add, remove, or update.
            Identify watchlist by name. If name is not found or ambiguous, lists available watchlists.
            """
            # Ensure tickers is a list, even if passed as a string
            if isinstance(tickers, str):
                tickers = tickers.strip()
                try:
                    tickers = json.loads(tickers)
                except:
                    # Fallback for non-JSON string representations like "[TCS,UPL]"
                    cleaned = tickers.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
                    tickers = [t.strip() for t in cleaned.split(",") if t.strip()]

            conn = get_db_connection()
            cur = conn.cursor()
            
            # Get user_id from conversation table using the unique_id (conversation_id)
            cur.execute("SELECT user_id FROM conversation WHERE conversation_id = %s", (unique_id,))
            user_res = cur.fetchone()
            if not user_res:
                yield f"❌ Error: Conversation ID {unique_id} not found. Cannot determine User ID.\n"
                conn.close()
                return
            user_id = user_res[0]
            
            # Helper to list watchlists
            def list_watchlists():
                cur.execute("SELECT name FROM watchlist WHERE user_id = %s", (user_id,))
                rows = cur.fetchall()
                names = [r[0] for r in rows]
                return names

            watchlist_id = None
            if watchlist_name:
                cur.execute("SELECT watchlist_id FROM watchlist WHERE name = %s AND user_id = %s", (watchlist_name, user_id))
                res = cur.fetchone()
                if res:
                    watchlist_id = res[0]
                else:
                    yield f"❌ Watchlist '{watchlist_name}' not found.\n"
                    names = list_watchlists()
                    yield f"ℹ️ Available watchlists: {', '.join(names)}\n"
                    conn.close()
                    return
            else:
                yield "ℹ️ No watchlist name provided.\n"
                names = list_watchlists()
                yield f"ℹ️ Please specify one of the following watchlists: {', '.join(names)}\n"
                conn.close()
                return

            if not tickers and action in ['add', 'remove', 'update']:
                 yield f"❌ No tickers provided for action '{action}'.\n"
                 conn.close()
                 return

            yield f"🚀 Process Started for watchlist '{watchlist_name}' (ID: {watchlist_id}), Action: {action}\n"
            
            if action == 'get':
                 try:
                    cur.execute("""
                        SELECT s.ticker, ws.price_of_stock_when_added, ws.date
                        FROM watchlist_stocks ws
                        JOIN stock s ON ws.stock_id = s.stock_id
                        WHERE ws.watchlist_id = %s
                    """, (watchlist_id,))
                    rows = cur.fetchall()
                    stocks = [{"ticker": r[0], "added_price": r[1], "date": str(r[2])} for r in rows]
                    
                    yield f"   ✅ Found {len(stocks)} stocks in watchlist '{watchlist_name}'.\n"
                    conn.close()
                    yield json.dumps({"status": "success", "data": stocks})
                    return
                 except Exception as e:
                    yield f"   ❌ Error fetching stocks: {e}\n"
                    conn.close()
                    return

            results_summary = []

            for ticker in tickers:
                try:
                    # 1. Get Stock ID
                    # Check current date stock info
                    cur.execute("SELECT stock_id, price FROM stock WHERE ticker = %s AND date = CURRENT_DATE", (ticker,))
                    stock_res = cur.fetchone()
                    
                    stock_id = None
                    price = 0.0
                    
                    if stock_res:
                        stock_id = stock_res[0]
                        price = stock_res[1]
                    else:
                         yield f"   🆕 Stock {ticker} not found in DB or out of date. Fetching info...\n"
                         try:
                             # This helper inserts into DB if found
                             res = get_yfinance_data(ticker) 
                             if not res:
                                 yield f"   ⚠️ Could not fetch info for {ticker}. Skipping.\n"
                                 continue
                         except Exception as e:
                             yield f"   ⚠️ Error fetching {ticker}: {e}\n"
                             continue
                             
                         # Check again
                         cur.execute("SELECT stock_id, price FROM stock WHERE ticker = %s AND date = CURRENT_DATE", (ticker,))
                         res_retry = cur.fetchone()
                         if res_retry:
                            stock_id = res_retry[0]
                            price = res_retry[1]
                         else:
                            # Try with .NS 
                            cur.execute("SELECT stock_id, price FROM stock WHERE ticker = %s AND date = CURRENT_DATE", (f"{ticker}.NS",))
                            res_ns = cur.fetchone()
                            if res_ns:
                                stock_id = res_ns[0]
                                price = res_ns[1]
                            else:
                                 yield f"   ❌ Failed to find {ticker} in stock table after fetch.\n"
                                 continue

                    if action == "add":
                         cur.execute("SELECT 1 FROM watchlist_stocks WHERE watchlist_id = %s AND stock_id = %s", (watchlist_id, stock_id))
                         if cur.fetchone():
                            yield f"   ℹ️ {ticker} already in watchlist.\n"
                            results_summary.append({"ticker": ticker, "status": "exists"})
                         else:
                            cur.execute("""
                                INSERT INTO watchlist_stocks (watchlist_id, stock_id, price_of_stock_when_added, date)
                                VALUES (%s, %s, %s, %s)
                            """, (watchlist_id, stock_id, price, date.today()))
                            conn.commit()
                            yield f"   ✅ {ticker} added to watchlist.\n"
                            results_summary.append({"ticker": ticker, "status": "added", "price": price})

                    elif action == "remove":
                        cur.execute("DELETE FROM watchlist_stocks WHERE watchlist_id = %s AND stock_id = %s RETURNING stock_id", (watchlist_id, stock_id))
                        if cur.fetchone():
                            conn.commit()
                            yield f"   ✅ {ticker} removed from watchlist.\n"
                            results_summary.append({"ticker": ticker, "status": "removed"})
                        else:
                            yield f"   ℹ️ {ticker} not in watchlist.\n"
                            results_summary.append({"ticker": ticker, "status": "not_found"})
                            
                    elif action == "update":
                        # Update price/date to current
                        cur.execute("""
                            UPDATE watchlist_stocks 
                            SET price_of_stock_when_added = %s, date = %s 
                            WHERE watchlist_id = %s AND stock_id = %s 
                            RETURNING stock_id
                        """, (price, date.today(), watchlist_id, stock_id))
                        if cur.fetchone():
                            conn.commit()
                            yield f"   ✅ {ticker} updated in watchlist.\n"
                            results_summary.append({"ticker": ticker, "status": "updated", "price": price})
                        else:
                             yield f"   ℹ️ {ticker} not in watchlist to update.\n"
                             results_summary.append({"ticker": ticker, "status": "not_found"})


                        
                except Exception as e:
                    conn.rollback()
                    yield f"   ❌ Error processing {ticker if 'ticker' in locals() else 'request'}: {e}\n"

            conn.close()
            yield json.dumps({"status": "success", "results": results_summary})

        return DynamicTool(
            name="manage_watchlist_stocks",
            description="Add, remove, update or get stocks in a watchlist. Requires watchlist name.",
            triggers=["Add stocks to watchlist", "Remove stocks from watchlist", "Update watchlist stocks", "Get stocks from watchlist"],
            function=manage_watchlist_stocks,
            parameters=[
                ToolParam(name="action", type="string", required=True, description="Action: 'add', 'remove', 'update', 'get'"),
                ToolParam(name="watchlist_name", type="string", required=False, description="Name of the watchlist"),
                ToolParam(name="tickers", type="list", required=False, description="List of tickers (Required for add/remove/update, optional for get)")
            ],
            endpoint="/manage-watchlist-stocks",
            router=router
        )

    return func
