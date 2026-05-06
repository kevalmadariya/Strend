from src.core.db import get_db_connection

def create_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            print("Creating 'learnings' table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS learnings (
                    learning_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    learning TEXT NOT NULL,
                    exceptions TEXT,
                    sentiment INTEGER,
                    event TEXT
                );
            """)
            conn.commit()
            print("Table 'learnings' created successfully.")
    except Exception as e:
        print(f"Error creating table: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_table()
