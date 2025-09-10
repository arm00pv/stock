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

The scraper script (`scraper.py`) currently supports fetching tickers for the **Monthly Dividend Stocks** category.

1.  **Install Dependencies**: Ensure you have installed the required packages:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the Script**: Execute the script from your terminal to update the database:
    ```bash
    python scraper.py
    ```
    This will find and save the latest monthly dividend tickers to the `stocks.db` file. You can run this periodically to keep the list fresh.

**Note**: Web scraping can be fragile and may break if the source website changes its layout. This script is intended as a starting point for building a more robust data collection system.
