import os
from datetime import datetime
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from database import (
    init_db, get_all_portfolios_data,
    save_daily_pick, get_pick_history_for_category, get_recently_picked_tickers,
    execute_investment, get_ai_settings, save_ai_settings, execute_sale, get_db_connection
)
from ai_picker import get_ai_recommendation
from backtesting import run_backtest
from decimal import Decimal
from ai_trader import manage_ai_portfolio
from cache import yf_download_cached
from models import User
from screener import screen_stocks

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

from constants import TICKER_CATEGORIES

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
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
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (form.username.data, hashed_password))
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
            user = User(id=user_data['id'], username=user_data['username'], password=user_data['password'])
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

@app.route('/api/run-ai-trader', methods=['POST'])
def api_run_ai_trader():
    try:
        manage_ai_portfolio()
        return jsonify({'status': 'success', 'message': 'AI portfolio management cycle complete.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

@app.route('/api/screener', methods=['POST'])
def api_screener():
    criteria = request.get_json()
    results = screen_stocks(criteria)
    return jsonify(results)

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