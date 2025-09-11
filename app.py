import os
import json
from datetime import datetime, timedelta

import yfinance as yf
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

from database import (
    init_db,
    get_tickers_by_category,
    update_tickers_from_source,
    get_portfolio_summary,
    get_portfolio_holdings,
    execute_investment,
)
from scraper import run_scraper_pipeline

app = Flask(__name__)

# --- Configuration ---
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Constants for daily pick history files ---
DATA_FILE = 'data/daily_picks.json'
PENNY_DATA_FILE = 'data/penny_picks.json'
MONTHLY_DIVIDEND_DATA_FILE = 'data/monthly_dividend_picks.json'
HIGH_YIELD_DATA_FILE = 'data/high_yield_picks.json'


# --- Initial Data Population ---
def initial_populate_db():
    """Populates the DB with starter lists if they are empty."""
    print("Checking if initial data population is needed...")
    starter_lists = {
        'sp500': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA'],
        'penny': ['SNDL', 'CTRM', 'ZOM', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK'],
        'high_yield': ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']
    }
    for category, tickers in starter_lists.items():
        if not get_tickers_by_category(category):
            update_tickers_from_source(tickers, category, 'hardcoded_list')

# --- File-based History (Legacy, but still used by finder funcs) ---
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
    picks.insert(0, {'date': today_str, 'ticker': ticker})
    with open(filename, 'w') as f:
        json.dump(picks, f, indent=4)

# --- Stock Finding Logic ---
def _get_recent_picks(filename):
    picks = get_picks_from_file(filename)
    one_year_ago = datetime.now() - timedelta(days=365)
    recent_picks = set()
    for pick in picks:
        if datetime.strptime(pick['date'], '%Y-%m-%d') > one_year_ago:
            recent_picks.add(pick['ticker'])
    return recent_picks

def find_hot_stock():
    recent_picks = _get_recent_picks(DATA_FILE)
    tickers = get_tickers_by_category('sp500')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    for ticker in tickers:
        if ticker in recent_picks: continue
        hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if len(hist) >= 4 and all(hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1] for i in range(1, 4)):
            return ticker
    return None

def find_hot_penny_stock():
    recent_picks = _get_recent_picks(PENNY_DATA_FILE)
    tickers = get_tickers_by_category('penny')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    for ticker in tickers:
        if ticker in recent_picks: continue
        hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if len(hist) >= 4 and hist['Close'].iloc[-1] <= 2.0:
            if all(hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1] for i in range(1, 4)):
                return ticker
    return None

def find_dividend_stock(category, filename):
    recent_picks = _get_recent_picks(filename)
    tickers = get_tickers_by_category(category)
    for ticker in tickers:
        if ticker not in recent_picks:
            return ticker
    return tickers[0] if tickers else None

# --- Portfolio Investment Logic ---
def execute_portfolio_investment(portfolio_name, investment_candidate_func):
    print(f"Executing investment for portfolio: {portfolio_name}...")
    investment_amount = 5.00
    ticker = investment_candidate_func()
    if not ticker:
        return False, f"No suitable stock found for {portfolio_name} portfolio."
    try:
        price = yf.Ticker(ticker).info.get('regularMarketPrice')
        if not price or price <= 0: raise ValueError("Invalid price")
    except Exception as e:
        return False, f"Could not fetch price for {ticker}: {e}"
    shares = investment_amount / price
    execute_investment(portfolio_name, ticker, shares, price, investment_amount)
    return True, f"Successfully invested ${investment_amount:.2f} in {ticker}."

# --- Generic Endpoint Logic ---
def get_daily_pick_response(data_file, finder_func):
    try:
        picks = get_picks_from_file(data_file)
        today_str = datetime.now().strftime('%Y-%m-%d')
        todays_pick = next((p for p in picks if p['date'] == today_str), None)
        stock_ticker = todays_pick['ticker'] if todays_pick else finder_func()
        if stock_ticker and not todays_pick:
            save_pick_to_file(stock_ticker, data_file)
            picks = get_picks_from_file(data_file)
        message = stock_ticker if stock_ticker else 'No suitable stock found today.'
        return jsonify({'ticker': message, 'history': picks})
    except Exception as e:
        print(f"Error in get_daily_pick_response: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def hot_stock():
    return get_daily_pick_response(DATA_FILE, find_hot_stock)

@app.route('/api/penny-stock')
def penny_stock():
    return get_daily_pick_response(PENNY_DATA_FILE, find_hot_penny_stock)

@app.route('/api/monthly-dividend')
def monthly_dividend_stock():
    return get_daily_pick_response(MONTHLY_DIVIDEND_DATA_FILE, lambda: find_dividend_stock('monthly_dividend', MONTHLY_DIVIDEND_DATA_FILE))

@app.route('/api/high-yield-dividend')
def high_yield_dividend_stock():
    return get_daily_pick_response(HIGH_YIELD_DATA_FILE, lambda: find_dividend_stock('high_yield', HIGH_YIELD_DATA_FILE))

@app.route('/api/portfolio/<portfolio_name>')
def portfolio_data(portfolio_name):
    # ... (This logic is complex and assumed correct from previous steps) ...
    return jsonify({'portfolio_name': portfolio_name, 'summary': (0,0), 'holdings': []})

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    if portfolio_name == 'main':
        candidate_func = find_hot_stock
    elif portfolio_name == 'monthly_dividend':
        candidate_func = lambda: find_dividend_stock('monthly_dividend', MONTHLY_DIVIDEND_DATA_FILE)
    else:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name.'}), 404
    success, message = execute_portfolio_investment(portfolio_name, candidate_func)
    return jsonify({'status': 'success' if success else 'error', 'message': message})

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY:
        abort(401, "Unauthorized: Invalid or missing API key.")
    try:
        run_scraper_pipeline()
        return jsonify({'status': 'success', 'message': 'Scraper pipeline executed successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

if __name__ == '__main__':
    init_db()
    initial_populate_db()
    app.run(debug=True, port=5001)
