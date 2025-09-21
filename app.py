import os
from datetime import datetime
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import logging
from database import (
    init_db, get_portfolio_summary, get_portfolio_holdings,
    save_daily_pick, get_pick_history_for_category, get_recently_picked_tickers,
    execute_investment
)
from ai_picker import get_ai_recommendation

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# Initialize the database
init_db()

logging.basicConfig(level=logging.INFO,
                    filename='app.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Using hardcoded lists for stability during the reset
TICKER_CATEGORIES = {
    'hot_stock': ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'JNJ', 'V'],
    'penny_stock': ['SNDL', 'CTRM', 'ZOM', 'AMC', 'BB', 'EXPR', 'GSAT', 'NAKD', 'TXMD', 'GNUS'],
    'monthly_dividend': ['O', 'MAIN', 'STAG', 'GAIN', 'GOOD', 'PBA', 'SBR', 'ADC', 'EPR', 'LTC'],
    'high_yield': ['AGNC', 'ORC', 'PSEC', 'ARR', 'MFA', 'IVR', 'TWO', 'EARN', 'OXLC', 'HRZN']
}

def find_stock_of_the_day(category, price_limit=None):
    """Picks a stock using the AI recommendation engine."""
    tickers = TICKER_CATEGORIES.get(category, [])
    if not tickers:
        return None

    # Use the AI picker to get a recommendation
    recommended_ticker = get_ai_recommendation(category, tickers, price_limit)

    # Fallback to the first ticker if AI fails to provide a recommendation
    return recommended_ticker if recommended_ticker else tickers[0]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/daily-pick/<category_key>')
def api_daily_pick(category_key):
    logging.info(f"Request for daily pick for category: {category_key}")
    if category_key not in TICKER_CATEGORIES:
        logging.error(f"Invalid category: {category_key}")
        return jsonify({'error': 'Invalid category'}), 404

    # Check if a pick for today already exists
    history = get_pick_history_for_category(category_key)
    logging.info(f"Initial history: {history}")
    today_str = datetime.now().strftime('%Y-%m-%d')
    todays_pick_ticker = None

    if history:
        logging.info("History is not empty, checking for today's pick.")
        latest_pick_date_str = history[0]['pick_date'].strftime('%Y-%m-%d')
        if latest_pick_date_str == today_str:
            todays_pick_ticker = history[0]['ticker']
            logging.info(f"Found today's pick in history: {todays_pick_ticker}")

    # If no pick exists for today, find a new one
    if not todays_pick_ticker:
        logging.info("No pick for today, finding a new one.")
        price_limit = 5 if category_key == 'penny_stock' else None
        todays_pick_ticker = find_stock_of_the_day(category_key, price_limit)
        logging.info(f"New pick found: {todays_pick_ticker}")
        if todays_pick_ticker:
            save_daily_pick(category_key, todays_pick_ticker)
            # Re-fetch history to include the newly saved pick
            history = get_pick_history_for_category(category_key)
            logging.info(f"History after saving new pick: {history}")

    latest_pick_to_display = history[0]['ticker'] if history else "N/A"
    logging.info(f"Final ticker to display: {latest_pick_to_display}")
    return jsonify({'ticker': latest_pick_to_display, 'history': history})

@app.route('/api/all-portfolios')
def all_portfolios_data():
    """
    This single, efficient endpoint fetches all data for all portfolios.
    """
    try:
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
            data = yf.download(list(all_tickers), period='1d', progress=False)
            if not data.empty and 'Close' in data and not data['Close'].empty:
                if len(all_tickers) == 1:
                    price_data[list(all_tickers)[0]] = data['Close'].iloc[-1]
                else:
                    price_data = data['Close'].iloc[-1].to_dict()

        # Step 3: Process each portfolio with the fetched prices
        response_data = {}
        for name in portfolio_names:
            summary = get_portfolio_summary(name)
            holdings = all_holdings[name]

            total_market_value = 0.0

            for holding in holdings:
                current_price = price_data.get(holding['ticker'])
                if current_price is None or pd.isna(current_price):
                    current_price = float(holding['purchase_price'])

                # Ensure all calculations result in standard float types
                holding['shares'] = float(holding['shares'])
                holding['purchase_price'] = float(holding['purchase_price'])
                holding['current_price'] = float(current_price)
                holding['cost_basis'] = holding['shares'] * holding['purchase_price']
                holding['current_value'] = holding['shares'] * holding['current_price']
                holding['gain_loss'] = holding['current_value'] - holding['cost_basis']
                total_market_value += holding['current_value']

            total_capital_invested = float(summary[1])
            total_gain_loss = total_market_value - sum(h['cost_basis'] for h in holdings)
            roi_percentage = (total_gain_loss / total_capital_invested) * 100 if total_capital_invested > 0 else 0

            response_data[name] = {
                'portfolio_name': name,
                'cash_balance': float(summary[0]),
                'total_invested': total_capital_invested,
                'current_market_value': total_market_value,
                'total_assets': float(summary[0]) + total_market_value,
                'total_gain_loss': total_gain_loss,
                'roi_percentage': roi_percentage,
                'holdings': holdings
            }

        print(f"--- Successfully prepared all portfolio data. ---")
        return jsonify(response_data)

    except Exception as e:
        import traceback
        print(f"--- CRITICAL ERROR in all_portfolios_data ---")
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception: {e}")
        traceback.print_exc()
        print(f"---------------------------------------------")
        return jsonify({'error': 'Failed to load portfolio data due to a server error.'}), 500

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
