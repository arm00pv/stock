import os
from datetime import datetime
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, Response
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from database import (
    init_db, get_portfolio_summary, get_portfolio_holdings,
    save_daily_pick, get_pick_history_for_category, get_recently_picked_tickers,
    execute_investment, get_ai_settings, save_ai_settings, get_db_connection, execute_sale,
    get_ai_performance_data, search_stocks_db, get_new_listings,
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    get_all_transactions, get_total_portfolio_value
)
from ai_picker import get_ai_recommendation, get_stock_analysis, get_latest_news
from ai_prediction import get_sp500_predictions
from market_data import get_market_status
from backtesting import run_backtest
from ai_assistant import process_chat_message
from personal_portfolio import create_portfolio, get_portfolio_status, execute_user_trade, get_leaderboard
from decimal import Decimal
from models import User
from screener import screen_stocks
from ai_trader import manage_ai_portfolio, audit_portfolio

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_secret_key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Initialize the database
init_db()

# Using hardcoded lists for stability during the reset
TICKER_CATEGORIES = {
    'hot_stock': ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'JNJ', 'V'],
    'penny_stock': ['SNDL', 'CTRM', 'ZOM', 'AMC', 'BB', 'EXPR', 'GSAT', 'NAKD', 'TXMD', 'GNUS'],
    'monthly_dividend': ['O', 'MAIN', 'STAG', 'GAIN', 'GOOD', 'PBA', 'SBR', 'ADC', 'EPR', 'LTC'],
    'high_yield': ['AGNC', 'ORC', 'PSEC', 'ARR', 'MFA', 'IVR', 'TWO', 'EARN', 'OXLC', 'HRZN'],
    'crypto': ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD', 'XRP-USD', 'DOT-USD', 'LTC-USD', 'LINK-USD', 'BCH-USD']
}

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        conn = get_db_connection()
        if not conn:
            raise ValidationError('Database connection failed. Please try again later.')
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username.data,))
            user = cursor.fetchone()
            if user:
                raise ValidationError('That username is taken. Please choose a different one.')
        conn.close()

    def validate_email(self, email):
        conn = get_db_connection()
        if not conn: return
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email.data,))
            user = cursor.fetchone()
            if user:
                raise ValidationError('That email is already registered.')
        conn.close()

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed. Please try again later.', 'danger')
            return render_template('register.html', title='Register', form=form)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (form.username.data, form.email.data, hashed_password))
        conn.commit()
        conn.close()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed. Please try again later.', 'danger')
            return render_template('login.html', title='Login', form=form)
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (form.username.data,))
            user_data = cursor.fetchone()
        conn.close()
        if user_data and bcrypt.check_password_hash(user_data['password'], form.password.data):
            user = User(
                id=user_data['id'],
                username=user_data['username'],
                password=user_data['password'],
                email=user_data.get('email'),
                beta_active=bool(user_data.get('beta_active'))
            )
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
@login_required
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
        portfolio_names = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment', 'crypto_portfolio']
        all_holdings = {}
        all_tickers = set()

        for name in portfolio_names:
            holdings = get_portfolio_holdings(name)
            all_holdings[name] = holdings
            for holding in holdings:
                all_tickers.add(holding['ticker'])

        price_data = {}
        if all_tickers:
            data = yf.download(list(all_tickers), period='1d', progress=False)
            if not data.empty and 'Close' in data and not data['Close'].empty:
                # Handle both Series (single ticker) and DataFrame (multiple tickers)
                close_data = data['Close']
                if len(all_tickers) > 1:
                    price_data = close_data.iloc[-1].to_dict()
                else:
                    ticker = list(all_tickers)[0]
                    price_data = {ticker: close_data.iloc[-1]}

        response_data = {}
        for name in portfolio_names:
            summary = get_portfolio_summary(name)
            holdings = all_holdings[name]
            total_market_value = 0.0

            for holding in holdings:
                current_price = price_data.get(holding['ticker'], float(holding['purchase_price']))
                holding.update({
                    'shares': float(holding['shares']),
                    'purchase_price': float(holding['purchase_price']),
                    'current_price': float(current_price),
                    'cost_basis': float(holding['shares']) * float(holding['purchase_price']),
                    'current_value': float(holding['shares']) * float(current_price),
                    'gain_loss': (float(holding['shares']) * float(current_price)) - (float(holding['shares']) * float(holding['purchase_price']))
                })
                total_market_value += holding['current_value']

            total_capital_invested = float(summary[1])
            roi_percentage = ((total_market_value - total_capital_invested) / total_capital_invested) * 100 if total_capital_invested > 0 else 0

            response_data[name] = {
                'portfolio_name': name,
                'cash_balance': float(summary[0]),
                'total_invested': total_capital_invested,
                'current_market_value': total_market_value,
                'total_assets': float(summary[0]) + total_market_value,
                'total_gain_loss': total_market_value - total_capital_invested,
                'roi_percentage': roi_percentage,
                'holdings': holdings
            }
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': 'Failed to load portfolio data due to a server error.'}), 500

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00
    category_map = {
        'main': 'hot_stock',
        'monthly_dividend': 'monthly_dividend',
        'high_yield_investment': 'high_yield',
        'daily_investment': 'hot_stock',
        'crypto_portfolio': 'crypto'
    }
    category = category_map.get(portfolio_name)

    if not category:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name'}), 404

    price_limit = 5 if category == 'penny_stock' else None
    ticker = get_ai_recommendation(category, TICKER_CATEGORIES.get(category, []), price_limit)

    if not ticker:
        return jsonify({'status': 'error', 'message': 'No suitable stock found.'})

    try:
        price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
        if not price or price <= 0: raise ValueError("Invalid price")
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
    strategy = data.get('strategy', 'ai_score') # Default to AI Score

    if not all([start_date, end_date, category]):
        return jsonify({'error': 'Missing required parameters'}), 400

    tickers = TICKER_CATEGORIES.get(category)
    if not tickers:
        return jsonify({'error': 'Invalid category'}), 400

    results = run_backtest(start_date, end_date, initial_capital, investment_amount, category, tickers, 50, 200, strategy)
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
@login_required
def api_sell_stock():
    data = request.get_json()
    portfolio_name = data.get('portfolio_name')
    ticker = data.get('ticker')
    shares_to_sell = data.get('shares')

    if not all([portfolio_name, ticker, shares_to_sell]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    try:
        price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
        if not price or price <= 0: raise ValueError("Invalid price")

        success, message = execute_sale(portfolio_name, ticker, float(shares_to_sell), price)
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to sell {ticker}: {e}'}), 500

@app.route('/api/screener', methods=['POST'])
@login_required
def api_screener():
    criteria = request.get_json()
    results = screen_stocks(criteria)
    return jsonify(results)

@app.route('/api/ai-performance')
@login_required
def api_ai_performance():
    performance_data = get_ai_performance_data('ai_guided_portfolio')
    return jsonify(performance_data)

@app.route('/api/run-ai-trader', methods=['POST'])
@login_required
def run_ai_trader():
    manage_ai_portfolio()
    return jsonify({"status": "success"})

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

@app.route('/api/search')
def api_search_stocks():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    results = search_stocks_db(query)
    return jsonify(results)

@app.route('/api/new-listings')
def api_new_listings():
    days = request.args.get('days', 30)
    listings = get_new_listings(int(days))
    return jsonify(listings)

@app.route('/api/ai-analysis/<ticker>')
@login_required
def api_ai_analysis(ticker):
    analysis = get_stock_analysis(ticker)
    if not analysis:
        return jsonify({'error': 'Could not generate analysis'}), 404
    return jsonify(analysis)

@app.route('/api/audit-portfolio/<portfolio_name>')
@login_required
def api_audit_portfolio(portfolio_name):
    report = audit_portfolio(portfolio_name)
    return jsonify(report)

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_watchlist():
    if request.method == 'GET':
        watchlist = get_watchlist(current_user.id)
        # Enhance with current price
        if watchlist:
            tickers = [item['ticker'] for item in watchlist]
            try:
                # Only download if tickers list is not empty
                # yf.download returns DataFrame or Series depending on input
                data = yf.download(tickers, period='1d', progress=False)
                close_data = data['Close']
                prices = {}
                if not close_data.empty:
                    if len(tickers) > 1:
                        prices = close_data.iloc[-1].to_dict()
                    else:
                        prices = {tickers[0]: close_data.iloc[-1]}

                for item in watchlist:
                    item['current_price'] = prices.get(item['ticker'], 0)
                    # convert timestamps to string
                    item['date_added'] = item['date_added'].strftime('%Y-%m-%d')
            except Exception as e:
                print(f"Error fetching watchlist prices: {e}")

        return jsonify(watchlist)

    data = request.get_json()
    ticker = data.get('ticker')
    if not ticker:
        return jsonify({'error': 'Ticker is required'}), 400

    if request.method == 'POST':
        success = add_to_watchlist(current_user.id, ticker)
        return jsonify({'status': 'success' if success else 'error'})

    elif request.method == 'DELETE':
        success = remove_from_watchlist(current_user.id, ticker)
        return jsonify({'status': 'success' if success else 'error'})

@app.route('/api/news/<ticker>')
@login_required
def api_stock_news(ticker):
    news = get_latest_news(ticker)
    return jsonify(news)

@app.route('/api/beta/activate', methods=['POST'])
@login_required
def api_activate_beta():
    data = request.get_json()
    email = data.get('email')

    if not current_user.email and not email:
        return jsonify({'error': 'Email is required to activate Beta features.'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'error': 'Database error'}), 500

    try:
        with conn.cursor() as cursor:
            # Update email if provided and different
            if email and email != current_user.email:
                cursor.execute("UPDATE users SET email = %s WHERE id = %s", (email, current_user.id))

            cursor.execute("UPDATE users SET beta_active = TRUE WHERE id = %s", (current_user.id,))
            conn.commit()

            # Update current session user object
            current_user.beta_active = True
            if email: current_user.email = email

            return jsonify({'status': 'success', 'message': 'Beta features activated!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/beta/sp500-predictions')
@login_required
def api_sp500_predictions():
    if not current_user.beta_active:
        return jsonify({'error': 'Beta features not active.'}), 403

    predictions = get_sp500_predictions()
    return jsonify(predictions)

@app.route('/api/market-status')
def api_market_status():
    # Cache could be added here
    return jsonify(get_market_status())

@app.route('/api/transactions')
@login_required
def api_transactions():
    transactions = get_all_transactions()
    # Convert date objects to string
    for t in transactions:
        t['purchase_date'] = t['purchase_date'].strftime('%Y-%m-%d')
        # Clean decimal
        t['shares'] = float(t['shares'])
        t['purchase_price'] = float(t['purchase_price'])
    return jsonify(transactions)

@app.route('/api/allocation')
@login_required
def api_allocation():
    data = get_total_portfolio_value()
    # Process for chart: just return list of {name, value}
    result = []
    for row in data:
        # Use total_invested + cash_balance as total assets
        result.append({
            'portfolio': row['portfolio_name'],
            'value': float(row['total_invested']) + float(row['cash_balance'])
        })
    return jsonify(result)

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({'response': "Please say something."})

    response = process_chat_message(current_user.id, message)
    return jsonify({'response': response})

@app.route('/api/export-history')
@login_required
def api_export_history():
    transactions = get_all_transactions()
    if not transactions:
        return Response("No transactions to export", status=204)

    # Convert to DataFrame
    df = pd.DataFrame(transactions)
    # Format data
    df['shares'] = df['shares'].astype(float)
    df['purchase_price'] = df['purchase_price'].astype(float)

    csv_data = df.to_csv(index=False)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=transactions.csv"}
    )

@app.route('/api/personal/portfolio', methods=['GET', 'POST'])
@login_required
def api_personal_portfolio():
    if request.method == 'POST':
        success, message = create_portfolio(current_user.id)
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400

    status = get_portfolio_status(current_user.id)
    if not status:
        # Not created yet
        return jsonify({'status': 'not_found'})
    return jsonify(status)

@app.route('/api/personal/trade', methods=['POST'])
@login_required
def api_personal_trade():
    data = request.get_json()
    ticker = data.get('ticker')
    action = data.get('action') # BUY or SELL
    amount = data.get('amount') # $ for BUY, Shares for SELL

    if not all([ticker, action, amount]):
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400

    success, message = execute_user_trade(current_user.id, ticker, action, amount)
    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message}), 400

@app.route('/api/leaderboard')
@login_required
def api_leaderboard():
    data = get_leaderboard()
    # Convert dates
    for row in data:
        row['start_date'] = row['start_date'].strftime('%Y-%m-%d')
        row['total_equity'] = float(row['total_equity'])
        row['cash_balance'] = float(row.get('cash_balance', 0)) # Might not be selected if I removed it from query, let's check personal_portfolio.py
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=False, port=5000)