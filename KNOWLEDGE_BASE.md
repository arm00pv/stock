# Knowledge Base & Developer Guide

This document encapsulates the architectural decisions, coding patterns, and "tribal knowledge" required to maintain and extend the Stock Picker application.

## 1. Architecture Overview

### Backend (Flask + MySQL)
- **State Management**: The app is stateless. Session data is stored in client-side cookies (signed), but all business data resides in MySQL.
- **Connection Pooling**: `database.py` uses `mysql.connector.connect(pool_name="stock_pool", pool_size=5)`. This is critical for performance under WSGI.
  - *Rule*: Always use `get_db_connection()` and ensure `cursor.close()` and `conn.close()` are called in a `finally` block to return connections to the pool.
- **Concurrency**: `app.py` uses `concurrent.futures.ThreadPoolExecutor` for the `/api/portfolio` endpoint.
  - *Reasoning*: `yfinance` calls are synchronous and network-bound. Threading allows parallel fetching of prices for multiple holdings, reducing request latency from O(n) to O(1) roughly.
  - *Safety*: Threads **only** fetch data. Database writes are kept on the main thread or in separate batch processes to avoid race conditions.

### Frontend (HTML + Playwright)
- **Visuals**: Uses `Chart.js` for graphs and `CSS` for tabs.
- **Verification**: We use Playwright (`verify_frontend.py`) for regression testing.
  - *Pattern*: Verification scripts live outside the app (e.g., `/home/jules/verification/`) and take screenshots to confirm UI elements (like the Beta tab) render correctly.

## 2. Key Modules & Patterns

### Beta Features (`beta_features.py`)
- **Isolation**: New experimental features are encapsulated here to avoid bloating `app.py`.
- **AI Prediction**: Uses `RandomForestRegressor`.
  - *Constraint*: Currently trains on-the-fly. For high scale, this should be moved to a background job that saves models/predictions to the DB.
- **Error Handling**: Uses `try-except Exception` blocks to prevent beta features from crashing the main app.

### Enrichment Pipeline (`enricher.py`)
- **Batch Processing**: Uses `update_stock_details_batch` with `executemany` to avoid N+1 query performance killing.
- **Caching**: S&P 500 list is cached in `sp500_cache.json` (24h TTL) to respect Wikipedia/Source limits.

### Testing Strategy
- **Unit Tests**: `test_consolidation.py` and `test_endpoints.py`.
- **Mocking**: Because the dev environment lacks a live MySQL server, we aggressively mock `mysql.connector` and `yfinance` in `sys.modules` **before** importing app modules.
  - *Pattern*:
    ```python
    sys.modules['mysql'] = MagicMock()
    # ... then import app
    ```
- **Duplicate Prevention**:
  - *Database*: Always use `SELECT DISTINCT ticker` when fetching lists to process.
  - *Logic*: Use Python `set()` operations when merging ticker lists from multiple sources.

## 3. Common Pitfalls & Solutions

- **"ModuleNotFoundError: dotenv"**: Ensure `python-dotenv` is installed. It's used in almost every file.
- **Database Connection Errors**:
  - *Cause*: `executemany` with inconsistent tuple sizes.
  - *Fix*: Ensure all tuples in the list have the exact same number of elements matching the SQL placeholders.
- **FutureWarning in Pandas**:
  - *Cause*: `pd.read_html(response.text)`
  - *Fix*: Use `pd.read_html(io.StringIO(response.text))`

## 4. Automation & Deployment
- **Cron Jobs**: Essential for `scraper.py`, `enricher.py`, and `sentiment_analyzer.py`.
- **WSGI**: The entry point is `wsgi.py`, which simply imports `app` as `application`.
- **Proxy Headers**: `app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)` is configured for reverse proxy setups (e.g., behind Nginx/Apache).

## 5. Future Improvements
- **Async DB**: Move to `aiomysql` or `SQLAlchemy` async for better concurrency.
- **Model Persistence**: Save the trained Random Forest models to disk/DB.
- **Frontend Framework**: Migrate vanilla JS/HTML to React or Vue for more complex Beta dashboards.
