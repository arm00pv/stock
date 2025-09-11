from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
import os
from flask import request, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from database import (
    get_tickers_by_category, add_tickers_to_db, init_db, execute_investment,
    get_portfolio_summary, get_portfolio_holdings
)
from scraper import run_scraper_pipeline

app = Flask(__name__)

# Secret key for securing the scraper endpoint
# In a real production environment, this should be set as an environment variable
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')

# Apply the ProxyFix middleware to handle the X-Forwarded-Prefix header
# This is crucial for running the app in a subdirectory behind a reverse proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

DATA_FILE = 'data/daily_picks.json'
PENNY_DATA_FILE = 'data/penny_picks.json'
MONTHLY_DIVIDEND_DATA_FILE = 'data/monthly_dividend_picks.json'
HIGH_YIELD_DATA_FILE = 'data/high_yield_picks.json'


# --- Ticker Data Source ---
# The get_tickers_by_category function from database.py is now the source of truth.
# The hardcoded lists below are used only for the one-time initial population of the database.

def initial_populate_db():
    """
    Populates the database with initial hardcoded lists if they don't exist.
    This ensures the app works out-of-the-box before the scraper is run.
    """
    print("Checking if initial data population is needed...")
    # S&P 500
    if not get_tickers_by_category('sp500'):
        sp500_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA']
        add_tickers_to_db(sp500_tickers, 'sp500')
    # Penny Stocks
    if not get_tickers_by_category('penny'):
        penny_tickers = ['SNDL', 'NAKD', 'CTRM', 'ZOM', 'TXMD', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK']
        add_tickers_to_db(penny_tickers, 'penny')
    # High Yield
    if not get_tickers_by_category('high_yield'):
        high_yield_tickers = ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']
        add_tickers_to_db(high_yield_tickers, 'high_yield')
    # The 'monthly_dividend' category is intentionally left to be populated by the scraper.

# --- Generic Data Handling Functions ---
def get_picks_from_file(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_pick_to_file(ticker, filename):
    picks = get_picks_from_file(filename)
    today_str = datetime.now().strftime('%Y-%m-%d')

    if any(p['date'] == today_str for p in picks):
        return

    new_pick = {'date': today_str, 'ticker': ticker}
    picks.insert(0, new_pick)

    with open(filename, 'w') as f:
        json.dump(picks, f, indent=4)

# --- Hot Stock (S&P 500) Logic ---
def find_hot_stock():
    picks = get_picks_from_file(DATA_FILE)
    one_year_ago = datetime.now() - timedelta(days=365)

    recent_picks = set()
    for pick in picks:
        pick_date = datetime.strptime(pick['date'], '%Y-%m-%d')
        if pick_date > one_year_ago:
            recent_picks.add(pick['ticker'])

    tickers = get_tickers_by_category('sp500')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    for ticker in tickers:
        if ticker in recent_picks:
            continue

        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)

        if len(hist) < 4:
            continue

        # Check for 3 consecutive days of growth
        positive_days = 0
        for i in range(1, 4):
            # Check if there is enough data points
            if len(hist['Close']) > i+1:
                if hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1]:
                    positive_days += 1
                else:
                    break

        if positive_days >= 3:
            return ticker

    return None

# --- Penny Stock Logic ---
def find_hot_penny_stock():
    picks = get_picks_from_file(PENNY_DATA_FILE)
    one_year_ago = datetime.now() - timedelta(days=365)

    recent_picks = set()
    for pick in picks:
        pick_date = datetime.strptime(pick['date'], '%Y-%m-%d')
        if pick_date > one_year_ago:
            recent_picks.add(pick['ticker'])

    tickers = get_tickers_by_category('penny')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    for ticker in tickers:
        if ticker in recent_picks:
            continue

        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)

        if len(hist) < 4:
            continue

        # Price check for penny stocks
        last_price = hist['Close'].iloc[-1]
        if last_price > 2.0:
            continue

        # Check for 3 consecutive days of growth
        positive_days = 0
        for i in range(1, 4):
            if len(hist['Close']) > i+1:
                if hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1]:
                    positive_days += 1
                else:
                    break

        if positive_days >= 3:
            return ticker

    return None


