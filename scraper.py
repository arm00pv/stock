import requests
from bs4 import BeautifulSoup
import re
import time
import csv
from database import init_db, update_tickers_from_source, get_tickers_by_category, prune_old_tickers

def get_all_existing_tickers():
    """Fetches all tickers currently in the database across all categories."""
    all_tickers = set()
    # Assuming get_tickers_by_category can be called for all existing categories
    # A more robust way might be a direct SQL query, but this works for now.
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_tickers.update(get_tickers_by_category(category))
    return all_tickers

def load_securities_from_alphavantage():
    """
    Parses the local etf_list.csv, identifies new stocks, ETFs, and bonds,
    and returns them as separate lists.
    """
    print("--- Loading new securities from Alpha Vantage file ---")

    try:
        existing_tickers = get_all_existing_tickers()
        print(f"Found {len(existing_tickers)} existing tickers in the database.")
    except Exception as e:
        print(f"Could not fetch existing tickers from DB, proceeding without check. Error: {e}")
        existing_tickers = set()

    new_stocks, new_etfs, new_bonds = [], [], []

    try:
        with open('etf_list.csv', mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
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

    except FileNotFoundError:
        print("Error: etf_list.csv not found. Please download it first.")
        return [], [], []
    except Exception as e:
        print(f"An error occurred while parsing the securities list: {e}")
        return [], [], []

# --- Main Execution ---
def run_scraper_pipeline():
    """
    Runs the full pipeline to enrich the database with new securities.
    """
    init_db()
    print("--- Starting Data Enrichment Pipeline ---")

    # Step 1: Load new securities from Alpha Vantage file
    new_stocks, new_etfs, new_bonds = load_securities_from_alphavantage()

    if new_stocks:
        update_tickers_from_source(new_stocks, 'generic_stock', 'https://www.alphavantage.co')
    if new_etfs:
        update_tickers_from_source(new_etfs, 'etf', 'https://www.alphavantage.co')
    if new_bonds:
        update_tickers_from_source(new_bonds, 'bond', 'https://www.alphavantage.co')

    # Note: Web scraping for other sources is disabled for this focused task.
    # We can re-enable it later if needed.

    print("\n--- Data Enrichment Pipeline Finished ---")

if __name__ == '__main__':
    run_scraper_pipeline()
