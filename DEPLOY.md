# Deployment Guide for Stock App with Apache2 and MySQL
(All previous sections are unchanged)
...

## Step 9: Configure Automation
Set up your `n8n` or `cron` jobs to call the application's API endpoints.

### Recommended Automation Schedule

1.  **Populate Security List (Daily):**
    *   **Trigger:** Daily (e.g., at 1 AM).
    *   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-scraper`
    *   **Purpose:** Adds new stocks, ETFs, and bonds from Alpha Vantage to your database.

2.  **Enrich Security Data (Daily):**
    *   **Trigger:** Daily (e.g., at 2 AM, after the population step).
    *   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-enrichment`
    *   **Purpose:** Updates all securities in your database with their latest Market Cap, Sector, and S&P 500 status.

3.  **Sentiment Analysis (Hourly):**
    *   **Trigger:** Hourly.
    *   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-sentiment-analysis`
    *   **Purpose:** Updates sell flags on your current portfolio holdings based on news sentiment.

4.  **Performance Tracking (Daily):**
    *   **Trigger:** Daily (e.g., at 3 AM).
    *   **Endpoint:** `POST` to `https://zapp.sytes.net/stock/api/run-performance-tracker`
    *   **Purpose:** Checks the 7, 30, and 90-day performance of past picks.

5.  **Portfolio Investments (Weekly/Daily):**
    *   **Trigger:** On your desired schedule (e.g., daily or weekly at 8 AM).
    *   **Endpoints:** Call the specific `/api/trigger-investment/<portfolio_name>` endpoint for each portfolio you want to automate.

**Note:** All automation endpoints are protected by the `SCRAPER_API_KEY` set in your `.env` file. You must include it as an `X-API-Key` header in your requests.
