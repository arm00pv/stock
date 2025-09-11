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
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # --- Stocks Table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT NOT NULL,
            category TEXT NOT NULL,
            date_added TEXT NOT NULL,
            PRIMARY KEY (ticker, category)
        )
    ''')
    # Add new columns for source tracking
    _add_column_if_not_exists(cursor, 'stocks', 'source_url', 'TEXT')
    _add_column_if_not_exists(cursor, 'stocks', 'last_seen_date', 'TEXT')

    # --- Portfolio Tables ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_summary (
            id INTEGER PRIMARY KEY,
            cash_balance REAL NOT NULL,
            total_invested REAL NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            purchase_price REAL NOT NULL,
            purchase_date TEXT NOT NULL
        )
    ''')

    # Initialize summary if it's empty
    cursor.execute('SELECT COUNT(*) FROM portfolio_summary')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO portfolio_summary (id, cash_balance, total_invested) VALUES (1, 0, 0)')

    conn.commit()
    conn.close()
    print("Database initialized/updated.")

def update_tickers_from_source(tickers, category, source_url):
    """
    Adds new tickers and updates the last_seen_date for existing tickers from a given source.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')

    new_tickers_added = 0
    tickers_updated = 0

    for ticker in tickers:
        try:
            # Try to insert a new record.
            cursor.execute('''
                INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (ticker, category, today_str, source_url, today_str))
            new_tickers_added += 1
        except sqlite3.IntegrityError:
            # If it fails, the ticker/category pair already exists. Update it instead.
            cursor.execute('''
                UPDATE stocks
                SET last_seen_date = ?, source_url = ?
                WHERE ticker = ? AND category = ?
            ''', (today_str, source_url, ticker, category))
            tickers_updated += 1

    conn.commit()
    conn.close()
    print(f"Source: {source_url}")
    print(f" - Added {new_tickers_added} new tickers.")
    print(f" - Refreshed {tickers_updated} existing tickers.")

def get_tickers_by_category(category):
    """
    Retrieves a list of all tickers for a given category.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM stocks WHERE category = ?', (category,))
    tickers = [item[0] for item in cursor.fetchall()]
    conn.close()
    return tickers

def replace_tickers_for_category(tickers, category):
    """
    Replaces all tickers for a given category with a new list from a manual source.
    This is an atomic operation.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    source_url = 'manual_update'

    try:
        # First, delete all existing tickers for this category
        cursor.execute('DELETE FROM stocks WHERE category = ?', (category,))
        print(f"Deleted existing tickers for category '{category}'.")

        # Then, add the new tickers
        for ticker in tickers:
            cursor.execute('''
                INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (ticker, category, today_str, source_url, today_str))

        conn.commit()
        print(f"Successfully replaced with {len(tickers)} new tickers for '{category}'.")

    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during ticker replacement: {e}")
    finally:
        conn.close()

def prune_old_tickers(days_old=30):
    """
    Removes tickers from the database that haven't been seen in a while.
    This helps remove stocks that are no longer on the source lists.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cutoff_date = datetime.now() - timedelta(days=days_old)
    cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')

    try:
        cursor.execute("SELECT COUNT(*) FROM stocks WHERE last_seen_date < ?", (cutoff_date_str,))
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"Pruning {count} old tickers not seen since {cutoff_date_str}...")
            cursor.execute("DELETE FROM stocks WHERE last_seen_date < ?", (cutoff_date_str,))
            conn.commit()
            print(f"Successfully pruned {count} old tickers.")
        else:
            print("No old tickers to prune.")

    except sqlite3.Error as e:
        print(f"Database error during pruning: {e}")
    finally:
        conn.close()

# --- Portfolio Management Functions ---

def get_portfolio_summary():
    """Retrieves the portfolio summary (cash, total invested)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE id = 1')
    summary = cursor.fetchone()
    conn.close()
    return summary if summary else (0, 0)

def get_portfolio_holdings():
    """Retrieves all portfolio transactions."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker, shares, purchase_price, purchase_date FROM portfolio_transactions ORDER BY purchase_date DESC')
    holdings = cursor.fetchall()
    conn.close()
    return holdings

def execute_investment(ticker, shares, price, investment_amount):
    """
    Records a new investment transaction and updates the portfolio summary.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE id = 1')
        cash, total_invested = cursor.fetchone()

        new_cash = cash + investment_amount
        new_total_invested = total_invested + investment_amount

        cost = shares * price
        new_cash -= cost

        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT INTO portfolio_transactions (ticker, shares, purchase_price, purchase_date)
            VALUES (?, ?, ?, ?)
        ''', (ticker, shares, price, today_str))

        cursor.execute('''
            UPDATE portfolio_summary
            SET cash_balance = ?, total_invested = ?
            WHERE id = 1
        ''', (new_cash, new_total_invested))

        conn.commit()
        print(f"Successfully executed investment: Bought {shares:.4f} shares of {ticker} at ${price:.2f}")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during investment: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
