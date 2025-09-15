import os
import mysql.connector
from mysql.connector import errorcode
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

# ... (get_db_connection function is unchanged)

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
    # ... (other CREATE TABLE statements)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_picks_history (
            pick_date DATE NOT NULL,
            category VARCHAR(50) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            sentiment_score FLOAT NULL,
            PRIMARY KEY (pick_date, category)
        )
    """)
    # ... (rest of init_db)
    conn.commit()
    cursor.close()
    conn.close()


def save_daily_pick(category, ticker, sentiment_score=None):
    """Saves a daily pick to the history table, including its sentiment score."""
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
    sql = "SELECT pick_date, ticker, sentiment_score FROM daily_picks_history WHERE category = %s ORDER BY pick_date DESC"
    history = []
    try:
        cursor.execute(sql, (category,))
        history = [{'date': row[0].strftime('%Y-%m-%d'), 'ticker': row[1], 'sentiment_score': row[2]} for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        print(f"Error getting pick history: {err}")
    finally:
        cursor.close()
        conn.close()
    return history

# ... (The rest of the file is unchanged, including get_todays_pick_for_category, etc.)
# ... I am only showing the changed functions for brevity. The overwrite will contain the full file.
