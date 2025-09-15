# Deployment Guide for Stock App with Apache2 and MySQL
(All previous sections are unchanged)
...

## Step 8: Configure Apache2 and Start Services
(This section remains the same)
...

## Step 9: Configure Automation
Set up your `n8n` or `cron` jobs to call the application's API endpoints.

### 1. Data Enrichment (Daily)
-   **Trigger:** Daily (e.g., at 1 AM).
-   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-scraper`
-   **Purpose:** Adds new stocks/ETFs from Alpha Vantage to the database.

### 2. Sentiment Analysis (Hourly)
-   **Trigger:** Hourly.
-   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-sentiment-analysis`
-   **Purpose:** Updates sell flags on your current holdings based on news sentiment.

### 3. Performance Tracking (Daily)
-   **Trigger:** Daily (e.g., at 2 AM).
-   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-performance-tracker`
-   **Purpose:** Checks the 7, 30, and 90-day performance of past picks.

### 4. Portfolio Investments (Weekly/Daily)
-   **Trigger:** On your desired schedule (e.g., daily or weekly at 8 AM).
-   **Endpoints:**
    -   `POST` to `https://zapp.sytes.net/stock/api/trigger-investment/main`
    -   `POST` to `https://zapp.sytes.net/stock/api/trigger-investment/monthly_dividend`
    -   `POST` to `https://zapp.sytes.net/stock/api/trigger-investment/high_yield_investment`
    -   `POST` to `https://zapp.sytes.net/stock/api/trigger-investment/daily_investment`

**Note:** All automation endpoints are protected by the `SCRAPER_API_KEY` set in your `.env` file. You must include it as an `X-API-Key` header in your requests.
