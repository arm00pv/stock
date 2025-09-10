from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Apply the ProxyFix middleware to handle the X-Forwarded-Prefix header
# This is crucial for running the app in a subdirectory behind a reverse proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

DATA_FILE = 'data/daily_picks.json'
PENNY_DATA_FILE = 'data/penny_picks.json'
MONTHLY_DIVIDEND_DATA_FILE = 'data/monthly_dividend_picks.json'
HIGH_YIELD_DATA_FILE = 'data/high_yield_picks.json'


# --- Ticker Functions ---
def get_sp500_tickers():
    # For demonstration purposes, using a small list of tickers.
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA']

def get_penny_stock_tickers():
    # A sample list of penny stocks.
    return ['SNDL', 'NAKD', 'CTRM', 'ZOM', 'TXMD', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK']

def get_monthly_dividend_tickers():
    # A sample list of stocks/ETFs known for paying monthly dividends.
    return ['O', 'MAIN', 'STAG', 'GAIN', 'GOOD', 'PBA', 'SBR', 'AGNC', 'LTC', 'ADC']

def get_high_yield_tickers():
    # A sample list of stocks/ETFs known for high dividend yields.
    return ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']

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

    tickers = get_sp500_tickers()
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

    tickers = get_penny_stock_tickers()
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


# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def hot_stock():
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

@app.route('/api/penny-stock')
def penny_stock():
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

# --- Dividend Stock Logic ---
def find_dividend_stock(filename, ticker_function):
    """A generic function to find a stock from a list that hasn't been picked recently."""
    picks = get_picks_from_file(filename)
    one_year_ago = datetime.now() - timedelta(days=365)

    recent_picks = set()
    for pick in picks:
        pick_date = datetime.strptime(pick['date'], '%Y-%m-%d')
        if pick_date > one_year_ago:
            recent_picks.add(pick['ticker'])

    tickers = ticker_function()

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
    picks = get_picks_from_file(MONTHLY_DIVIDEND_DATA_FILE)
    today_str = datetime.now().strftime('%Y-%m-%d')

    todays_pick = next((p for p in picks if p['date'] == today_str), None)

    if todays_pick:
        stock_ticker = todays_pick['ticker']
    else:
        stock_ticker = find_dividend_stock(MONTHLY_DIVIDEND_DATA_FILE, get_monthly_dividend_tickers)
        if stock_ticker:
            save_pick_to_file(stock_ticker, MONTHLY_DIVIDEND_DATA_FILE)
            picks = get_picks_from_file(MONTHLY_DIVIDEND_DATA_FILE)

    if stock_ticker:
        return jsonify({'ticker': stock_ticker, 'history': picks})
    else:
        return jsonify({'ticker': 'No monthly dividend stock found today.', 'history': picks})

@app.route('/api/high-yield-dividend')
def high_yield_dividend_stock():
    picks = get_picks_from_file(HIGH_YIELD_DATA_FILE)
    today_str = datetime.now().strftime('%Y-%m-%d')

    todays_pick = next((p for p in picks if p['date'] == today_str), None)

    if todays_pick:
        stock_ticker = todays_pick['ticker']
    else:
        stock_ticker = find_dividend_stock(HIGH_YIELD_DATA_FILE, get_high_yield_tickers)
        if stock_ticker:
            save_pick_to_file(stock_ticker, HIGH_YIELD_DATA_FILE)
            picks = get_picks_from_file(HIGH_YIELD_DATA_FILE)

    if stock_ticker:
        return jsonify({'ticker': stock_ticker, 'history': picks})
    else:
        return jsonify({'ticker': 'No high yield dividend stock found today.', 'history': picks})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
