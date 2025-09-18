import os
import yfinance as yf
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

@app.route('/api/portfolio/<portfolio_name>')
def portfolio_data(portfolio_name):
    summary = get_portfolio_summary(portfolio_name)
    holdings = get_portfolio_holdings(portfolio_name)

    total_market_value = 0.0
    total_cost_basis = 0.0

    tickers_for_batch_fetch = [h['ticker'] for h in holdings]
    price_data = {}
    if tickers_for_batch_fetch:
        try:
            data = yf.download(tickers_for_batch_fetch, period='1d', progress=False)
            if not data.empty:
                price_data = data['Close'].iloc[-1].to_dict()
        except Exception as e:
            print(f"Warning: yfinance batch download failed: {e}")

    for holding in holdings:
        cost_basis = float(holding['shares']) * float(holding['purchase_price'])
        total_cost_basis += cost_basis

        current_price = price_data.get(holding['ticker'])
        if current_price is None:
            current_price = float(holding['purchase_price']) # Fallback

        current_value = float(holding['shares']) * current_price
        total_market_value += current_value

        holding['current_price'] = current_price
        holding['current_value'] = current_value
        holding['cost_basis'] = cost_basis
        holding['gain_loss'] = current_value - cost_basis

    total_gain_loss = total_market_value - total_cost_basis
    total_capital_invested = summary[1]

    roi_percentage = (total_gain_loss / total_capital_invested) * 100 if total_capital_invested > 0 else 0

    return jsonify({
        'portfolio_name': portfolio_name,
        'cash_balance': summary[0],
        'total_invested': total_capital_invested,
        'current_market_value': total_market_value,
        'total_assets': summary[0] + total_market_value,
        'total_gain_loss': total_gain_loss,
        'roi_percentage': roi_percentage,
        'holdings': holdings
    })

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
