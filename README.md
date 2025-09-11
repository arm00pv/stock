# Stock Picker Web Application

This web application helps users discover interesting stocks based on several criteria. It presents a daily "pick" for different categories in a simple, easy-to-use tabbed interface.

## Features

- **Hot Stocks**: Finds stocks from a list of S&P 500 companies that have shown positive growth for 3 or more consecutive days.
- **Penny Stocks**: Finds stocks priced at $2 or less that meet the same 3-day growth criteria.
- **Monthly Dividend Stocks**: Shows a daily pick from a list of stocks and ETFs known to pay monthly dividends.
- **High Yield Dividends**: Shows a daily pick from a list of stocks and ETFs known for their high dividend yields.

## Running the Web Application

### 1. Installation

First, clone the repository and navigate into the project directory. Then, install the required Python packages using pip:

```bash
pip install -r requirements.txt
```

### 2. Running the App

To start the Flask development server, run the following command:

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5001`.

### 3. Deployment

For instructions on how to deploy this application to a production server using Gunicorn and Apache2, please see the `DEPLOY.md` file.

---

## Data Scraper (`scraper.py`)

This project includes a standalone script, `scraper.py`, designed to build lists of stocks for different categories by scraping financial websites.

### Data Management

The application's stock lists are managed via an SQLite database (`stocks.db`). This database is the central source of truth for the ticker lists used in each category.

The database is populated in two ways:
1.  **Initial Seeding**: When `app.py` is run for the first time, it will create the database and seed it with starter lists for the "Hot Stocks", "Penny Stocks", and "High Yield Dividends" categories.
2.  **Web Scraping**: The `scraper.py` script is designed to dynamically update the database with fresh ticker lists from online sources.

### Running the Scraper

The scraper script (`scraper.py`) is designed to run periodically (e.g., via a daily cron job) to keep the database updated.

It currently scrapes the following categories from different sources:
-   **Monthly Dividend Stocks**: from `simplysafedividends.com`
-   **High Yield Dividends**: from `kiplinger.com`

When you run the script, it will:
1.  Fetch the latest tickers from these sources.
2.  Add any new tickers to the database.
3.  Update the `last_seen_date` for tickers that are still present on the lists.
4.  After processing all sources, it will automatically **prune** any tickers that have not been seen on a list for a long time (default is 90 days), keeping the database clean and relevant.

To run the scraper manually:
```bash
python scraper.py
```
For instructions on how to automate this script, see the `DEPLOY.md` file.

---

## Manual Ticker Updates (`update_tickers.py`)

For categories where a reliable scraper is not available (e.g., 'High Yield', 'Penny Stocks'), you can use the `update_tickers.py` script to manually replace the list for a category.

### How to Use

1.  **Run the script** from your terminal:
    ```bash
    python update_tickers.py
    ```

2.  **Choose a category**: The script will display a list of available categories to update. Enter the number corresponding to your choice.

3.  **Paste the new tickers**: The script will prompt you to paste a new, comma-separated list of tickers.

4.  **Confirm**: Review the parsed list and confirm the action. The script will then delete the old list for that category and insert the new one.

**Note**: Web scraping can be fragile and may break if the source website changes its layout. This script is intended as a starting point for building a more robust data collection system.
