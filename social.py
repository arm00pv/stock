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

def cast_vote(user_id, ticker, vote):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO community_votes (user_id, ticker, vote) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE vote = VALUES(vote)",
                (user_id, ticker, vote)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"Error casting vote: {e}")
        return False
    finally:
        conn.close()

def get_ticker_sentiment(ticker):
    conn = get_db_connection()
    if not conn: return {'bullish': 0, 'bearish': 0, 'total': 0}
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT vote, COUNT(*) as count FROM community_votes WHERE ticker = %s GROUP BY vote",
                (ticker,)
            )
            votes = cursor.fetchall()
            result = {'BULLISH': 0, 'BEARISH': 0}
            for v in votes:
                result[v['vote']] = v['count']

            total = result['BULLISH'] + result['BEARISH']
            bull_pct = (result['BULLISH'] / total * 100) if total > 0 else 0
            bear_pct = (result['BEARISH'] / total * 100) if total > 0 else 0

            return {
                'bullish_pct': bull_pct,
                'bearish_pct': bear_pct,
                'total': total
            }
    finally:
        conn.close()
