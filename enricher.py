import pandas as pd
import yfinance as yf
from database import get_tickers_by_category, get_db_connection
from dotenv import load_dotenv

load_dotenv()

import requests

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
        # pandas.read_html can take the HTML text directly
        tables = pd.read_html(response.text)
        sp500_table = tables[0]
        # The ticker symbol is in the 'Symbol' column
        tickers = set(sp500_table['Symbol'].tolist())
        print(f"Successfully scraped {len(tickers)} S&P 500 tickers.")
        return tickers
    except Exception as e:
        print(f"Could not scrape S&P 500 list: {e}")
        return set()

def update_stock_details(ticker, market_cap, sector, is_sp500):
    """Updates a single stock's details in the database."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        sql = """
            UPDATE stocks
            SET market_cap = %s, sector = %s, is_sp500 = %s
            WHERE ticker = %s
        """
        cursor.execute(sql, (market_cap, sector, 1 if is_sp500 else 0, ticker))
        conn.commit()
    except Exception as e:
        print(f"Error updating details for {ticker}: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def run_enrichment():
    """
    Goes through all securities in the 'stocks' table and enriches them
    with market cap, sector, and S&P 500 status.
    """
    print("--- Starting Data Enrichment Pipeline ---")

    sp500_tickers = scrape_sp500_tickers()

    # Get all tickers from all categories in our database
    # This is inefficient, a better way would be a single query.
    # But for a script that runs periodically, it's acceptable.
    print("Fetching all existing tickers from database...")
    all_db_tickers = set()
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_db_tickers.update(get_tickers_by_category(category))

    print(f"Found {len(all_db_tickers)} total unique tickers to enrich.")

    for ticker in all_db_tickers:
        try:
            print(f"Enriching {ticker}...")
            stock_info = yf.Ticker(ticker).info

            market_cap = stock_info.get('marketCap')
            sector = stock_info.get('sector')
            is_sp500 = ticker in sp500_tickers

            if market_cap and sector:
                update_stock_details(ticker, market_cap, sector, is_sp500)
            else:
                # Also flag S&P 500 stocks even if other info is missing
                if is_sp500:
                    update_stock_details(ticker, None, None, True)
                print(f"  -> Could not find full info for {ticker}.")

        except Exception as e:
            print(f"  -> Error processing {ticker}: {e}")

    print("--- Data Enrichment Pipeline Finished ---")

if __name__ == '__main__':
    run_enrichment()
