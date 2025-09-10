import sqlite3

DB_NAME = 'stocks.db'

def init_db():
    """
    Initializes the database and creates the stocks table if it doesn't exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create table
    # A ticker can belong to multiple categories, so a composite primary key is used.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT NOT NULL,
            category TEXT NOT NULL,
            date_added TEXT NOT NULL,
            PRIMARY KEY (ticker, category)
        )
    ''')

    # --- New Portfolio Tables ---
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
    print("Database initialized.")

def add_tickers_to_db(tickers, category):
    """
    Adds a list of tickers to the database for a specific category.
    It ignores duplicates based on the composite primary key (ticker, category).
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    added_count = 0
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')

    for ticker in tickers:
        try:
            cursor.execute('''
                INSERT INTO stocks (ticker, category, date_added)
                VALUES (?, ?, ?)
            ''', (ticker, category, today_str))
            added_count += 1
        except sqlite3.IntegrityError:
            # This ticker/category pair already exists, so we just ignore it.
            pass

    conn.commit()
    conn.close()
    print(f"Added {added_count} new tickers to the '{category}' category.")

def get_tickers_by_category(category):
    """
    Retrieves a list of all tickers for a given category.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT ticker FROM stocks WHERE category = ?', (category,))

    # The fetchall() returns a list of tuples, so we need to flatten it.
    tickers = [item[0] for item in cursor.fetchall()]

    conn.close()
    return tickers

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
    This function handles the database transaction atomically.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        # Get current summary
        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE id = 1')
        cash, total_invested = cursor.fetchone()

        # Add the weekly $5
        new_cash = cash + investment_amount
        new_total_invested = total_invested + investment_amount

        # 'Buy' the stock
        cost = shares * price
        new_cash -= cost

        # Record the transaction
        from datetime import datetime
        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT INTO portfolio_transactions (ticker, shares, purchase_price, purchase_date)
            VALUES (?, ?, ?, ?)
        ''', (ticker, shares, price, today_str))

        # Update the summary
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
    # This allows the script to be run directly to initialize the database.
    init_db()
