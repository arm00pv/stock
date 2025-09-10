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

if __name__ == '__main__':
    # This allows the script to be run directly to initialize the database.
    init_db()
