import os
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

# Import all necessary functions from our new database module
from database import (
    init_db,
    get_tickers_by_category,
    get_portfolio_summary,
    get_portfolio_holdings,
    execute_investment,
    save_daily_pick,
    get_pick_history_for_category,
    get_todays_pick_for_category,
    get_recently_picked_tickers
)
from scraper import run_scraper_pipeline
from utils import is_market_open

app = Flask(__name__)

# --- Configuration ---
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Constants ---
MIN_AVG_VOLUME = 100000
SMA_SHORT = 50
SMA_LONG = 200

# --- Categories ---
CATEGORIES = {
    'hot_stock': {'db_category': 'sp500', 'display_name': 'Hot Stocks'},
    'penny_stock': {'db_category': 'penny', 'display_name': '$5 or Less', 'price_limit': 5},
    'monthly_dividend': {'db_category': 'monthly_dividend', 'display_name': 'Monthly Dividends'},
    'high_yield_dividend': {'db_category': 'high_yield', 'display_name': 'High-Yield Dividends'}
}

# --- New, Smarter Stock Finding Logic ---

def find_growth_candidate(categories_to_search, price_limit=None):
    """
    Finds a growth candidate based on Golden Cross and Volume strategies.
    - categories_to_search: A list of db_categories to search through.
    - price_limit: An optional maximum price for the stock.
    """
    print(f"Searching for growth candidate in categories: {categories_to_search}, price_limit: {price_limit}")

    # 1. Get all tickers to analyze
    all_tickers = []
    for category in categories_to_search:
        all_tickers.extend(get_tickers_by_category(category))
    unique_tickers = sorted(list(set(all_tickers)))

    # 2. Get all recently picked tickers from ALL history to avoid re-picking anything
    recent_picks = set()
    all_history_categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'daily_investment_pick']
    for category in all_history_categories:
        recent_picks.update(get_recently_picked_tickers(category))

    print(f"Found {len(unique_tickers)} unique tickers to analyze. Skipping {len(recent_picks)} recent picks.")

    # 3. Analyze each ticker
    for ticker in unique_tickers:
        if ticker in recent_picks:
            continue

        try:
            stock_info = yf.Ticker(ticker).info

            # Volume Filter
            avg_volume = stock_info.get('averageDailyVolume10Day', 0)
            if avg_volume is None or avg_volume < MIN_AVG_VOLUME:
                continue

            # Price Limit Filter
            if price_limit:
                current_price = stock_info.get('regularMarketPrice')
                if current_price is None or current_price > price_limit:
                    continue

            # Golden Cross Logic
            hist = yf.Ticker(ticker).history(period=f"{SMA_LONG + 2}d") # Get a bit of extra data
            if len(hist) < SMA_LONG + 1:
                continue

            hist['SMA50'] = hist['Close'].rolling(window=SMA_SHORT).mean()
            hist['SMA200'] = hist['Close'].rolling(window=SMA_LONG).mean()

            sma50_today = hist['SMA50'].iloc[-1]
            sma200_today = hist['SMA200'].iloc[-1]
            sma50_yesterday = hist['SMA50'].iloc[-2]
            sma200_yesterday = hist['SMA200'].iloc[-2]

            if pd.notna(sma50_today) and pd.notna(sma200_today) and pd.notna(sma50_yesterday) and pd.notna(sma200_yesterday):
                if sma50_yesterday < sma200_yesterday and sma50_today > sma200_today:
                    print(f"FOUND GOLDEN CROSS CANDIDATE: {ticker}")
                    return ticker
        except Exception:
            pass

    # 4. Fallback logic
    print("No Golden Cross candidate found. Falling back to first available ticker.")
    for ticker in unique_tickers:
        if ticker not in recent_picks:
            return ticker

    return unique_tickers[0] if unique_tickers else None

# --- Simplified "Finder" Functions ---

def find_hot_stock(category_key):
    details = CATEGORIES.get(category_key, {})
    db_category = details.get('db_category')
    price_limit = details.get('price_limit')
    return find_growth_candidate(categories_to_search=[db_category], price_limit=price_limit)

def find_best_candidate_from_all():
    return find_growth_candidate(categories_to_search=['sp500', 'penny', 'etf', 'generic_stock'])