# --- Portfolio Logic ---
def invest_weekly_five_dollars():
    """
    Selects a stock based on the "hot stock" logic and simulates investing $5.
    """
    print("Attempting to execute weekly investment...")
    investment_amount = 5.00

    # Use the existing hot_stock logic to find a candidate
    ticker = find_hot_stock()

    if not ticker:
        print("No suitable stock found for investment today.")
        return False, "No suitable stock found for investment."

    # Get the latest price for the chosen ticker
    try:
        stock = yf.Ticker(ticker)
        # Use 'regularMarketPrice' for a more current price if available, else fall back to previous close.
        price = stock.info.get('regularMarketPrice') or stock.history(period='1d')['Close'].iloc[-1]

        if price is None or price <= 0:
            raise ValueError("Invalid price received.")

    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return False, f"Could not fetch price for {ticker}."

    # Calculate fractional shares and execute the investment in the database
    shares = investment_amount / price
    execute_investment(ticker, shares, price, investment_amount)

    return True, f"Successfully invested ${investment_amount} in {ticker}."


# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def hot_stock():
    try:
        picks = get_picks_from_file(DATA_FILE)
        today_str = datetime.now().strftime('%Y-%m-%d')

        todays_pick = next((p for p in picks if p['date'] == today_str), None)

        if todays_pick:
            stock_ticker = todays_pick['ticker']
        else:
            stock_ticker = find_hot_stock()
            if stock_ticker:
                save_pick_to_file(stock_ticker, DATA_FILE)
                picks = get_picks_from_file(DATA_FILE) # Refresh picks

        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No hot stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/hot-stock: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

@app.route('/api/penny-stock')
def penny_stock():
    try:
        picks = get_picks_from_file(PENNY_DATA_FILE)
        today_str = datetime.now().strftime('%Y-%m-%d')

        todays_pick = next((p for p in picks if p['date'] == today_str), None)

        if todays_pick:
            stock_ticker = todays_pick['ticker']
        else:
            stock_ticker = find_hot_penny_stock()
            if stock_ticker:
                save_pick_to_file(stock_ticker, PENNY_DATA_FILE)
                picks = get_picks_from_file(PENNY_DATA_FILE) # Refresh picks

        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No hot penny stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/penny-stock: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

# --- Dividend Stock Logic ---
def find_dividend_stock(filename, category):
    """A generic function to find a stock from a list that hasn't been picked recently."""
    picks = get_picks_from_file(filename)
    one_year_ago = datetime.now() - timedelta(days=365)

    recent_picks = set()
    for pick in picks:
        pick_date = datetime.strptime(pick['date'], '%Y-%m-%d')
        if pick_date > one_year_ago:
            recent_picks.add(pick['ticker'])

    tickers = get_tickers_by_category(category)

    for ticker in tickers:
        if ticker not in recent_picks:
            # For dividend stocks, we just need one that hasn't been picked.
            # A more complex algorithm could be added later if needed.
            return ticker

    # If all have been picked recently, just return the first one from the list.
    return tickers[0] if tickers else None

# --- API Endpoints ---
@app.route('/api/monthly-dividend')
def monthly_dividend_stock():
    try:
        picks = get_picks_from_file(MONTHLY_DIVIDEND_DATA_FILE)
        today_str = datetime.now().strftime('%Y-%m-%d')

        todays_pick = next((p for p in picks if p['date'] == today_str), None)

        if todays_pick:
            stock_ticker = todays_pick['ticker']
        else:
            stock_ticker = find_dividend_stock(MONTHLY_DIVIDEND_DATA_FILE, 'monthly_dividend')
            if stock_ticker:
                save_pick_to_file(stock_ticker, MONTHLY_DIVIDEND_DATA_FILE)
                picks = get_picks_from_file(MONTHLY_DIVIDEND_DATA_FILE)

        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No monthly dividend stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/monthly-dividend: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

