import os
from datetime import datetime, timedelta
import yfinance as yf
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

# Import all necessary functions from our new database module
from database import (
    init_db,
    get_tickers_by_category,
    update_tickers_from_source,
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
# Fix for running behind a reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Categories ---
CATEGORIES = {
    'hot_stock': {'db_category': 'sp500', 'display_name': 'Hot Stocks'},
    'penny_stock': {'db_category': 'penny', 'display_name': '$5 or Less'},
    'monthly_dividend': {'db_category': 'monthly_dividend', 'display_name': 'Monthly Dividends'},
    'high_yield_dividend': {'db_category': 'high_yield', 'display_name': 'High-Yield Dividends'}
}

# --- Stock Finding Logic ---
def find_best_candidate_from_all():
    """
    Finds a stock with 3+ days of positive growth from a combined list of all
    stock categories ('sp500', 'penny').
    """
    # Combine tickers from all relevant stock and ETF categories
    all_tickers = get_tickers_by_category('sp500') + get_tickers_by_category('penny') + get_tickers_by_category('etf')
    unique_tickers = sorted(list(set(all_tickers))) # Sort for deterministic behavior

    # We need to avoid picking any stock that was recently picked for ANY category
    sp500_recent = get_recently_picked_tickers('sp500')
    penny_recent = get_recently_picked_tickers('penny')
    all_recent_picks = sp500_recent.union(penny_recent)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    for ticker in unique_tickers:
        if ticker in all_recent_picks:
            continue
        try:
            hist = yf.Ticker(ticker).history(start=start_date, end=end_date, auto_adjust=False)
            if hist.empty or len(hist) < 4:
                continue

            # Check for 3 consecutive days of growth
            if all(hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1] for i in range(1, 4)):
                 return ticker
        except Exception as e:
            print(f"Could not analyze ticker {ticker} for daily portfolio: {e}")

    # Fallback: if no stock meets the criteria, return the first one not picked recently
    for ticker in unique_tickers:
        if ticker not in all_recent_picks:
            return ticker

    return unique_tickers[0] if unique_tickers else None

def find_hot_stock(category):
    recent_picks = get_recently_picked_tickers(category)
    tickers = get_tickers_by_category(category)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    for ticker in tickers:
        if ticker in recent_picks:
            continue
        try:
            hist = yf.Ticker(ticker).history(start=start_date, end=end_date, auto_adjust=False)
            if hist.empty or len(hist) < 4:
                continue

            is_penny = category == 'penny'
            is_under_limit = hist['Close'].iloc[-1] <= 5.0
            is_hot = all(hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1] for i in range(1, 4))

            if is_hot and (not is_penny or (is_penny and is_under_limit)):
                 return ticker
        except Exception as e:
            print(f"Could not analyze ticker {ticker}: {e}")

    # Fallback: if no stock meets the criteria, return the first one not picked recently
    for ticker in tickers:
        if ticker not in recent_picks:
            return ticker

    return tickers[0] if tickers else None

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
        # 1. Check if a pick was already made today
        todays_pick = get_todays_pick_for_category(db_category)
        stock_ticker = todays_pick['ticker'] if todays_pick else None

        # 2. If no pick for today, find one
        if not stock_ticker:
            if 'dividend' in category_key:
                stock_ticker = find_dividend_stock(db_category)
            else:
                stock_ticker = find_hot_stock(db_category)

            # 3. If a new stock is found, save it to the DB
            if stock_ticker:
                save_daily_pick(db_category, stock_ticker)

        # 4. Fetch the full history for the response
        history = get_pick_history_for_category(db_category)
        message = stock_ticker if stock_ticker else 'No suitable stock found today.'

        return jsonify({'ticker': message, 'history': history})

    except Exception as e:
        print(f"Error in get_daily_pick_response for '{db_category}': {e}")
        # Log the full error for debugging
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
    """Provides a complete summary of a given portfolio."""
    summary = get_portfolio_summary(portfolio_name)
    holdings = get_portfolio_holdings(portfolio_name)

    # Calculate current value of holdings
    total_value = 0
    detailed_holdings = []
    for holding in holdings:
        try:
            current_price = yf.Ticker(holding['ticker']).info.get('regularMarketPrice')
            if not current_price: current_price = holding['purchase_price'] # fallback
            value = holding['shares'] * current_price
            total_value += value
            detailed_holdings.append({**holding, 'current_price': current_price, 'current_value': value})
        except Exception:
            total_value += holding['shares'] * holding['purchase_price'] # fallback on error
            detailed_holdings.append({**holding, 'current_price': holding['purchase_price'], 'current_value': holding['shares'] * holding['purchase_price']})

    return jsonify({
        'portfolio_name': portfolio_name,
        'cash_balance': summary[0],
        'total_invested': summary[1],
        'current_market_value': total_value,
        'total_assets': summary[0] + total_value,
        'holdings': detailed_holdings
    })

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00  # This could be a configurable value

    # --- New Logic for Daily Portfolio ---
    if portfolio_name == 'daily_investment':
        if not is_market_open():
            return jsonify({'status': 'success', 'message': 'Market is closed today. No investment made.'})

        # For the daily portfolio, we find the best candidate from all lists
        candidate_ticker = find_best_candidate_from_all()
        # The daily pick should be saved under its own category to avoid re-picking
        if candidate_ticker:
            save_daily_pick('daily_investment_pick', candidate_ticker)

    # --- Existing Logic for other portfolios ---
    elif portfolio_name == 'main':
        candidate_ticker = find_hot_stock('sp500')
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
        if not price or price <= 0:
            raise ValueError("Invalid price from yfinance")
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

def initial_populate_db():
    """Populates the DB with starter lists if they are empty."""
    print("Checking if initial data population is needed...")
    starter_lists = {
        'sp500': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA'],
        'penny': ['SNDL', 'CTRM', 'ZOM', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK'],
        'monthly_dividend': ['O', 'MAIN', 'GAIN', 'STAG', 'GOOD', 'PBA', 'SJR', 'AGNC'],
        'high_yield': ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']
    }
    for category, tickers in starter_lists.items():
        if not get_tickers_by_category(category):
            print(f"Adding starter list for '{category}'...")
            # Using replace_tickers to ensure a clean slate for hardcoded lists
            from database import replace_tickers_for_category
            replace_tickers_for_category(tickers, category)

if __name__ == '__main__':
    # The database should be initialized and populated via a separate script now.
    # See setup_database.py
    # This ensures the web server starts quickly and doesn't perform lengthy setup tasks.
    print("Starting Flask server...")
    app.run(debug=True, port=5001)