def find_dividend_stock(category):
    recent_picks = get_recently_picked_tickers(category)
    tickers = get_tickers_by_category(category)
    for ticker in tickers:
        if ticker not in recent_picks:
            return ticker
    return tickers[0] if tickers else None

# --- Generic Endpoint Logic ---
def get_daily_pick_response(category_key):
    db_category = CATEGORIES[category_key]['db_category']

    try:
        todays_pick = get_todays_pick_for_category(db_category)
        stock_ticker = todays_pick['ticker'] if todays_pick else None

        if not stock_ticker:
            if 'dividend' in category_key:
                stock_ticker = find_dividend_stock(db_category)
            else:
                stock_ticker = find_hot_stock(category_key)

            if stock_ticker:
                save_daily_pick(db_category, stock_ticker)

        history = get_pick_history_for_category(db_category)
        message = stock_ticker if stock_ticker else 'No suitable stock found today.'

        return jsonify({'ticker': message, 'history': history})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ticker': 'Error loading data.', 'history': []}), 500

# --- API Endpoints ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hot-stock')
def api_hot_stock():
    return get_daily_pick_response('hot_stock')

@app.route('/api/penny-stock')
def api_penny_stock():
    return get_daily_pick_response('penny_stock')

@app.route('/api/monthly-dividend')
def api_monthly_dividend_stock():
    return get_daily_pick_response('monthly_dividend')

@app.route('/api/high-yield-dividend')
def api_high_yield_dividend_stock():
    return get_daily_pick_response('high_yield_dividend')

@app.route('/api/portfolio/<portfolio_name>')
def portfolio_data(portfolio_name):
    summary = get_portfolio_summary(portfolio_name)
    holdings = get_portfolio_holdings(portfolio_name)
    total_value = 0
    detailed_holdings = []
    for holding in holdings:
        try:
            current_price = yf.Ticker(holding['ticker']).info.get('regularMarketPrice')
            if not current_price: current_price = holding['purchase_price']
            value = holding['shares'] * current_price
            total_value += value
            detailed_holdings.append({**holding, 'current_price': current_price, 'current_value': value})
        except Exception:
            total_value += holding['shares'] * holding['purchase_price']
            detailed_holdings.append({**holding, 'current_price': holding['purchase_price'], 'current_value': holding['shares'] * holding['purchase_price']})
    return jsonify({
        'portfolio_name': portfolio_name, 'cash_balance': summary[0], 'total_invested': summary[1],
        'current_market_value': total_value, 'total_assets': summary[0] + total_value, 'holdings': detailed_holdings
    })

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00
    candidate_ticker = None

    if portfolio_name == 'daily_investment':
        if not is_market_open():
            return jsonify({'status': 'success', 'message': 'Market is closed today. No investment made.'})
        candidate_ticker = find_best_candidate_from_all()
        if candidate_ticker:
            save_daily_pick('daily_investment_pick', candidate_ticker)

    elif portfolio_name == 'main':
        candidate_ticker = find_hot_stock('hot_stock')
    elif portfolio_name == 'monthly_dividend':
        candidate_ticker = find_dividend_stock('monthly_dividend')
    elif portfolio_name == 'high_yield_investment':
        candidate_ticker = find_dividend_stock('high_yield')
    else:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name.'}), 404

    if not candidate_ticker:
        return jsonify({'status': 'error', 'message': f'No suitable stock found for {portfolio_name} portfolio investment.'})

    try:
        price = yf.Ticker(candidate_ticker).info.get('regularMarketPrice')
        if not price or price <= 0: raise ValueError("Invalid price from yfinance")
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Could not fetch price for {candidate_ticker}: {e}"})

    shares_to_buy = investment_amount / price
    execute_investment(portfolio_name, candidate_ticker, shares_to_buy, price, investment_amount)
    return jsonify({'status': 'success', 'message': f"Successfully invested ${investment_amount:.2f} in {candidate_ticker} for '{portfolio_name}' portfolio."})

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper_api():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY:
        abort(401, "Unauthorized: Invalid or missing API key.")
    try:
        run_scraper_pipeline()
        return jsonify({'status': 'success', 'message': 'Scraper pipeline executed successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500
