import os
import requests
import csv
import io
from collections import defaultdict
from database import init_db, update_tickers_from_source, get_tickers_by_category, prune_old_tickers

# Load environment variables for API keys
from dotenv import load_dotenv
load_dotenv()

MARKETAUX_API_KEY = os.environ.get('MARKETAUX_API_KEY')
ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY', 'demo') # Default to 'demo' if not set

def get_all_existing_tickers():
    """Fetches all tickers currently in the database across all categories."""
    all_tickers = set()
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_tickers.update(get_tickers_by_category(category))
    return all_tickers

def load_securities_from_alphavantage():
    """
    Downloads and parses the full security list from Alpha Vantage,
    identifies new stocks, ETFs, and bonds, and returns them as separate lists.
    """
    print("--- Downloading and loading new securities from Alpha Vantage ---")

    url = f"https://www.alphavantage.co/query?function=LISTING_STATUS&apikey={ALPHAVANTAGE_API_KEY}"

    try:
        existing_tickers = get_all_existing_tickers()
        print(f"Found {len(existing_tickers)} existing tickers in the database.")
    except Exception as e:
        print(f"Could not fetch existing tickers from DB, proceeding without check. Error: {e}")
        existing_tickers = set()

    new_stocks, new_etfs, new_bonds = [], [], []

    try:
        response = requests.get(url)
        response.raise_for_status()

        # Use io.StringIO to treat the CSV string content as a file
        csv_file = io.StringIO(response.text)
        reader = csv.DictReader(csv_file)

        for row in reader:
            symbol = row.get('symbol')
            if not symbol or symbol in existing_tickers:
                continue

            asset_type = row.get('assetType')
            name = row.get('name', '').lower()
            status = row.get('status')

            if status != 'Active':
                continue

            if asset_type == 'Stock':
                new_stocks.append(symbol)
            elif asset_type == 'ETF':
                if 'bond' in name or 'treasury' in name or 'fixed income' in name:
                    new_bonds.append(symbol)
                else:
                    new_etfs.append(symbol)

        print(f"Found {len(new_stocks)} new stocks.")
        print(f"Found {len(new_etfs)} new equity ETFs.")
        print(f"Found {len(new_bonds)} new bond ETFs.")

        return new_stocks, new_etfs, new_bonds

    except requests.exceptions.RequestException as e:
        print(f"Error downloading from Alpha Vantage: {e}")
        return [], [], []
    except Exception as e:
        print(f"An error occurred while parsing the securities list: {e}")
        return [], [], []

# --- Main Execution ---
def run_scraper_pipeline():
    """
    Runs the full pipeline to enrich the database with new securities.
    """
    print("--- Starting Data Enrichment Pipeline ---")
    # init_db() # Should be called from a dedicated setup script

    # Step 1: Load new securities from Alpha Vantage
    new_stocks, new_etfs, new_bonds = load_securities_from_alphavantage()

    if new_stocks:
        update_tickers_from_source(new_stocks, 'generic_stock', 'https://www.alphavantage.co')
    if new_etfs:
        update_tickers_from_source(new_etfs, 'etf', 'https://www.alphavantage.co')
    if new_bonds:
        update_tickers_from_source(new_bonds, 'bond', 'https://www.alphavantage.co')

    print("\n--- Data Enrichment Pipeline Finished ---")

if __name__ == '__main__':
    run_scraper_pipeline()
