# This script should be run once to set up the database for the first time.
from database import init_db, get_tickers_by_category
# This import is needed for the initial population logic
from database import replace_tickers_for_category

def initial_populate_db():
    """Populates the DB with starter lists if they are empty."""
    print("Checking if initial data population is needed...")
    starter_lists = {
        'sp500': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'JPM', 'JNJ', 'V', 'PG', 'NVDA'],
        'penny': ['SNDL', 'CTRM', 'ZOM', 'GNUS', 'RIG', 'AMC', 'BB', 'NOK'],
        'monthly_dividend': ['O', 'MAIN', 'GAIN', 'STAG', 'GOOD', 'PBA', 'SJR', 'AGNC'],
        'high_yield': ['MO', 'T', 'VZ', 'IBM', 'XOM', 'CVX', 'KO', 'PEP', 'MCD', 'WMT']
    }
    for category, tickers in starter_lists.items():
        # Check if the category is already populated
        if not get_tickers_by_category(category):
            print(f"Adding starter list for '{category}'...")
            replace_tickers_for_category(tickers, category)
        else:
            print(f"Category '{category}' already has data. Skipping population.")

def main():
    """
    Runs the initial database setup.
    """
    print("--- Running Database Setup ---")

    print("\nStep 1: Initializing database schema (creating tables)...")
    init_db()
    print("Schema initialization complete.")

    print("\nStep 2: Populating database with starter ticker lists...")
    initial_populate_db()
    print("Starter data population complete.")

    print("\n--- Database Setup Finished ---")

if __name__ == '__main__':
    main()
