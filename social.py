from database import get_db_connection
from gamification import get_user_badges
from personal_portfolio import get_portfolio_status

def get_public_profile(username):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id, username, beta_active FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user: return None

            user_id = user['id']
            badges = get_user_badges(user_id)

            # Basic Portfolio Stats (Safe subset)
            cursor.execute("SELECT start_date, total_invested, cash_balance FROM user_portfolios WHERE user_id = %s", (user_id,))
            portfolio = cursor.fetchone()

            # Calculate Total Equity for display
            equity = 0
            if portfolio:
                equity = float(portfolio['cash_balance']) + float(portfolio['total_invested'])

            # Get best trade (highest return)
            cursor.execute("""
                SELECT ticker, (price * shares) as volume, action
                FROM user_transactions
                WHERE user_id = %s
                ORDER BY volume DESC
                LIMIT 1
            """, (user_id,))
            best_trade = cursor.fetchone()

            return {
                'username': user['username'],
                'is_beta': bool(user['beta_active']),
                'badges': [b for b in badges if b['earned']],
                'member_since': portfolio['start_date'].strftime('%Y-%m-%d') if portfolio else 'N/A',
                'total_equity': equity,
                'top_trade': best_trade['ticker'] if best_trade else 'None'
            }
    finally:
        conn.close()
