import yfinance as yf
import pandas as pd
from database import get_db_connection
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_portfolio(user_id):
    conn = get_db_connection()
    if not conn: return False, "Database connection failed"
    try:
        with conn.cursor() as cursor:
            # Check if exists
            cursor.execute("SELECT 1 FROM user_portfolios WHERE user_id = %s", (user_id,))
            if cursor.fetchone():
                return False, "Portfolio already exists"

            cursor.execute("INSERT INTO user_portfolios (user_id, cash_balance) VALUES (%s, 10000.00)", (user_id,))
            conn.commit()
            return True, "Portfolio created with $10,000"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_portfolio_status(user_id):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM user_portfolios WHERE user_id = %s", (user_id,))
            summary = cursor.fetchone()
            if not summary: return None

            # Get holdings by summing transactions
            cursor.execute("""
                SELECT ticker, SUM(shares) as total_shares, AVG(price) as avg_cost
                FROM user_transactions
                WHERE user_id = %s
                GROUP BY ticker
                HAVING total_shares > 0
            """, (user_id,))
            holdings = cursor.fetchall()

            # Fetch current prices
            total_value = float(summary['cash_balance'])
            holdings_list = []

            if holdings:
                tickers = [h['ticker'] for h in holdings]
                try:
                    data = yf.download(tickers, period="1d", progress=False)
                    # Handle yf structure
                    close = data['Close']
                    current_prices = {}
                    if not close.empty:
                        if len(tickers) > 1:
                            current_prices = close.iloc[-1].to_dict()
                        else:
                            current_prices = {tickers[0]: close.iloc[-1]}
                except:
                    current_prices = {}

                holdings_value = 0
                for h in holdings:
                    shares = float(h['total_shares'])
                    ticker = h['ticker']
                    current_price = float(current_prices.get(ticker, h['avg_cost'])) # Fallback to cost
                    value = shares * current_price
                    holdings_value += value

                    holdings_list.append({
                        'ticker': ticker,
                        'shares': shares,
                        'avg_cost': float(h['avg_cost']),
                        'current_price': current_price,
                        'value': value,
                        'return_pct': ((current_price - float(h['avg_cost'])) / float(h['avg_cost']) * 100) if float(h['avg_cost']) > 0 else 0
                    })

                total_value += holdings_value

            return {
                'cash': float(summary['cash_balance']),
                'net_worth': total_value,
                'holdings': holdings_list,
                'total_return_pct': ((total_value - 10000) / 10000) * 100
            }
    finally:
        conn.close()

def execute_user_trade(user_id, ticker, action, amount):
    """
    action: 'BUY' (amount is $) or 'SELL' (amount is shares)
    """
    conn = get_db_connection()
    if not conn: return False, "Database error"

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if hist.empty: return False, "Ticker not found"
        current_price = float(hist['Close'].iloc[-1])

        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT cash_balance FROM user_portfolios WHERE user_id = %s FOR UPDATE", (user_id,))
            portfolio = cursor.fetchone()
            if not portfolio: return False, "Portfolio not found"

            cash = float(portfolio['cash_balance'])

            if action == 'BUY':
                cost = float(amount)
                if cash < cost: return False, "Insufficient funds"

                shares = cost / current_price
                new_cash = cash - cost

                cursor.execute("UPDATE user_portfolios SET cash_balance = %s, total_invested = total_invested + %s WHERE user_id = %s", (new_cash, cost, user_id))
                cursor.execute("INSERT INTO user_transactions (user_id, ticker, action, shares, price) VALUES (%s, %s, 'BUY', %s, %s)",
                               (user_id, ticker, shares, current_price))

            elif action == 'SELL':
                shares_to_sell = float(amount)
                # Check holdings
                cursor.execute("SELECT SUM(shares) as total_shares FROM user_transactions WHERE user_id = %s AND ticker = %s", (user_id, ticker))
                holding = cursor.fetchone()
                if not holding or float(holding['total_shares'] or 0) < shares_to_sell:
                    return False, "Insufficient shares"

                proceeds = shares_to_sell * current_price
                new_cash = cash + proceeds
                cost_basis_reduction = shares_to_sell * current_price # Approximation for simple total_invested logic, or ideally average cost

                cursor.execute("UPDATE user_portfolios SET cash_balance = %s, total_invested = total_invested - %s WHERE user_id = %s", (new_cash, cost_basis_reduction, user_id))
                # Negative shares for sell logic in accumulation, or just track actions.
                # My get_portfolio_status sums shares. So Sell should be negative shares.
                cursor.execute("INSERT INTO user_transactions (user_id, ticker, action, shares, price) VALUES (%s, %s, 'SELL', %s, %s)",
                               (user_id, ticker, -shares_to_sell, current_price))

            conn.commit()
            return True, f"Successfully {action}ed {ticker}"

    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_leaderboard():
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Sort by Total Equity (Cash + Invested)
            # This is cost basis equity, not market value, but fair enough for MVP speed
            cursor.execute("""
                SELECT u.username, (p.cash_balance + p.total_invested) as total_equity, p.start_date
                FROM user_portfolios p
                JOIN users u ON p.user_id = u.id
                ORDER BY total_equity DESC
                LIMIT 10
            """)
            return cursor.fetchall()
    finally:
        conn.close()
