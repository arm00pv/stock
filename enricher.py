import pandas as pd
import yfinance as yf
import time
from database import get_tickers_by_category, get_db_connection, update_stock_details_batch
from dotenv import load_dotenv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

def scrape_sp500_tickers():
    """
    Scrapes the Wikipedia page for the list of S&P 500 companies.
    Returns a set of ticker symbols.
    """
    print("Scraping Wikipedia for S&P 500 component list...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tables = pd.read_html(response.text)
        sp500_table = tables[0]
        tickers = set(sp500_table['Symbol'].tolist())
        print(f"Successfully scraped {len(tickers)} S&P 500 tickers.")
        return tickers
    except Exception as e:
        print(f"Could not scrape S&P 500 list: {e}")
        return set()

def process_ticker(ticker, sp500_tickers):
    """Fetches info for a single ticker."""
    try:
        print(f"Enriching {ticker}...")
        stock_info = yf.Ticker(ticker).info
        market_cap = stock_info.get('marketCap')
        sector = stock_info.get('sector')
        is_sp500 = ticker in sp500_tickers

        if market_cap or sector or is_sp500:
            return (market_cap, sector, is_sp500, ticker)
        else:
            print(f"  -> No new info found for {ticker}.")
            return None
    except Exception as e:
        print(f"  -> Error processing {ticker}: {e}")
        return None

def run_enrichment():
    """
    Goes through all securities in the 'stocks' table and enriches them
    with market cap, sector, and S&P 500 status.
    """
    print("--- Starting Data Enrichment Pipeline ---")

    sp500_tickers = scrape_sp500_tickers()

    print("Fetching all existing tickers from database...")
    all_db_tickers = set()
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_db_tickers.update(get_tickers_by_category(category))

    print(f"Found {len(all_db_tickers)} total unique tickers to enrich.")
    enriched_count = 0
    updates = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(process_ticker, ticker, sp500_tickers): ticker for ticker in all_db_tickers}

        for future in as_completed(future_to_ticker):
            result = future.result()
            if result:
                updates.append(result)
                enriched_count += 1

                # Batch update every 50 records to prevent memory build up or large transactions
                if len(updates) >= 50:
                    update_stock_details_batch(updates)
                    updates = []

    # Update remaining
    if updates:
        update_stock_details_batch(updates)

    print(f"--- Data Enrichment Pipeline Finished. Enriched {enriched_count} tickers. ---")

if __name__ == '__main__':
    run_enrichment()