@app.route('/api/high-yield-dividend')
def high_yield_dividend_stock():
    try:
        picks = get_picks_from_file(HIGH_YIELD_DATA_FILE)
        today_str = datetime.now().strftime('%Y-%m-%d')

        todays_pick = next((p for p in picks if p['date'] == today_str), None)

        if todays_pick:
            stock_ticker = todays_pick['ticker']
        else:
            stock_ticker = find_dividend_stock(HIGH_YIELD_DATA_FILE, 'high_yield')
            if stock_ticker:
                save_pick_to_file(stock_ticker, HIGH_YIELD_DATA_FILE)
                picks = get_picks_from_file(HIGH_YIELD_DATA_FILE)

        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No high yield dividend stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/high-yield-dividend: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

@app.route('/api/portfolio')
def portfolio_data():
    try:
        summary = get_portfolio_summary()
        holdings_db = get_portfolio_holdings()

        holdings_with_current_value = []
        total_portfolio_value = 0

        # Create a set of unique tickers to fetch prices efficiently
        unique_tickers = {h[0] for h in holdings_db}

        # yfinance allows fetching multiple tickers at once
        if unique_tickers:
            tickers_data = yf.Tickers(list(unique_tickers))

            # Group holdings by ticker to sum up shares
            holdings_by_ticker = {}
            for ticker, shares, purchase_price, purchase_date in holdings_db:
                if ticker not in holdings_by_ticker:
                    holdings_by_ticker[ticker] = {'shares': 0, 'total_cost': 0}
                holdings_by_ticker[ticker]['shares'] += shares
                holdings_by_ticker[ticker]['total_cost'] += shares * purchase_price

            for ticker_symbol, holding_info in holdings_by_ticker.items():
                try:
                    # Access the specific ticker's data
                    ticker_obj = tickers_data.tickers.get(ticker_symbol.upper())
                    current_price = ticker_obj.info.get('regularMarketPrice') or ticker_obj.history(period='1d')['Close'].iloc[-1]
                    current_value = holding_info['shares'] * current_price
                    total_portfolio_value += current_value

                    holdings_with_current_value.append({
                        'ticker': ticker_symbol,
                        'shares': holding_info['shares'],
                        'average_cost': holding_info['total_cost'] / holding_info['shares'],
                        'current_price': current_price,
                        'current_value': current_value
                    })
                except Exception as e:
                    print(f"Could not fetch current price for {ticker_symbol}: {e}")
                    # If price fetch fails, use last known value (cost basis) for that holding
                    cost_value = holding_info['total_cost']
                    total_portfolio_value += cost_value
                    holdings_with_current_value.append({
                        'ticker': ticker_symbol,
                        'shares': holding_info['shares'],
                        'average_cost': holding_info['total_cost'] / holding_info['shares'],
                        'current_price': 'N/A',
                        'current_value': cost_value
                    })

        return jsonify({
            'cash_balance': summary[0],
            'total_invested': summary[1],
            'holdings_value': total_portfolio_value,
            'total_portfolio_value': summary[0] + total_portfolio_value, # Cash + Holdings
            'holdings': holdings_with_current_value
        })

    except Exception as e:
        print(f"Error in /api/portfolio: {e}")
        return jsonify({'error': 'Could not retrieve portfolio data.'}), 500

@app.route('/api/trigger-investment', methods=['POST'])
def trigger_investment():
    # Note: In a real-world production environment, this endpoint should be
    # secured with an API key or other authentication mechanism to prevent abuse.
    success, message = invest_weekly_five_dollars()
    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message}), 500

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    # --- Security Check ---
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != SCRAPER_API_KEY:
        abort(401, description="Unauthorized: Invalid or missing API key.")

    try:
        # Running the scraper in a separate thread could be a future improvement
        # to avoid long request times, but for now, we run it synchronously.
        print("Scraper run triggered by API call.")
        run_scraper_pipeline()
        return jsonify({'status': 'success', 'message': 'Scraper pipeline executed successfully.'})
    except Exception as e:
        print(f"Error during API-triggered scrape: {e}")
        return jsonify({'status': 'error', 'message': 'An error occurred during the scrape.'}), 500

if __name__ == '__main__':
    init_db()
    initial_populate_db()
    app.run(debug=True, port=5001)
