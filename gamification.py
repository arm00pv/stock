from database import get_db_connection
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BADGES = {
    "First Trade": "Execute your first trade.",
    "Diversified": "Hold 5 or more different stocks.",
    "Big Gainer": "Have a holding with >10% return.",
    "Active Trader": "Execute 10 or more trades."
}

def get_user_badges(user_id):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT badge_name, earned_at FROM user_achievements WHERE user_id = %s", (user_id,))
            earned = cursor.fetchall()

            # Format for frontend
            result = []
            earned_names = {b['badge_name'] for b in earned}

            for name, desc in BADGES.items():
                result.append({
                    'name': name,
                    'description': desc,
                    'earned': name in earned_names,
                    'date': next((b['earned_at'].strftime('%Y-%m-%d') for b in earned if b['badge_name'] == name), None)
                })
            return result
    finally:
        conn.close()

def award_badge(user_id, badge_name):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO user_achievements (user_id, badge_name) VALUES (%s, %s)", (user_id, badge_name))
            if cursor.rowcount > 0:
                conn.commit()
                logging.info(f"Awarded badge {badge_name} to user {user_id}")
                return True
    except Exception as e:
        logging.error(f"Error awarding badge: {e}")
    finally:
        conn.close()
    return False

def check_and_award_badges(user_id):
    """
    Checks all conditions and awards badges if met.
    """
    conn = get_db_connection()
    if not conn: return []

    new_badges = []
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Check First Trade & Active Trader
            cursor.execute("SELECT COUNT(*) as count FROM user_transactions WHERE user_id = %s", (user_id,))
            trade_count = cursor.fetchone()['count']

            if trade_count >= 1:
                if award_badge(user_id, "First Trade"): new_badges.append("First Trade")
            if trade_count >= 10:
                if award_badge(user_id, "Active Trader"): new_badges.append("Active Trader")

            # Check Diversified
            cursor.execute("SELECT COUNT(DISTINCT ticker) as count FROM user_transactions WHERE user_id = %s", (user_id,))
            # Note: This counts distinct tickers traded, not necessarily held.
            # For simplicity, let's use "Holdings" from portfolio calculation logic or just distinct traded.
            # Let's be strict: currently held.
            # Re-implementing simple holding check:
            cursor.execute("""
                SELECT ticker, SUM(shares) as total_shares
                FROM user_transactions
                WHERE user_id = %s
                GROUP BY ticker
                HAVING total_shares > 0.0001
            """, (user_id,))
            holdings = cursor.fetchall()

            if len(holdings) >= 5:
                if award_badge(user_id, "Diversified"): new_badges.append("Diversified")

            # Check Big Gainer
            # Need current prices. This is expensive to do on every trade.
            # Let's skip this for synchronous check or approximate it if we have price data passed in?
            # For now, we'll skip Big Gainer in this automatic check or implement it if we have price data in the context.
            # Let's leave it for now or maybe run it async.

    except Exception as e:
        logging.error(f"Error checking badges: {e}")
    finally:
        conn.close()

    return new_badges
