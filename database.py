import os
import mysql.connector
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.environ.get('DB_HOST'), user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'), database=os.environ.get('DB_NAME'),
            connection_timeout=10
        )
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_summary (
            portfolio_name VARCHAR(50) PRIMARY KEY,
            cash_balance DECIMAL(18, 4) NOT NULL,
            total_invested DECIMAL(18, 4) NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            portfolio_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            shares DECIMAL(18, 8) NOT NULL,
            purchase_price DECIMAL(18, 4) NOT NULL,
            purchase_date DATE NOT NULL,
            FOREIGN KEY (portfolio_name) REFERENCES portfolio_summary(portfolio_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_picks_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pick_date DATE NOT NULL,
            category VARCHAR(50) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            UNIQUE KEY unique_pick (pick_date, category)
        )
    """)

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
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT pick_date, ticker FROM daily_picks_history WHERE category = %s ORDER BY pick_date DESC", (category,))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return history

def get_recently_picked_tickers(category, days=7):
    conn = get_db_connection()
    if not conn: return set()
    cursor = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute("SELECT ticker FROM daily_picks_history WHERE category = %s AND pick_date >= %s", (category, cutoff_date))
    tickers = {row[0] for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    return tickers

def get_portfolio_summary(portfolio_name):
    conn = get_db_connection()
    if not conn: return (0.0, 0.0)
    cursor = conn.cursor()
    cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s', (portfolio_name,))
    summary = cursor.fetchone()
    cursor.close()
    conn.close()
    return (float(summary[0]), float(summary[1])) if summary else (0.0, 0.0)

def get_portfolio_holdings(portfolio_name):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, ticker, shares, purchase_price FROM portfolio_transactions WHERE portfolio_name = %s", (portfolio_name,))
    holdings = cursor.fetchall()
    cursor.close()
    conn.close()
    return holdings

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        print(f"--- EXECUTING INVESTMENT for {portfolio_name} ---")
        print(f"Attempting to buy {shares} of {ticker} at ${price}")

        cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s FOR UPDATE', (portfolio_name,))
        summary = cursor.fetchone()
        if not summary:
            print(f"Error: Portfolio '{portfolio_name}' not found.")
            return

        cash, total_invested = summary
        cost = Decimal(str(shares)) * Decimal(str(price))
        dec_investment = Decimal(str(investment_amount))

        print(f"Before investment: Cash = ${cash}, Total Invested = ${total_invested}")
        print(f"Investment amount = ${dec_investment}, Purchase cost = ${cost}")

        new_cash = Decimal(str(cash)) + dec_investment - cost
        new_total_invested = Decimal(str(total_invested)) + dec_investment

        print(f"After investment: New Cash = ${new_cash}, New Total Invested = ${new_total_invested}")

        if new_cash < 0:
            print(f"INVESTMENT FAILED: Not enough cash for {portfolio_name}.")
            conn.rollback()
            return

        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            'INSERT INTO portfolio_transactions (portfolio_name, ticker, shares, purchase_price, purchase_date) VALUES (%s, %s, %s, %s, %s)',
            (portfolio_name, ticker, shares, price, today_str)
        )
        cursor.execute(
            'UPDATE portfolio_summary SET cash_balance = %s, total_invested = %s WHERE portfolio_name = %s',
            (new_cash, new_total_invested, portfolio_name)
        )
        conn.commit()
        print(f"--- INVESTMENT SUCCEEDED for {portfolio_name} ---")
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Database error during investment: {err}")
    finally:
        cursor.close()
        conn.close()
