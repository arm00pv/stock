import os
import mysql.connector
from mysql.connector import errorcode
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables.
    """
    try:
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            database=os.environ.get('DB_NAME'),
            connection_timeout=10,
            pool_name="stock_pool",
            pool_size=5
        )
        return conn
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Something is wrong with your user name or password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist")
        else:
            print(f"Database connection error: {err}")
        return None

def init_db():
    """Initializes the MySQL database and creates tables if they don't exist."""
    conn = get_db_connection()
    if not conn:
        print("Could not connect to database for initialization.")
        return
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS stocks (ticker VARCHAR(20) NOT NULL, category VARCHAR(50) NOT NULL, date_added DATE NOT NULL, source_url VARCHAR(255), last_seen_date DATE, PRIMARY KEY (ticker, category))")
    cursor.execute("CREATE TABLE IF NOT EXISTS portfolio_summary (portfolio_name VARCHAR(50) PRIMARY KEY, cash_balance DECIMAL(18, 4) NOT NULL, total_invested DECIMAL(18, 4) NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS portfolio_transactions (id INT AUTO_INCREMENT PRIMARY KEY, portfolio_name VARCHAR(50) NOT NULL, ticker VARCHAR(20) NOT NULL, shares DECIMAL(18, 8) NOT NULL, purchase_price DECIMAL(18, 4) NOT NULL, purchase_date DATE NOT NULL, FOREIGN KEY (portfolio_name) REFERENCES portfolio_summary(portfolio_name))")
    cursor.execute("CREATE TABLE IF NOT EXISTS daily_picks_history (pick_date DATE NOT NULL, category VARCHAR(50) NOT NULL, ticker VARCHAR(20) NOT NULL, PRIMARY KEY (pick_date, category))")

    portfolios_to_init = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment']
    for p_name in portfolios_to_init:
        cursor.execute('SELECT COUNT(*) FROM portfolio_summary WHERE portfolio_name = %s', (p_name,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested) VALUES (%s, 0, 0)', (p_name,))

    conn.commit()
    cursor.close()
    conn.close()

def save_daily_pick(category, ticker):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    sql = "INSERT INTO daily_picks_history (pick_date, category, ticker) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE ticker = VALUES(ticker)"
    try:
        cursor.execute(sql, (today_str, category, ticker))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error saving daily pick: {err}")
    finally:
        cursor.close()
        conn.close()

def get_pick_history_for_category(category):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor()
    sql = "SELECT pick_date, ticker FROM daily_picks_history WHERE category = %s ORDER BY pick_date DESC"
    history = []
    try:
        cursor.execute(sql, (category,))
        history = [{'date': row[0].strftime('%Y-%m-%d'), 'ticker': row[1]} for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        print(f"Error getting pick history: {err}")
    finally:
        cursor.close()
        conn.close()
    return history

def get_todays_pick_for_category(category):
    history = get_pick_history_for_category(category)
    today_str = datetime.now().strftime('%Y-%m-%d')
    for pick in history:
        if pick['date'] == today_str:
            return pick
    return None

def get_recently_picked_tickers(category, days=365):
    conn = get_db_connection()
    if not conn: return set()
    cursor = conn.cursor()
    cutoff_date = datetime.now() - timedelta(days=days)
    sql = "SELECT ticker FROM daily_picks_history WHERE category = %s AND pick_date > %s"
    tickers = set()
    try:
        cursor.execute(sql, (category, cutoff_date))
        tickers = {row[0] for row in cursor.fetchall()}
    except mysql.connector.Error as err:
        print(f"Error getting recent tickers: {err}")
    finally:
        cursor.close()
        conn.close()
    return tickers

def update_tickers_from_source(tickers, category, source_url):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    new_tickers_added, tickers_updated = 0, 0
    sql = "INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date) VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE last_seen_date = VALUES(last_seen_date), source_url = VALUES(source_url)"
    for ticker in tickers:
        try:
            cursor.execute(sql, (ticker, category, today_str, source_url, today_str))
            if cursor.rowcount == 1: new_tickers_added += 1
            elif cursor.rowcount == 2: tickers_updated += 1
        except mysql.connector.Error as err:
            print(f"Error updating ticker {ticker}: {err}")
    conn.commit()
    cursor.close()
    conn.close()

def get_tickers_by_category(category):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM stocks WHERE category = %s', (category,))
    tickers = [item[0] for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return tickers

def replace_tickers_for_category(tickers, category):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    source_url = 'manual_update'
    try:
        cursor.execute('DELETE FROM stocks WHERE category = %s', (category,))
        sql = 'INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date) VALUES (%s, %s, %s, %s, %s)'
        data = [(ticker, category, today_str, source_url, today_str) for ticker in tickers]
        cursor.executemany(sql, data)
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Database error during ticker replacement: {e}")
    finally:
        cursor.close()
        conn.close()

def prune_old_tickers(days_old=30):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')
    try:
        cursor.execute("DELETE FROM stocks WHERE last_seen_date < %s", (cutoff_date,))
        conn.commit()
    except mysql.connector.Error as e:
        print(f"Database error during pruning: {e}")
    finally:
        cursor.close()
        conn.close()

def get_portfolio_summary(portfolio_name):
    conn = get_db_connection()
    if not conn: return (0, 0)
    cursor = conn.cursor()
    cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s', (portfolio_name,))
    summary = cursor.fetchone()
    cursor.close()
    conn.close()
    if summary:
        return (float(summary[0]), float(summary[1]))
    return (0.0, 0.0)

def get_portfolio_holdings(portfolio_name):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('SELECT ticker, shares, purchase_price, purchase_date FROM portfolio_transactions WHERE portfolio_name = %s ORDER BY purchase_date DESC', (portfolio_name,))
    holdings = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{'ticker': h[0], 'shares': float(h[1]), 'purchase_price': float(h[2]), 'purchase_date': h[3].strftime('%Y-%m-%d')} for h in holdings]

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s FOR UPDATE', (portfolio_name,))
        cash, total_invested = cursor.fetchone()

        # Convert all inputs to Decimal for precision
        dec_investment = Decimal(str(investment_amount))
        dec_shares = Decimal(str(shares))
        dec_price = Decimal(str(price))

        # Perform calculations with Decimal objects
        new_cash = cash + dec_investment
        new_total_invested = total_invested + dec_investment
        cost = dec_shares * dec_price
        new_cash -= cost

        today_str = datetime.now().strftime('%Y-%m-%d')

        # Insert the transaction with high-precision values
        cursor.execute('''
            INSERT INTO portfolio_transactions (portfolio_name, ticker, shares, purchase_price, purchase_date)
            VALUES (%s, %s, %s, %s, %s)
        ''', (portfolio_name, ticker, dec_shares, dec_price, today_str))

        # Update the summary
        cursor.execute(
            'UPDATE portfolio_summary SET cash_balance = %s, total_invested = %s WHERE portfolio_name = %s',
            (new_cash, new_total_invested, portfolio_name)
        )

        conn.commit()
        print(f"Successfully executed investment for '{portfolio_name}': Bought {dec_shares} shares of {ticker} at ${dec_price}")
    except (mysql.connector.Error, InvalidOperation) as e:
        conn.rollback()
        print(f"Database error or invalid decimal operation during investment for '{portfolio_name}': {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    init_db()
