import psycopg2
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5433"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "12345")
    )
    cur = conn.cursor()
    # Check if '8' exists, if not insert it.
    cur.execute("SELECT conversation_id FROM conversation WHERE conversation_id = '8'")
    if not cur.fetchone():
        # Insert minimal dummy data. Assuming agent_id=1 and user_id=4 exist from previous context, but user_id 4 might not exist if DB reset?
        # Let's check user 4.
        cur.execute("SELECT user_id FROM \"user\" WHERE user_id = 4")
        if not cur.fetchone():
             # Insert user 4 if missing (unlikely if user didn't drop user table, but best to be safe)
             # User table has id serial, so difficult to force 4 unless we change sequence or simple insert.
             # Actually user table was NOT dropped in my previous edits (only conversation tables were).
             pass
        
        # Insert conversation '8'
        # We need agent_id. Assuming 1 exists.
        try:
            cur.execute("INSERT INTO conversation (conversation_id, agent_id, title, user_id, date) VALUES ('8', 1, 'Restored Manual Conv', 4, CURRENT_DATE)")
            conn.commit()
            print("Inserted conversation 8")
        except Exception as e:
            print(f"Failed to insert 8: {e}")
            conn.rollback()
    else:
        print("Conversation 8 already exists")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
