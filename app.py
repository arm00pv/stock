from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.exceptions import NotFound

app = Flask(__name__)

DATA_FILE = 'data/daily_picks.json'

def get_sp500_tickers():
    # For demonstration purposes, using a small list of tickers.
    # In a real-world scenario, you might fetch this list from a reliable source.
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA']

def get_daily_picks():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def find_hot_stock():
    picks = get_daily_picks()
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

def save_daily_pick(ticker):
    picks = get_daily_picks()
    today_str = datetime.now().strftime('%Y-%m-%d')

    # Check if a pick for today already exists
    if any(p['date'] == today_str for p in picks):
        return

    new_pick = {
        'date': today_str,
        'ticker': ticker
    }
    picks.insert(0, new_pick) # Add to the beginning of the list

    with open(DATA_FILE, 'w') as f:
        json.dump(picks, f, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def hot_stock():
    picks = get_daily_picks()
    today_str = datetime.now().strftime('%Y-%m-%d')

    # Check if a pick for today has already been saved
    todays_pick = next((p for p in picks if p['date'] == today_str), None)

    if todays_pick:
        stock_ticker = todays_pick['ticker']
    else:
        stock_ticker = find_hot_stock()
        if stock_ticker:
            save_daily_pick(stock_ticker)

    # Refresh picks after potential save
    if not todays_pick and stock_ticker:
        picks = get_daily_picks()

    if stock_ticker:
        return jsonify({
            'ticker': stock_ticker,
            'history': picks
        })
    else:
        return jsonify({
            'ticker': 'No hot stock found today.',
            'history': picks
        }), 404

# Application factory for Gunicorn
def create_app():
    return app

# Add middleware to handle the /stock/ prefix
application = DispatcherMiddleware(NotFound(), {
    '/stock': app
})

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    run_simple('localhost', 5001, application, use_reloader=True, use_debugger=True)
