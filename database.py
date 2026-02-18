import os
import mysql.connector
from mysql.connector import errorcode
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'), user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'), database=os.environ.get('DB_NAME'),
            connection_timeout=10, pool_name="stock_pool", pool_size=5
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            ticker VARCHAR(20) NOT NULL,
            category VARCHAR(50) NOT NULL,
            date_added DATE NOT NULL,
            source_url VARCHAR(255),
            last_seen_date DATE,
            market_cap BIGINT NULL,
            sector VARCHAR(255) NULL,
            is_sp500 TINYINT(1) DEFAULT 0,
            PRIMARY KEY (ticker, category)
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS portfolio_summary (portfolio_name VARCHAR(50) PRIMARY KEY, cash_balance DECIMAL(18, 4) NOT NULL, total_invested DECIMAL(18, 4) NOT NULL)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INT AUTO_INCREMENT PRIMARY KEY, portfolio_name VARCHAR(50) NOT NULL, ticker VARCHAR(20) NOT NULL,
            shares DECIMAL(18, 8) NOT NULL, purchase_price DECIMAL(18, 4) NOT NULL, purchase_date DATE NOT NULL,
            sell_flag TINYINT(1) DEFAULT 0, FOREIGN KEY (portfolio_name) REFERENCES portfolio_summary(portfolio_name)
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_picks_history (
            id INT AUTO_INCREMENT PRIMARY KEY, pick_date DATE NOT NULL, category VARCHAR(50) NOT NULL,
            ticker VARCHAR(20) NOT NULL, sentiment_score FLOAT NULL, UNIQUE KEY unique_pick (pick_date, category)
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pick_performance (
            id INT AUTO_INCREMENT PRIMARY KEY, pick_id INT NOT NULL, days_after_pick INT NOT NULL,
            performance_percent FLOAT NOT NULL, date_checked DATE NOT NULL,
            FOREIGN KEY (pick_id) REFERENCES daily_picks_history(id) ON DELETE CASCADE,
            UNIQUE KEY unique_performance_check (pick_id, days_after_pick)
        )""")
    portfolios_to_init = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment']
    for p_name in portfolios_to_init:
        cursor.execute('SELECT COUNT(*) FROM portfolio_summary WHERE portfolio_name = %s', (p_name,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested) VALUES (%s, 0, 0)', (p_name,))
    conn.commit()
    cursor.close()
    conn.close()

def save_daily_pick(category, ticker, sentiment_score=None):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    sql = "INSERT INTO daily_picks_history (pick_date, category, ticker, sentiment_score) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE ticker = VALUES(ticker), sentiment_score = VALUES(sentiment_score)"
    try:
        cursor.execute(sql, (today_str, category, ticker, sentiment_score))
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
    sql = "SELECT id, pick_date, ticker, sentiment_score FROM daily_picks_history WHERE category = %s ORDER BY pick_date DESC"
    history = []
    try:
        cursor.execute(sql, (category,))
        history = [{'id': row[0], 'date': row[1].strftime('%Y-%m-%d'), 'ticker': row[2], 'sentiment_score': row[3]} for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        print(f"Error getting pick history: {err}")
    finally:
        cursor.close()
        conn.close()
    return history

def get_todays_pick_for_category(category):
    history = get_pick_history_for_category(category)
    if not history: return None
    today_str = datetime.now().strftime('%Y-%m-%d')
    for pick in history:
        if pick['date'] == today_str:
            return pick
    return None

def get_recently_picked_tickers(category, days=365):
    conn = get_db_connection()
    if not conn: return set()
    cursor = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
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

def update_tickers_from_source(tickers, category, source_url):
    if not tickers:
        return
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    sql = """
        INSERT INTO stocks (ticker, category, date_added, source_url, last_seen_date)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE last_seen_date = VALUES(last_seen_date), source_url = VALUES(source_url)
    """
    data = [(ticker, category, today_str, source_url, today_str) for ticker in tickers]
    try:
        cursor.executemany(sql, data)
        conn.commit()
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Database error during batch ticker update: {err}")
    finally:
        cursor.close()
        conn.close()

def update_stock_details_batch(updates):
    """
    Updates multiple stocks' details in the database using batch processing.
    updates: list of tuples (market_cap, sector, is_sp500, ticker)
    """
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        sql = """
            UPDATE stocks
            SET market_cap = %s, sector = %s, is_sp500 = %s
            WHERE ticker = %s
        """
        cursor.executemany(sql, updates)
        conn.commit()
    except mysql.connector.Error as e:
        print(f"Error updating batch details: {e}")
        conn.rollback()
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
    if not conn: return (0.0, 0.0)
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
    cursor.execute('SELECT ticker, shares, purchase_price, purchase_date, sell_flag FROM portfolio_transactions WHERE portfolio_name = %s ORDER BY purchase_date DESC', (portfolio_name,))
    holdings = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{'ticker': h[0], 'shares': float(h[1]), 'purchase_price': float(h[2]), 'purchase_date': h[3].strftime('%Y-%m-%d'), 'sell_flag': h[4]} for h in holdings]

def set_sell_flag(ticker, flag_value):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        sql = "UPDATE portfolio_transactions SET sell_flag = %s WHERE ticker = %s"
        cursor.execute(sql, (1 if flag_value else 0, ticker))
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Database error while setting sell_flag for {ticker}: {e}")
    finally:
        cursor.close()
        conn.close()

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s FOR UPDATE', (portfolio_name,))
        cash, total_invested = cursor.fetchone()
        dec_investment = Decimal(str(investment_amount))
        dec_shares = Decimal(str(shares))
        dec_price = Decimal(str(price))
        new_cash = cash + dec_investment
        new_total_invested = total_invested + dec_investment
        cost = dec_shares * dec_price
        new_cash -= cost
        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('INSERT INTO portfolio_transactions (portfolio_name, ticker, shares, purchase_price, purchase_date) VALUES (%s, %s, %s, %s, %s)', (portfolio_name, ticker, dec_shares, dec_price, today_str))
        cursor.execute('UPDATE portfolio_summary SET cash_balance = %s, total_invested = %s WHERE portfolio_name = %s', (new_cash, new_total_invested, portfolio_name))
        conn.commit()
    except (mysql.connector.Error, InvalidOperation) as e:
        conn.rollback()
        print(f"Database error or invalid decimal operation during investment for '{portfolio_name}': {e}")
    finally:
        cursor.close()
        conn.close()

def get_untracked_picks():
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT p.id, p.ticker, p.pick_date
        FROM daily_picks_history p
        LEFT JOIN pick_performance pp7 ON p.id = pp7.pick_id AND pp7.days_after_pick = 7
        LEFT JOIN pick_performance pp30 ON p.id = pp30.pick_id AND pp30.days_after_pick = 30
        LEFT JOIN pick_performance pp90 ON p.id = pp90.pick_id AND pp90.days_after_pick = 90
        WHERE
            (p.pick_date <= CURDATE() - INTERVAL 7 DAY AND pp7.id IS NULL) OR
            (p.pick_date <= CURDATE() - INTERVAL 30 DAY AND pp30.id IS NULL) OR
            (p.pick_date <= CURDATE() - INTERVAL 90 DAY AND pp90.id IS NULL)
    """
    picks_to_track = []
    try:
        cursor.execute(sql)
        picks_to_track = cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Error getting untracked picks: {e}")
    finally:
        cursor.close()
        conn.close()
    return picks_to_track

def add_performance_record(pick_id, days_after, performance):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    sql = "INSERT INTO pick_performance (pick_id, days_after_pick, performance_percent, date_checked) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE performance_percent = VALUES(performance_percent), date_checked = VALUES(date_checked)"
    try:
        cursor.execute(sql, (pick_id, days_after, performance, today_str))
        conn.commit()
    except mysql.connector.Error as e:
        print(f"Error adding performance record: {e}")
    finally:
        cursor.close()
        conn.close()
