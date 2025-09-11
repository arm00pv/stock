import sqlite3
from datetime import datetime, timedelta

DB_NAME = 'stocks.db'

def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Utility function to safely add a column to a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [info[1] for info in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"Added '{column_name}' column to '{table_name}' table.")

def init_db():
    """
    Initializes the database and creates/updates tables as needed.
    Includes logic to handle migration from single-portfolio to multi-portfolio schema.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # --- Stocks Table (unchanged) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT NOT NULL,
            category TEXT NOT NULL,
            date_added TEXT NOT NULL,
            PRIMARY KEY (ticker, category)
        )
    ''')
    _add_column_if_not_exists(cursor, 'stocks', 'source_url', 'TEXT')
    _add_column_if_not_exists(cursor, 'stocks', 'last_seen_date', 'TEXT')

    # --- Portfolio Tables Migration and Creation ---

    # Check if the old portfolio_summary table exists (by checking for the old primary key `id`)
    cursor.execute("PRAGMA table_info(portfolio_summary)")
    summary_columns = [info[1] for info in cursor.fetchall()]

    if 'id' in summary_columns:
        print("Old portfolio_summary table detected. Migrating data...")
        # 1. Rename old table
        cursor.execute("ALTER TABLE portfolio_summary RENAME TO portfolio_summary_old")
        # 2. Create new table
        cursor.execute('''
            CREATE TABLE portfolio_summary (
                portfolio_name TEXT PRIMARY KEY,
                cash_balance REAL NOT NULL,
                total_invested REAL NOT NULL
            )
        ''')
        # 3. Copy data, assigning it to the 'main' portfolio
        cursor.execute('''
            INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested)
            SELECT 'main', cash_balance, total_invested
            FROM portfolio_summary_old
        ''')
        # 4. Drop old table
        cursor.execute("DROP TABLE portfolio_summary_old")
        print("Migration of portfolio_summary complete.")

    # Safely create the table if it doesn't exist at all
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_summary (
            portfolio_name TEXT PRIMARY KEY,
            cash_balance REAL NOT NULL,
            total_invested REAL NOT NULL
        )
    ''')

    # Create transactions table and add portfolio_name column if needed
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            purchase_price REAL NOT NULL,
            purchase_date TEXT NOT NULL
        )
    ''')
    _add_column_if_not_exists(cursor, 'portfolio_transactions', 'portfolio_name', "TEXT NOT NULL DEFAULT 'main'")


    # Initialize default portfolios if they don't exist
    portfolios_to_init = ['main', 'monthly_dividend']
    for p_name in portfolios_to_init:
        cursor.execute('SELECT COUNT(*) FROM portfolio_summary WHERE portfolio_name = ?', (p_name,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested) VALUES (?, 0, 0)', (p_name,))

    conn.commit()
    conn.close()
    print("Database initialized/updated for multiple portfolios.")

# ... (rest of the file is the same as the last correct version) ...

def update_tickers_from_source(tickers, category, source_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    new_tickers_added, tickers_updated = 0, 0
    for ticker in tickers:
        try:
            cursor.execute('INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date) VALUES (?, ?, ?, ?, ?)', (ticker, category, today_str, source_url, today_str))
            new_tickers_added += 1
        except sqlite3.IntegrityError:
            cursor.execute('UPDATE stocks SET last_seen_date = ?, source_url = ? WHERE ticker = ? AND category = ?', (today_str, source_url, ticker, category))
            tickers_updated += 1
    conn.commit()
    conn.close()
    print(f"Source: {source_url}\n - Added {new_tickers_added} new tickers.\n - Refreshed {tickers_updated} existing tickers.")

def get_tickers_by_category(category):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM stocks WHERE category = ?', (category,))
    tickers = [item[0] for item in cursor.fetchall()]
    conn.close()
    return tickers

def replace_tickers_for_category(tickers, category):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    source_url = 'manual_update'
    try:
        cursor.execute('DELETE FROM stocks WHERE category = ?', (category,))
        for ticker in tickers:
            cursor.execute('INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date) VALUES (?, ?, ?, ?, ?)', (ticker, category, today_str, source_url, today_str))
        conn.commit()
        print(f"Successfully replaced with {len(tickers)} new tickers for '{category}'.")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during ticker replacement: {e}")
    finally:
        conn.close()

def prune_old_tickers(days_old=30):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cutoff_date_str = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')
    try:
        cursor.execute("DELETE FROM stocks WHERE last_seen_date < ?", (cutoff_date_str,))
        conn.commit()
        print(f"Pruned {cursor.rowcount} old tickers not seen since {cutoff_date_str}.")
    except sqlite3.Error as e:
        print(f"Database error during pruning: {e}")
    finally:
        conn.close()

def get_portfolio_summary(portfolio_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = ?', (portfolio_name,))
    summary = cursor.fetchone()
    conn.close()
    return summary if summary else (0, 0)

def get_portfolio_holdings(portfolio_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker, shares, purchase_price, purchase_date FROM portfolio_transactions WHERE portfolio_name = ? ORDER BY purchase_date DESC', (portfolio_name,))
    holdings = cursor.fetchall()
    conn.close()
    return holdings

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = ?', (portfolio_name,))
        cash, total_invested = cursor.fetchone()

        new_cash = cash + investment_amount
        new_total_invested = total_invested + investment_amount
        cost = shares * price
        new_cash -= cost

        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT INTO portfolio_transactions (portfolio_name, ticker, shares, purchase_price, purchase_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (portfolio_name, ticker, shares, price, today_str))

        cursor.execute('UPDATE portfolio_summary SET cash_balance = ?, total_invested = ? WHERE portfolio_name = ?', (new_cash, new_total_invested, portfolio_name))

        conn.commit()
        print(f"Successfully executed investment for '{portfolio_name}': Bought {shares:.4f} shares of {ticker} at ${price:.2f}")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during investment for '{portfolio_name}': {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
