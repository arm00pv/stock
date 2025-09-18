import os
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from database import (
    init_db, get_portfolio_summary, get_portfolio_holdings,
    save_daily_pick, get_pick_history_for_category, get_recently_picked_tickers,
    execute_investment
)

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# Initialize the database
init_db()

# Using hardcoded lists for stability during the reset
TICKER_CATEGORIES = {
    'hot_stock': ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'JNJ', 'V'],
    'penny_stock': ['SNDL', 'CTRM', 'ZOM', 'AMC', 'BB', 'EXPR', 'GSAT', 'NAKD', 'TXMD', 'GNUS'],
    'monthly_dividend': ['O', 'MAIN', 'STAG', 'GAIN', 'GOOD', 'PBA', 'SBR', 'ADC', 'EPR', 'LTC'],
    'high_yield': ['AGNC', 'ORC', 'PSEC', 'ARR', 'MFA', 'IVR', 'TWO', 'EARN', 'OXLC', 'HRZN']
}

def find_stock_of_the_day(category, price_limit=None):
    """Picks the first stock from a hardcoded list that hasn't been picked recently."""
    all_tickers = TICKER_CATEGORIES.get(category, [])
    recent_picks = get_recently_picked_tickers(category, days=7)
    for ticker in all_tickers:
        if ticker in recent_picks:
            continue
        if price_limit:
            try:
                price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
                if price > price_limit:
                    continue
            except Exception:
                continue
        return ticker
    return all_tickers[0] if all_tickers else None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/daily-pick/<category_key>')
def api_daily_pick(category_key):
    if category_key not in TICKER_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 404

    price_limit = 5 if category_key == 'penny_stock' else None
    ticker = find_stock_of_the_day(category_key, price_limit)

    if ticker:
        save_daily_pick(category_key, ticker)

    history = get_pick_history_for_category(category_key)
    latest_pick = history[0]['ticker'] if history else "N/A"
    return jsonify({'ticker': latest_pick, 'history': history})

@app.route('/api/all-portfolios')
def all_portfolios_data():
    """
    This single, efficient endpoint fetches all data for all portfolios.
    """
    portfolio_names = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment']
    all_holdings = {}
    all_tickers = set()

    # Step 1: Gather all holdings and unique tickers
    for name in portfolio_names:
        holdings = get_portfolio_holdings(name)
        all_holdings[name] = holdings
        for holding in holdings:
            all_tickers.add(holding['ticker'])

    # Step 2: Batch fetch all prices in one go
    price_data = {}
    if all_tickers:
        try:
            data = yf.download(list(all_tickers), period='1d', progress=False)
            if not data.empty and 'Close' in data and not data['Close'].empty:
                # Handle both single and multi-ticker responses
                if len(all_tickers) == 1:
                    price_data[list(all_tickers)[0]] = data['Close'].iloc[-1]
                else:
                    price_data = data['Close'].iloc[-1].to_dict()
        except Exception as e:
            print(f"CRITICAL: Main yfinance batch download failed: {e}")

    # Step 3: Process each portfolio with the fetched prices
    response_data = {}
    for name in portfolio_names:
        summary = get_portfolio_summary(name)
        holdings = all_holdings[name]

        total_market_value = 0.0

        for holding in holdings:
            current_price = price_data.get(holding['ticker'])
            if current_price is None or pd.isna(current_price):
                current_price = float(holding['purchase_price']) # Fallback

            holding['current_price'] = current_price
            holding['current_value'] = float(holding['shares']) * current_price
            holding['cost_basis'] = float(holding['shares']) * float(holding['purchase_price'])
            holding['gain_loss'] = holding['current_value'] - holding['cost_basis']
            total_market_value += holding['current_value']

        total_capital_invested = summary[1]
        # Note: total_cost_basis is the sum of cost_basis of *current* holdings, which can change.
        # total_capital_invested is the sum of all money *put into* the portfolio. This is the correct base for ROI.
        total_gain_loss = total_market_value - sum(h['cost_basis'] for h in holdings)

        roi_percentage = (total_gain_loss / total_capital_invested) * 100 if total_capital_invested > 0 else 0

        response_data[name] = {
            'portfolio_name': name,
            'cash_balance': summary[0],
            'total_invested': total_capital_invested,
            'current_market_value': total_market_value,
            'total_assets': summary[0] + total_market_value,
            'total_gain_loss': total_gain_loss,
            'roi_percentage': roi_percentage,
            'holdings': holdings
        }

    return jsonify(response_data)

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00
    category_map = {
        'main': 'hot_stock',
        'monthly_dividend': 'monthly_dividend',
        'high_yield_investment': 'high_yield',
        'daily_investment': 'hot_stock'
    }
    category = category_map.get(portfolio_name)

    if not category:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name'}), 404

    price_limit = 5 if category == 'penny_stock' else None
    ticker = find_stock_of_the_day(category, price_limit)

    if not ticker:
        return jsonify({'status': 'error', 'message': 'No suitable stock found.'})

    try:
        price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
        if not price or price <= 0:
            raise ValueError("Invalid price")

        shares = investment_amount / price
        execute_investment(portfolio_name, ticker, shares, price, investment_amount)
        return jsonify({'status': 'success', 'message': f'Successfully invested in {ticker}.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to invest in {ticker}: {e}'}), 500
