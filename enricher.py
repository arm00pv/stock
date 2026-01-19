import pandas as pd
import yfinance as yf
import time
import json
import os
import io
from database import get_tickers_by_category, update_stock_details_batch
from dotenv import load_dotenv
import requests

load_dotenv()

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sp500_cache.json')
CACHE_TTL = 86400  # 24 hours

def get_sp500_tickers():
    """Scrapes S&P 500 tickers with local caching."""
    if os.path.exists(CACHE_FILE):
        if time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
            try:
                with open(CACHE_FILE, 'r') as f:
                    print("Loading S&P 500 tickers from cache...")
                    return set(json.load(f))
            except Exception as e:
                print(f"Error reading cache: {e}")

    print("Scraping Wikipedia for S&P 500 component list...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        # Use StringIO to avoid FutureWarning
        tables = pd.read_html(io.StringIO(response.text))
        sp500_table = tables[0]
        tickers = set(sp500_table['Symbol'].tolist())

        with open(CACHE_FILE, 'w') as f:
            json.dump(list(tickers), f)

        print(f"Successfully scraped and cached {len(tickers)} S&P 500 tickers.")
        return tickers
    except Exception as e:
        print(f"Could not scrape S&P 500 list: {e}")
        return set()

def run_enrichment():
    """
    Goes through all securities in the 'stocks' table and enriches them.
    Uses batch processing to improve performance.
    """
    print("--- Starting Data Enrichment Pipeline ---")

    sp500_tickers = get_sp500_tickers()

    print("Fetching all existing tickers from database...")
    all_db_tickers = set()
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_db_tickers.update(get_tickers_by_category(category))

    print(f"Found {len(all_db_tickers)} total unique tickers to enrich.")
    enriched_count = 0
    batch_size = 50
    updates_buffer = []

    ticker_list = list(all_db_tickers)

    # Process in chunks to enable batch yfinance calls if possible,
    # but yfinance .info is per ticker usually. We still batch the DB writes.

    for i in range(0, len(ticker_list), batch_size):
        batch_tickers = ticker_list[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}...")

        for ticker in batch_tickers:
            try:
                # print(f"Enriching {ticker}...") # Verbose
                stock_info = yf.Ticker(ticker).info

                market_cap = stock_info.get('marketCap')
                sector = stock_info.get('sector')
                is_sp500 = ticker in sp500_tickers

                if market_cap or sector or is_sp500:
                    updates_buffer.append((market_cap, sector, 1 if is_sp500 else 0, ticker))
            except Exception as e:
                # print(f"  -> Error processing {ticker}: {e}")
                pass

        if updates_buffer:
            update_stock_details_batch(updates_buffer)
            enriched_count += len(updates_buffer)
            updates_buffer = []
            print(f"  Committed batch. Total enriched so far: {enriched_count}")

        # Small sleep between batches to be nice to API
        time.sleep(1)

    print(f"--- Data Enrichment Pipeline Finished. Enriched {enriched_count} tickers. ---")

if __name__ == '__main__':
    run_enrichment()
