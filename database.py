import os
import mysql.connector
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'), user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'), database=os.environ.get('DB_NAME'),
            connection_timeout=10
        )
        logging.info("Database connection successful.")
        return conn
    except mysql.connector.Error as err:
        logging.error(f"Database connection error: {err}")
        return None

def log_db_operation(func_name, err):
    logging.error(f"Database operation error in {func_name}: {err}")

def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_settings (
                    category VARCHAR(50) PRIMARY KEY,
                    momentum_weight DECIMAL(5, 2) NOT NULL,
                    value_weight DECIMAL(5, 2) NOT NULL,
                    ma_weight DECIMAL(5, 2) NOT NULL,
                    volatility_weight DECIMAL(5, 2) NOT NULL,
                    volume_weight DECIMAL(5, 2) NOT NULL,
                    sentiment_weight DECIMAL(5, 2) NOT NULL
                )
            """)

            portfolios_to_init = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment', 'ai_guided_portfolio']
            for p_name in portfolios_to_init:
                cursor.execute('SELECT COUNT(*) FROM portfolio_summary WHERE portfolio_name = %s', (p_name,))
                if cursor.fetchone()[0] == 0:
                    cursor.execute('INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested) VALUES (%s, 0, 0)', (p_name,))

            categories = ['hot_stock', 'penny_stock', 'monthly_dividend', 'high_yield']
            default_weights = (0.20, 0.20, 0.20, 0.15, 0.05, 0.20)
            for category in categories:
                cursor.execute('SELECT COUNT(*) FROM ai_settings WHERE category = %s', (category,))
                if cursor.fetchone()[0] == 0:
                    sql = "INSERT INTO ai_settings (category, momentum_weight, value_weight, ma_weight, volatility_weight, volume_weight, sentiment_weight) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (category,) + default_weights)
            conn.commit()
            logging.info("Database initialized/verified successfully.")
    except mysql.connector.Error as err:
        log_db_operation(init_db.__name__, err)
    finally:
        if conn and conn.is_connected():
            conn.close()

def execute_sale(portfolio_name, ticker, shares_to_sell, price):
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed."
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Check current holdings
            cursor.execute(
                "SELECT SUM(shares) as total_shares FROM portfolio_transactions WHERE portfolio_name = %s AND ticker = %s",
                (portfolio_name, ticker)
            )
            holding = cursor.fetchone()
            if not holding or holding['total_shares'] < shares_to_sell:
                return False, "Not enough shares to sell."

            # Record the sale as a negative transaction
            today_str = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                'INSERT INTO portfolio_transactions (portfolio_name, ticker, shares, purchase_price, purchase_date) VALUES (%s, %s, %s, %s, %s)',
                (portfolio_name, ticker, -shares_to_sell, price, today_str)
            )

            # Update the portfolio summary
            proceeds = Decimal(str(shares_to_sell)) * Decimal(str(price))
            cursor.execute(
                'UPDATE portfolio_summary SET cash_balance = cash_balance + %s WHERE portfolio_name = %s',
                (proceeds, portfolio_name)
            )

            conn.commit()
            logging.info(f"Sale of {shares_to_sell} shares of {ticker} from {portfolio_name} successful.")
            return True, f"Successfully sold {shares_to_sell} shares of {ticker}."

    except mysql.connector.Error as err:
        log_db_operation(execute_sale.__name__, err)
        conn.rollback()
        return False, "A database error occurred during the sale."
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_all_portfolios_data():
    conn = get_db_connection()
    if not conn: return {}, {}

    try:
        with conn.cursor(dictionary=True) as cursor:
            # Get summaries
            cursor.execute('SELECT portfolio_name, cash_balance, total_invested FROM portfolio_summary')
            summaries = {row['portfolio_name']: row for row in cursor.fetchall()}

            # Get holdings
            cursor.execute("""
                SELECT t.portfolio_name, t.ticker, SUM(t.shares) as shares, AVG(t.purchase_price) as purchase_price
                FROM portfolio_transactions t
                GROUP BY t.portfolio_name, t.ticker
            """)
            holdings_results = cursor.fetchall()

            all_holdings = {}
            for row in holdings_results:
                portfolio_name = row.pop('portfolio_name')
                if portfolio_name not in all_holdings:
                    all_holdings[portfolio_name] = []
                all_holdings[portfolio_name].append(row)

            return summaries, all_holdings

    except mysql.connector.Error as err:
        log_db_operation(get_all_portfolios_data.__name__, err)
        return {}, {}
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_ai_settings(category):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM ai_settings WHERE category = %s", (category,))
            return cursor.fetchone()
    except mysql.connector.Error as err:
        log_db_operation(get_ai_settings.__name__, err)
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()

def save_ai_settings(category, weights):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            sql = """
                UPDATE ai_settings
                SET momentum_weight = %s, value_weight = %s, ma_weight = %s,
                    volatility_weight = %s, volume_weight = %s, sentiment_weight = %s
                WHERE category = %s
            """
            cursor.execute(sql, (
                weights['momentum_weight'], weights['value_weight'], weights['ma_weight'],
                weights['volatility_weight'], weights['volume_weight'], weights['sentiment_weight'],
                category
            ))
            conn.commit()
            logging.info(f"AI settings for {category} saved successfully.")
    except mysql.connector.Error as err:
        log_db_operation(save_ai_settings.__name__, err)
    finally:
        if conn and conn.is_connected():
            conn.close()

def save_daily_pick(category, ticker):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            today_str = datetime.now().strftime('%Y-%m-%d')
            sql = "INSERT INTO daily_picks_history (pick_date, category, ticker) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE ticker = VALUES(ticker)"
            cursor.execute(sql, (today_str, category, ticker))
            conn.commit()
            logging.info(f"Daily pick for {category} saved: {ticker}")
    except mysql.connector.Error as err:
        log_db_operation(save_daily_pick.__name__, err)
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_pick_history_for_category(category):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT pick_date, ticker FROM daily_picks_history WHERE category = %s ORDER BY pick_date DESC", (category,))
            return cursor.fetchall()
    except mysql.connector.Error as err:
        log_db_operation(get_pick_history_for_category.__name__, err)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_recently_picked_tickers(category, days=7):
    conn = get_db_connection()
    if not conn: return set()
    try:
        with conn.cursor() as cursor:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            cursor.execute("SELECT ticker FROM daily_picks_history WHERE category = %s AND pick_date >= %s", (category, cutoff_date))
            return {row[0] for row in cursor.fetchall()}
    except mysql.connector.Error as err:
        log_db_operation(get_recently_picked_tickers.__name__, err)
        return set()
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_portfolio_summary(portfolio_name):
    conn = get_db_connection()
    if not conn: return (0.0, 0.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s', (portfolio_name,))
            summary = cursor.fetchone()
            return (float(summary[0]), float(summary[1])) if summary else (0.0, 0.0)
    except mysql.connector.Error as err:
        log_db_operation(get_portfolio_summary.__name__, err)
        return (0.0, 0.0)
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_portfolio_holdings(portfolio_name):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id, ticker, shares, purchase_price FROM portfolio_transactions WHERE portfolio_name = %s", (portfolio_name,))
            return cursor.fetchall()
    except mysql.connector.Error as err:
        log_db_operation(get_portfolio_holdings.__name__, err)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            logging.info(f"Executing investment for {portfolio_name}: {shares} of {ticker} at ${price}")

            cursor.execute('SELECT cash_balance, total_invested FROM portfolio_summary WHERE portfolio_name = %s FOR UPDATE', (portfolio_name,))
            summary = cursor.fetchone()
            if not summary:
                logging.error(f"Portfolio '{portfolio_name}' not found.")
                return

            cash, total_invested = map(Decimal, summary)
            cost = Decimal(str(shares)) * Decimal(str(price))
            dec_investment = Decimal(str(investment_amount))

            new_cash = cash + dec_investment - cost
            new_total_invested = total_invested + dec_investment

            if new_cash < 0:
                logging.warning(f"Investment failed for {portfolio_name}: Insufficient cash.")
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
            logging.info(f"Investment successful for {portfolio_name}.")
    except mysql.connector.Error as err:
        log_db_operation(execute_investment.__name__, err)
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            conn.close()