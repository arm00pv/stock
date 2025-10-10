import os
from datetime import datetime
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from database import (
    init_db, get_all_portfolios_data,
    save_daily_pick, get_pick_history_for_category, get_recently_picked_tickers,
    execute_investment, get_ai_settings, save_ai_settings, execute_sale
)
from ai_picker import get_ai_recommendation
from backtesting import run_backtest
from decimal import Decimal
from cache import yf_download_cached

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/daily-pick/<category_key>')
def api_daily_pick(category_key):
    if category_key not in TICKER_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 404

    history = get_pick_history_for_category(category_key)
    today_str = datetime.now().strftime('%Y-%m-%d')
    todays_pick_ticker = None

    if history:
        latest_pick_date_str = history[0]['pick_date'].strftime('%Y-%m-%d')
        if latest_pick_date_str == today_str:
            todays_pick_ticker = history[0]['ticker']

    if not todays_pick_ticker:
        price_limit = 5 if category_key == 'penny_stock' else None
        todays_pick_ticker = get_ai_recommendation(category_key, TICKER_CATEGORIES.get(category_key, []), price_limit)
        if todays_pick_ticker:
            save_daily_pick(category_key, todays_pick_ticker)
            history = get_pick_history_for_category(category_key)

    latest_pick_to_display = history[0]['ticker'] if history else "N/A"
    return jsonify({'ticker': latest_pick_to_display, 'history': history})

@app.route('/api/all-portfolios')
def all_portfolios_data():
    try:
        summaries, all_holdings = get_all_portfolios_data()
        all_tickers = {holding['ticker'] for holdings in all_holdings.values() for holding in holdings}

        price_data = {}
        if all_tickers:
            data = yf_download_cached(list(all_tickers), period='1d', progress=False, raise_errors=False)
            if not data.empty and 'Close' in data:
                close_prices = data['Close']
                if isinstance(close_prices, pd.Series):
                    # Single ticker case
                    if not close_prices.empty and not pd.isna(close_prices.iloc[-1]):
                        price_data[list(all_tickers)[0]] = close_prices.iloc[-1]
                else:
                    # Multiple tickers case
                    if not close_prices.empty:
                        last_prices = close_prices.iloc[-1]
                        price_data = last_prices.dropna().to_dict()

        response_data = {}
        for name, summary in summaries.items():
            holdings = all_holdings.get(name, [])
            total_market_value = 0.0

            for holding in holdings:
                current_price = price_data.get(holding['ticker'])
                if not current_price or pd.isna(current_price):
                    current_price = float(holding['purchase_price'])

                holding.update({
                    'shares': float(holding['shares']),
                    'purchase_price': float(holding['purchase_price']),
                    'current_price': current_price,
                    'cost_basis': float(holding['shares']) * float(holding['purchase_price']),
                    'current_value': float(holding['shares']) * current_price,
                    'gain_loss': (float(holding['shares']) * current_price) - (float(holding['shares']) * float(holding['purchase_price']))
                })
                total_market_value += holding['current_value']

            total_capital_invested = float(summary['total_invested'])
            cash_balance = float(summary['cash_balance'])
            roi_percentage = ((total_market_value - total_capital_invested) / total_capital_invested) * 100 if total_capital_invested > 0 else 0

            response_data[name] = {
                'portfolio_name': name,
                'cash_balance': cash_balance,
                'total_invested': total_capital_invested,
                'current_market_value': total_market_value,
                'total_assets': cash_balance + total_market_value,
                'total_gain_loss': total_market_value - total_capital_invested,
                'roi_percentage': roi_percentage,
                'holdings': holdings
            }
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': f'Failed to load portfolio data: {e}'}), 500

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00
    category_map = {'main': 'hot_stock', 'monthly_dividend': 'monthly_dividend', 'high_yield_investment': 'high_yield', 'daily_investment': 'hot_stock'}
    category = category_map.get(portfolio_name)

    if not category:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name'}), 404

    price_limit = 5 if category == 'penny_stock' else None
    ticker = get_ai_recommendation(category, TICKER_CATEGORIES.get(category, []), price_limit)

    if not ticker:
        return jsonify({'status': 'error', 'message': 'No suitable stock found.'})

    try:
        price_history = yf_download_cached(ticker, period="1d")
        if price_history.empty or 'Close' not in price_history or price_history['Close'].iloc[-1] <= 0:
            raise ValueError("Invalid or zero price from yfinance")

        price = price_history['Close'].iloc[-1]
        shares = investment_amount / price
        execute_investment(portfolio_name, ticker, shares, price, investment_amount)
        return jsonify({'status': 'success', 'message': f'Successfully invested in {ticker}.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to invest in {ticker}: {e}'}), 500

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    initial_capital = float(data.get('initial_capital', 10000))
    investment_amount = float(data.get('investment_amount', 100))
    category = data.get('category')
    short_ma = int(data.get('short_ma', 50))
    long_ma = int(data.get('long_ma', 200))

    if not all([start_date, end_date, category]):
        return jsonify({'error': 'Missing required parameters'}), 400

    tickers = TICKER_CATEGORIES.get(category)
    if not tickers:
        return jsonify({'error': 'Invalid category'}), 400

    results = run_backtest(start_date, end_date, initial_capital, investment_amount, category, tickers, short_ma, long_ma)
    return jsonify(results)

@app.route('/api/settings/<category>', methods=['GET'])
def api_get_settings(category):
    settings = get_ai_settings(category)
    if not settings:
        return jsonify({'error': 'Settings not found for this category'}), 404
    for key, value in settings.items():
        if isinstance(value, Decimal):
            settings[key] = float(value)
    return jsonify(settings)

@app.route('/api/sell-stock', methods=['POST'])
def api_sell_stock():
    data = request.get_json()
    portfolio_name = data.get('portfolio_name')
    ticker = data.get('ticker')
    shares_to_sell = data.get('shares')

    if not all([portfolio_name, ticker, shares_to_sell]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    try:
        price_history = yf_download_cached(ticker, period="1d")
        if price_history.empty or 'Close' not in price_history or price_history['Close'].iloc[-1] <= 0:
            raise ValueError("Invalid or zero price from yfinance")

        price = price_history['Close'].iloc[-1]

        success, message = execute_sale(portfolio_name, ticker, float(shares_to_sell), price)
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to sell {ticker}: {e}'}), 500

@app.route('/api/settings/<category>', methods=['POST'])
def api_save_settings(category):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid data'}), 400

    required_keys = ['momentum_weight', 'value_weight', 'ma_weight', 'volatility_weight', 'volume_weight', 'sentiment_weight']
    if not all(key in data for key in required_keys):
        return jsonify({'error': 'Missing one or more weight parameters'}), 400

    save_ai_settings(category, data)
    return jsonify({'status': 'success', 'message': 'Settings saved successfully.'})