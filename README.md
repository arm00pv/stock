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

### Purpose

The main application relies on curated lists of tickers for categories like "Monthly Dividends". The scraper is a proof-of-concept tool to automate the creation of these lists. The current version is designed to extract a list of monthly dividend stocks from an article on `simplysafedividends.com`.

### Running the Scraper

1.  **Install Dependencies**: The scraper requires `requests` and `beautifulsoup4`, which are included in the main `requirements.txt` file. Make sure you have run `pip install -r requirements.txt`.

2.  **Run the Script**: Execute the script from your terminal:
    ```bash
    python scraper.py
    ```

3.  **Output**: The script will print a Python list of the scraped ticker symbols to your console. This list can then be copied and used to update the ticker lists in `app.py` (e.g., the `get_monthly_dividend_tickers` function).

**Note**: Web scraping can be fragile and may break if the source website changes its layout. This script is intended as a starting point for building a more robust data collection system.
