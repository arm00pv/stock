from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE = 'data/daily_picks.json'

def get_sp500_tickers():
    # For demonstration purposes, using a small list of tickers.
    # In a real-world scenario, you might fetch this list from a reliable source.
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA']

def find_hot_stock():
    tickers = get_sp500_tickers()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    for ticker in tickers:
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)

        if len(hist) < 4:
            continue

        # Check for 3 consecutive days of growth
        positive_days = 0
        for i in range(1, 4):
            if hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1]:
                positive_days += 1
            else:
                break

        if positive_days >= 3:
            return ticker

    return None

def get_daily_picks():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

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


if __name__ == '__main__':
    app.run(debug=True, port=5001)
