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
    print("Successfully connected to the 'strend' database!")
    # ... your table creation code ...
    
except Exception as e:
    print(f"Connection failed: {e}")
    import sys
    sys.exit(1)

cur = conn.cursor()
# # SQL statements to create tables
# # 1:trading_bot , 2:fundamental_analysis_agent , 3:news_agent , 4:technical_analysis_agent , 5:watchlist_agent
create_tables_sql = [
    """
    CREATE TABLE IF NOT EXISTS agent (
        agent_id SERIAL PRIMARY KEY,
        template TEXT,
        user_id INT
    );
    """,
    """
    INSERT INTO agent (template, user_id) VALUES ('trading_bot', 1);
    INSERT INTO agent (template, user_id) VALUES ('fundamental_analysis_agent', 1);
    INSERT INTO agent (template, user_id) VALUES ('news_agent', 1);
    INSERT INTO agent (template, user_id) VALUES ('technical_analysis_agent', 1);
    INSERT INTO agent (template, user_id) VALUES ('watchlist_agent', 1);
    """,
    """
    CREATE TABLE IF NOT EXISTS "user" (
        user_id SERIAL PRIMARY KEY,
        name TEXT,
        email_id TEXT,
        password TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation (
        conversation_id SERIAL PRIMARY KEY,
        agent_id INT REFERENCES agent(agent_id),
        title TEXT,
        user_id INT REFERENCES "user"(user_id),
        date DATE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_message (
        message_id SERIAL PRIMARY KEY,
        conversation_id INT NOT NULL REFERENCES conversation(conversation_id) ON DELETE CASCADE,
        sender_type VARCHAR(10) CHECK (sender_type IN ('user', 'agent')),
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """,
    
    """CREATE TABLE IF NOT EXISTS stock (
    stock_id SERIAL PRIMARY KEY,
    name TEXT,
    date DATE DEFAULT CURRENT_DATE,  -- ✅ New Date Field (Defaults to today)
    ticker TEXT,
    price FLOAT,
    volume FLOAT,
    percent_change FLOAT,
    close FLOAT,
    high FLOAT,
    open FLOAT,
    low FLOAT,
    UNIQUE(ticker, date)             -- ✅ Unique Constraint
);
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        watchlist_id SERIAL PRIMARY KEY,
        user_id INT REFERENCES "user"(user_id),
        date DATE,
        name TEXT,
        description TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_stocks (
        watchlist_id INT REFERENCES watchlist(watchlist_id),
        stock_id INT REFERENCES stock(stock_id),
        price_of_stock_when_added FLOAT,
        date DATE default CURRENT_DATE,
        unique (watchlist_id, stock_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS technical_analysis (
        technical_analysis_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE default CURRENT_DATE,
        trend TEXT,
        chart_pattern TEXT,
        macd_12_26_9_macd FLOAT,
        macd_12_26_9_signal FLOAT,
        macd_12_26_9_histogram FLOAT,
        rsi_14 FLOAT,
        adx_14 FLOAT,
        chart_image BYTEA,
        unique (stock_id, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fundamental_analysis (
        fundamental_analysis_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE default CURRENT_DATE,
        industry TEXT,
        description TEXT,
        sector TEXT,
        price FLOAT,
        quickratio FLOAT,
        peg FLOAT,
        market_cap FLOAT,
        enterprise_value FLOAT,
        no_of_shares FLOAT,
        p_e FLOAT,
        p_b FLOAT,
        face_value FLOAT,
        div_yield FLOAT,
        book_value_ttm FLOAT,
        cash FLOAT,
        debt FLOAT,
        promoter_holding FLOAT,
        eps_ttm FLOAT,
        sales_growth FLOAT,
        roe FLOAT,
        roce FLOAT,
        profit_growth FLOAT,
        cfo_pat_5_yr_avg FLOAT,
        debt_equity FLOAT,
        interest_cover_ratio FLOAT,
        strengths TEXT,
        limitations TEXT,
        news TEXT,
        promoter_q1 FLOAT,
        promoter_q2 FLOAT,
        promoter_q3 FLOAT,
        promoter_q4 FLOAT,
        pledge_q1 FLOAT,
        pledge_q2 FLOAT,
        pledge_q3 FLOAT,
        pledge_q4 FLOAT,
        fiis_q1 FLOAT,
        fiis_q2 FLOAT,
        fiis_q3 FLOAT,
        fiis_q4 FLOAT,
        diis_q1 FLOAT,
        diis_q2 FLOAT,
        diis_q3 FLOAT,
        diis_q4 FLOAT,
        government_q1 FLOAT,
        government_q2 FLOAT,
        government_q3 FLOAT,
        government_q4 FLOAT,
        public_q1 FLOAT,
        public_q2 FLOAT,
        public_q3 FLOAT,
        public_q4 FLOAT,
        UNIQUE (stock_id, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fundamental_results (
        fundamental_analysis_id INT REFERENCES fundamental_analysis(fundamental_analysis_id),
        date DATE default CURRENT_DATE,     
        total_score FLOAT,
        score_percentage FLOAT,
        rating TEXT,
        risk_level TEXT,
        earnings_yield_score FLOAT,
        profit_growth_score FLOAT,
        sales_growth_score FLOAT,
        pe_ratio_score FLOAT,
        debt_to_equity_score FLOAT,
        roe_dividend_score FLOAT,
        promoter_dii_fii_holding_score FLOAT,
        unique (fundamental_analysis_id, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS profit_and_loss_analysis (
        profit_and_loss_analysis_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE default CURRENT_DATE, 
        stop_loss FLOAT,
        profit FLOAT,
        support FLOAT,
        resistance FLOAT,
        fibonacci_retracement TEXT,
        unique (stock_id, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS news_analysis (
        news_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE default CURRENT_DATE,
        ago INT,
        news TEXT,
        url TEXT,
        unique (stock_id, date, ago)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS notification (
        notification_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE default CURRENT_DATE,
        notification TEXT,
        user_id INT REFERENCES "user"(user_id),
        watchlist_id INT REFERENCES watchlist(watchlist_id),
        unique (stock_id, date, user_id, watchlist_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction (
        prediction_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date DATE DEFAULT CURRENT_DATE,
        prediction TEXT,
        pdf_oid OID,
        UNIQUE (stock_id, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS comparison (
        comparison_id SERIAL PRIMARY KEY,
        stock_id INT REFERENCES stock(stock_id),
        date_added_into_watchlist DATE,
        date_of_comparison DATE default CURRENT_DATE,
        percent_change FLOAT,   
        percent_change_from_watchlist FLOAT,    
        comparison TEXT,
        is_positive BOOLEAN,
        unique (stock_id, date_added_into_watchlist, date_of_comparison)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS techincal_stocks (
        method TEXT,
        ticker  TEXT,
        date DATE default CURRENT_DATE,
        stock_name TEXT,
        volume FLOAT,
        price FLOAT,
        percent_change FLOAT,
        unique (method, ticker, date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS learnings (
                    learning_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    learning TEXT NOT NULL,
                    exceptions TEXT,
                    sentiment INTEGER,
                    event TEXT
    );"""
]

# Execute all table creation statements
for stmt in create_tables_sql:
    cur.execute(stmt)

conn.commit()
cur.close()
conn.close()

print("All tables created successfully in PostgreSQL database!")
