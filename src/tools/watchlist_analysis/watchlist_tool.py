import json
from typing import Optional, List
from datetime import date
from src.core.db import get_db_connection
from ..base import DynamicTool, ToolParam

def makeTool(router):
    
    def func(unique_id):
        
        async def manage_watchlist(action: str, name: Optional[str] = None, new_name: Optional[str] = None, description: Optional[str] = None):
            """
            Manage watchlists: create, update, delete, or get.
            Identifies watchlists by name for the current user.
            """
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

            try:
                if action == "create":
                    if not name:
                         yield "❌ Error: 'name' is required for creating a watchlist.\n"
                         return

                    # Check if already exists for this user with same name
                    cur.execute("SELECT watchlist_id FROM watchlist WHERE name = %s AND user_id = %s", (name, user_id))
                    res = cur.fetchone()
                    if res:
                        yield f"ℹ️ Watchlist '{name}' already exists (ID: {res[0]}).\n"
                        yield json.dumps({"status": "exists", "watchlist_id": res[0], "name": name})
                        return

                    cur.execute("""
                        INSERT INTO watchlist (user_id, date, name, description)
                        VALUES (%s, %s, %s, %s)
                        RETURNING watchlist_id
                    """, (user_id, date.today(), name, description))
                    new_id = cur.fetchone()[0]
                    conn.commit()
                    yield f"✅ Watchlist '{name}' created successfully.\n"
                    yield json.dumps({"status": "created", "watchlist_id": new_id, "name": name})

                elif action == "update":
                    if not name:
                        yield "❌ Error: 'name' is required to identify the watchlist for updating.\n"
                        return
                    
                    # Find watchlist_id
                    cur.execute("SELECT watchlist_id FROM watchlist WHERE name = %s AND user_id = %s", (name, user_id))
                    res = cur.fetchone()
                    if not res:
                        yield f"❌ Watchlist '{name}' not found.\n"
                        return
                    watchlist_id = res[0]
                    
                    # Build update query dynamically
                    updates = []
                    params = []
                    if new_name:
                        updates.append("name = %s")
                        params.append(new_name)
                    if description:
                        updates.append("description = %s")
                        params.append(description)
                    
                    if not updates:
                         yield "ℹ️ No changes provided for update.\n"
                         return

                    params.append(watchlist_id)
                    
                    query = f"UPDATE watchlist SET {', '.join(updates)} WHERE watchlist_id = %s RETURNING watchlist_id"
                    cur.execute(query, tuple(params))
                    if cur.fetchone():
                        conn.commit()
                        yield f"✅ Watchlist '{name}' updated.\n"
                        yield json.dumps({"status": "updated", "watchlist_id": watchlist_id, "name": new_name or name})
                    else:
                        yield f"❌ Update failed for watchlist '{name}'.\n"

                elif action == "delete":
                    if not name:
                        yield "❌ Error: 'name' is required for deletion.\n"
                        return

                    cur.execute("SELECT watchlist_id FROM watchlist WHERE name = %s AND user_id = %s", (name, user_id))
                    res = cur.fetchone()
                    if not res:
                        yield f"❌ Watchlist '{name}' not found.\n"
                        return
                    watchlist_id = res[0]

                    cur.execute("DELETE FROM watchlist_stocks WHERE watchlist_id = %s", (watchlist_id,))
                    cur.execute("DELETE FROM watchlist WHERE watchlist_id = %s", (watchlist_id,))
                    
                    conn.commit()
                    yield f"✅ Watchlist '{name}' deleted.\n"
                    yield json.dumps({"status": "deleted", "watchlist_id": watchlist_id, "name": name})

                elif action == "get":
                    if name:
                        cur.execute("SELECT watchlist_id, name, description, date FROM watchlist WHERE name = %s AND user_id = %s", (name, user_id))
                        row = cur.fetchone()
                        if row:
                            data = {"watchlist_id": row[0], "name": row[1], "description": row[2], "date": str(row[3])}
                            yield f"Found Watchlist: {data}\n"
                            yield json.dumps(data)
                        else:
                            yield f"❌ Watchlist '{name}' not found.\n"
                    else:
                        # List all
                        cur.execute("SELECT watchlist_id, name, description, date FROM watchlist WHERE user_id = %s ORDER BY watchlist_id", (user_id,))
                        rows = cur.fetchall()
                        data = [{"name": r[1], "description": r[2], "date": str(r[3])} for r in rows]
                        yield f"Found {len(data)} watchlists.\n"
                        yield json.dumps({"status" : "success" , "data" : data})

                else:
                    yield f"❌ Invalid action: {action}\n"

            except Exception as e:
                conn.rollback()
                yield f"❌ Error: {e}\n"
            finally:
                conn.close()

        return DynamicTool(
            name="manage_watchlist",
            description="Create, update, delete, or get watchlists. Identify watchlists by name.",
            triggers=["Create watchlist", "Update watchlist", "Delete watchlist", "List watchlists"],
            function=manage_watchlist,
            parameters=[
                ToolParam(name="action", type="string", required=True, description="Action to perform: 'create', 'update', 'delete', 'get'"),
                ToolParam(name="name", type="string", required=False, description="Name of the watchlist (required for create, update, delete; optional for get)"),
                ToolParam(name="new_name", type="string", required=False, description="New name for the watchlist (optional, for update)"),
                ToolParam(name="description", type="string", required=False, description="Description of the watchlist")
            ],
            endpoint="/manage-watchlist",
            router=router
        )

    return func
