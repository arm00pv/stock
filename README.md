# Stock Picker Web Application (Unified Beta)

This is a comprehensive Flask-based web application for stock discovery, portfolio tracking, and advanced market analysis. It unifies traditional screening methods with AI-powered insights.

> **For End Users:** Please check the [User Guide](USER_GUIDE.md) for step-by-step instructions on how to use the app.

## Core Features

### 1. Daily Picks & Screening
- **Hot Stocks**: Finds S&P 500 companies with 3+ days of positive growth.
- **Penny Stocks**: Screens for stocks under $5 with positive momentum.
- **Dividend Picks**: Daily selections for Monthly Dividend and High-Yield categories.
- **Efficient Caching**: Uses a custom LRU-style cache and `sp500_cache.json` to minimize external API calls.
- **Ticker Deduplication**: Implements rigorous unique filtering (SELECT DISTINCT) to prevent duplicate processing.

### 2. Portfolio Management
- **Automated Tracking**: Tracks "Main", "Monthly Dividend", "Daily Investment", and "High Yield" portfolios.
- **Real-time Valuation**: Uses `concurrent.futures.ThreadPoolExecutor` to fetch real-time prices for all holdings in parallel, ensuring fast page loads.
- **Sell Flags**: Integrates with `sentiment_analyzer.py` to flag holdings with negative news sentiment.

### 3. AI & Analytics Tools
- **AI Chat Assistant**: A regex-based AI assistant (`ai_assistant.py`) capable of answering questions about prices, risk, and analysis.
- **Stock Prediction**: `ai_prediction.py` uses a Random Forest Regressor (`scikit-learn`) to forecast 7-day price trends based on historical SMA, Volume, and Returns.
- **Smart Signals**: Calculates RSI and MACD indicators to provide Buy/Sell signals.
- **Market Anomalies**: Uses Isolation Forest to detect unusual volume or price movement patterns.
- **Sector Rotation**: Analyzes ETF momentum to identify trending market sectors.

## Architecture & Technology

- **Backend**: Flask (Python 3.12+)
- **Database**: MySQL (with connection pooling via `stock_pool`)
- **Data Sources**:
  - `yfinance` for market data.
  - `Marketaux` for sentiment analysis.
  - Alpha Vantage (optional/legacy) for ticker lists.
- **Concurrency**: Threading for API-bound tasks (pricing), Batch processing for DB-bound tasks (enrichment).
- **Frontend**: HTML/CSS with JavaScript for dynamic tabs, chat widgets, and Chart.js visualizations.

## Setup & Installation

### 1. Prerequisites
- Python 3.8+
- MySQL Server

### 2. Installation
```bash
git clone <repository-url>
cd stock-picker
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=stock_db
SECRET_KEY=your_flask_secret
SCRAPER_API_KEY=your_api_key
MARKETAUX_API_KEY=your_marketaux_key
SESSION_COOKIE_NAME=stock_session
SESSION_COOKIE_PATH=/
```

### 4. Database Initialization
Run the setup script to create tables (`stocks`, `portfolio_summary`, `daily_picks_history`, etc.):
```bash
python setup_database.py
```

### 5. Running the Application
```bash
python app.py
```
Access at `http://127.0.0.1:5000`.

### 6. Deployment (DigitalOcean)
The application includes a `Procfile` for easy deployment on DigitalOcean App Platform.
1. Connect your repo to DigitalOcean.
2. Add a **MySQL** database component.
3. Configure Environment Variables (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, etc.).
4. The app will launch using `gunicorn`.

## Automated Background Tasks

- **Enrichment**: `python enricher.py` (Batched updates for market cap/sector).
- **Sentiment**: `python sentiment_analyzer.py` (News analysis).
- **Performance**: `python performance_tracker.py` (Track pick success rates).

## Testing
Run the comprehensive test suite to verify functionality and UI:
```bash
python test_consolidation.py
python test_endpoints.py
python test_new_features.py
python verify_tickers.py
python verify_ui_enhancements.py
```
