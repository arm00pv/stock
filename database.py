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
    from models import init_user_db
    init_user_db()
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    # Portfolio Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_summary (
            portfolio_name VARCHAR(50) PRIMARY KEY,
            cash_balance DECIMAL(18, 4) NOT NULL,
                    total_invested DECIMAL(18, 4) NOT NULL,
                    paper_trade BOOLEAN DEFAULT TRUE
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

    # Stock Universe Table (from Alpha Vantage)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_universe (
            symbol VARCHAR(20) PRIMARY KEY,
            name VARCHAR(255),
            exchange VARCHAR(50),
            asset_type VARCHAR(50),
            ipo_date DATE,
            status VARCHAR(20),
            INDEX idx_name (name)
        )
    """)

    # Watchlist Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_watchlist (user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Personal Portfolio Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_portfolios (
            user_id INT PRIMARY KEY,
            cash_balance DECIMAL(18, 4) DEFAULT 10000.00,
            total_invested DECIMAL(18, 4) DEFAULT 0.00,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            action VARCHAR(10) NOT NULL,
            shares DECIMAL(18, 8) NOT NULL,
            price DECIMAL(18, 4) NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Beta & Gamification Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            target_price DECIMAL(18, 4) NOT NULL,
            condition_type VARCHAR(10) NOT NULL,
            is_triggered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            badge_name VARCHAR(50) NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_badge (user_id, badge_name),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            message VARCHAR(255) NOT NULL,
            type VARCHAR(20) DEFAULT 'info',
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # AI Settings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_decision_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            decision_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            portfolio_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            action VARCHAR(10) NOT NULL,
            reason VARCHAR(255)
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

    # Initialize portfolios
    portfolios_to_init = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment']
    for p_name in portfolios_to_init:
        cursor.execute('SELECT COUNT(*) FROM portfolio_summary WHERE portfolio_name = %s', (p_name,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO portfolio_summary (portfolio_name, cash_balance, total_invested) VALUES (%s, 0, 0)', (p_name,))

    # Initialize default AI settings
    categories = ['hot_stock', 'penny_stock', 'monthly_dividend', 'high_yield']
    default_weights = (0.20, 0.20, 0.20, 0.15, 0.05, 0.20)
    for category in categories:
        cursor.execute('SELECT COUNT(*) FROM ai_settings WHERE category = %s', (category,))
        if cursor.fetchone()[0] == 0:
            sql = "INSERT INTO ai_settings (category, momentum_weight, value_weight, ma_weight, volatility_weight, volume_weight, sentiment_weight) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(sql, (category,) + default_weights)

    conn.commit()
    cursor.close()
    conn.close()

def get_ai_settings(category):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ai_settings WHERE category = %s", (category,))
    settings = cursor.fetchone()
    cursor.close()
    conn.close()
    return settings

def save_ai_settings(category, weights):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    sql = """
        UPDATE ai_settings
        SET momentum_weight = %s, value_weight = %s, ma_weight = %s,
            volatility_weight = %s, volume_weight = %s, sentiment_weight = %s
        WHERE category = %s
    """
    try:
        cursor.execute(sql, (
            weights['momentum_weight'], weights['value_weight'], weights['ma_weight'],
            weights['volatility_weight'], weights['volume_weight'], weights['sentiment_weight'],
            category
        ))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error saving AI settings: {err}")
    finally:
        cursor.close()
        conn.close()

def get_watchlist(user_id):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM watchlist WHERE user_id = %s ORDER BY date_added DESC", (user_id,))
            return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching watchlist: {err}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def add_to_watchlist(user_id, ticker):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO watchlist (user_id, ticker) VALUES (%s, %s)", (user_id, ticker))
            conn.commit()
            return True
    except mysql.connector.Error as err:
        print(f"Error adding to watchlist: {err}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def remove_from_watchlist(user_id, ticker):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM watchlist WHERE user_id = %s AND ticker = %s", (user_id, ticker))
            conn.commit()
            return True
    except mysql.connector.Error as err:
        print(f"Error removing from watchlist: {err}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def search_stocks_db(query):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    search_term = f"%{query}%"
    # Prioritize exact match on symbol, then starts with, then contains
    sql = """
        SELECT symbol, name, exchange, asset_type
        FROM stock_universe
        WHERE symbol LIKE %s OR name LIKE %s
        ORDER BY
            CASE
                WHEN symbol = %s THEN 1
                WHEN symbol LIKE %s THEN 2
                ELSE 3
            END,
            symbol ASC
        LIMIT 10
    """
    try:
        cursor.execute(sql, (search_term, search_term, query, f"{query}%"))
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error searching stocks: {err}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_new_listings(days=30):
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    sql = """
        SELECT symbol, name, exchange, asset_type, ipo_date
        FROM stock_universe
        WHERE ipo_date >= %s
        ORDER BY ipo_date DESC
        LIMIT 20
    """
    try:
        cursor.execute(sql, (cutoff_date,))
        return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching new listings: {err}")
        return []
    finally:
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

def get_all_transactions():
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Return newest first
            cursor.execute("SELECT * FROM portfolio_transactions ORDER BY purchase_date DESC, id DESC LIMIT 100")
            return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching transactions: {err}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_total_portfolio_value():
    """
    Calculates the total current value of all portfolios.
    Note: This requires fetching current prices which might be slow if done synchronously here.
    For now, we will just return the distribution of 'total_invested' + 'cash_balance' per portfolio as a proxy,
    or better yet, let the frontend compute value based on the /api/all-portfolios endpoint.

    Let's stick to returning simple DB stats here if needed, but actually /api/all-portfolios already returns computed values.
    So we might not need a complex function here if the frontend can use existing data.

    However, for a standalone chart API, let's return the 'total_invested' breakdown.
    """
    conn = get_db_connection()
    if not conn: return {}
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT portfolio_name, total_invested, cash_balance FROM portfolio_summary")
            return cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching portfolio summary: {err}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def execute_sale(portfolio_name, ticker, shares_to_sell, price):
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed."
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Check if paper trading
            cursor.execute("SELECT paper_trade FROM portfolio_summary WHERE portfolio_name = %s", (portfolio_name,))
            paper_trade = cursor.fetchone()
            if not paper_trade or not paper_trade['paper_trade']:
                return False, "Only paper trading is allowed."

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

def log_ai_decision(portfolio_name, ticker, action, reason):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ai_decision_log (portfolio_name, ticker, action, reason) VALUES (%s, %s, %s, %s)",
                (portfolio_name, ticker, action, reason)
            )
            conn.commit()
    except mysql.connector.Error as err:
        log_db_operation(log_ai_decision.__name__, err)
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_ai_decision_log(portfolio_name):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM ai_decision_log WHERE portfolio_name = %s ORDER BY decision_date DESC",
                (portfolio_name,)
            )
            return cursor.fetchall()
    except mysql.connector.Error as err:
        log_db_operation(get_ai_decision_log.__name__, err)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_ai_performance_data(portfolio_name):
    # This is a placeholder for a more sophisticated performance calculation.
    # For now, we'll just return some dummy data.
    return {
        "total_return_pct": 15.5,
        "win_loss_ratio": 1.5,
        "vs_market": 5.2,
        "portfolio_history": [
            {"date": "2023-01-01", "total_value": 10000},
            {"date": "2023-01-02", "total_value": 10050},
            {"date": "2023-01-03", "total_value": 10100},
        ],
        "market_history": [
            {"date": "2023-01-01", "total_value": 10000},
            {"date": "2023-01-02", "total_value": 10020},
            {"date": "2023-01-03", "total_value": 10050},
        ]
    }

def execute_investment(portfolio_name, ticker, shares, price, investment_amount):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Check if paper trading
            cursor.execute("SELECT paper_trade FROM portfolio_summary WHERE portfolio_name = %s", (portfolio_name,))
            paper_trade = cursor.fetchone()
            if not paper_trade or not paper_trade['paper_trade']:
                logging.warning(f"Attempted to invest in non-paper trading portfolio: {portfolio_name}")
                return

            logging.info(f"Executing investment for {portfolio_name}: {shares} of {ticker} at ${price}")

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