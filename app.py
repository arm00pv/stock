from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
import os
from flask import request, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from database import (
    get_tickers_by_category, update_tickers_from_source, init_db, execute_investment,
    get_portfolio_summary, get_portfolio_holdings
)
from scraper import run_scraper_pipeline

app = Flask(__name__)

# Secret key for securing the scraper endpoint
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Constants for daily pick history files ---
DATA_FILE = 'data/daily_picks.json'
PENNY_DATA_FILE = 'data/penny_picks.json'
MONTHLY_DIVIDEND_DATA_FILE = 'data/monthly_dividend_picks.json'
HIGH_YIELD_DATA_FILE = 'data/high_yield_picks.json'


def initial_populate_db():
    print("Checking if initial data population is needed...")
    categories = {
        'sp500': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA'],
        'penny': ['SNDL', 'NAKD', 'CTRM', 'ZOM', 'TXMD', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK'],
        'high_yield': ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']
    }
    for category, tickers in categories.items():
        if not get_tickers_by_category(category):
            update_tickers_from_source(tickers, category, 'hardcoded_list')

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

# --- Stock Finding Logic ---
def find_hot_stock(category='sp500'):
    tickers = get_tickers_by_category(category)
    if not tickers: return None
    for ticker in tickers:
        # Simplified for brevity, in reality, check 3-day growth
        return ticker
    return None

def find_hot_penny_stock():
    tickers = get_tickers_by_category('penny')
    if not tickers: return None
    for ticker in tickers:
        # Simplified for brevity, in reality, check price and 3-day growth
        return ticker
    return None

def find_dividend_stock(category):
    tickers = get_tickers_by_category(category)
    return tickers[0] if tickers else None

# --- Portfolio Investment Logic ---
def execute_portfolio_investment(portfolio_name, investment_candidate_func):
    print(f"Attempting to execute weekly investment for portfolio: {portfolio_name}...")
    investment_amount = 5.00
    ticker = investment_candidate_func()
    if not ticker:
        msg = f"No suitable stock found for {portfolio_name} portfolio."
        print(msg)
        return False, msg
    try:
        stock = yf.Ticker(ticker)
        price = stock.info.get('regularMarketPrice') or stock.history(period='1d')['Close'].iloc[-1]
        if price is None or price <= 0: raise ValueError("Invalid price")
    except Exception as e:
        msg = f"Could not fetch price for {ticker}: {e}"
        print(msg)
        return False, msg
    shares = investment_amount / price
    execute_investment(portfolio_name, ticker, shares, price, investment_amount)
    return True, f"Successfully invested ${investment_amount} in {ticker} for portfolio '{portfolio_name}'."

# --- Generic Endpoint Logic ---
def get_daily_pick(data_file, finder_func):
    picks = get_picks_from_file(data_file)
    today_str = datetime.now().strftime('%Y-%m-%d')
    todays_pick = next((p for p in picks if p['date'] == today_str), None)
    if todays_pick:
        return todays_pick['ticker'], picks
    stock_ticker = finder_func()
    if stock_ticker:
        save_pick_to_file(stock_ticker, data_file)
        picks = get_picks_from_file(data_file)
    return stock_ticker, picks

# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def hot_stock():
    try:
        stock_ticker, picks = get_daily_pick(DATA_FILE, find_hot_stock)
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
        stock_ticker, picks = get_daily_pick(PENNY_DATA_FILE, find_hot_penny_stock)
        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No hot penny stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/penny-stock: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

@app.route('/api/monthly-dividend')
def monthly_dividend_stock():
    try:
        stock_ticker, picks = get_daily_pick(MONTHLY_DIVIDEND_DATA_FILE, lambda: find_dividend_stock('monthly_dividend'))
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
        stock_ticker, picks = get_daily_pick(HIGH_YIELD_DATA_FILE, lambda: find_dividend_stock('high_yield'))
        if stock_ticker:
            return jsonify({'ticker': stock_ticker, 'history': picks})
        else:
            return jsonify({'ticker': 'No high yield dividend stock found today.', 'history': picks})
    except Exception as e:
        print(f"Error in /api/high-yield-dividend: {e}")
        return jsonify({'ticker': 'Error loading data.', 'history': []})

@app.route('/api/portfolio/<portfolio_name>')
def portfolio_data(portfolio_name):
    # ... (Logic remains the same)
    return jsonify({})

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    if portfolio_name == 'main':
        candidate_func = find_hot_stock
    elif portfolio_name == 'monthly_dividend':
        candidate_func = lambda: find_dividend_stock('monthly_dividend')
    else:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name.'}), 404
    success, message = execute_portfolio_investment(portfolio_name, candidate_func)
    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message}), 500

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    # ... (Logic remains the same)
    return jsonify({})

if __name__ == '__main__':
    init_db()
    initial_populate_db()
    app.run(debug=True, port=5001)
