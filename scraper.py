import requests
from bs4 import BeautifulSoup
import re
import time
import csv
from database import init_db, update_tickers_from_source, prune_old_tickers

# --- Alpha Vantage ETF Loader ---
def load_etfs_from_alphavantage():
    """
    Parses the local etf_list.csv file from Alpha Vantage and returns a list of ETF tickers.
    """
    print("--- Loading ETFs from Alpha Vantage file ---")
    etf_tickers = []
    try:
        with open('etf_list.csv', mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                # We only want active ETFs
                if row.get('assetType') == 'ETF' and row.get('status') == 'Active':
                    etf_tickers.append(row['symbol'])
        print(f"Found {len(etf_tickers)} active ETF tickers in the file.")
        return etf_tickers
    except FileNotFoundError:
        print("Error: etf_list.csv not found. Please download it first.")
        return []
    except Exception as e:
        print(f"An error occurred while parsing the ETF list: {e}")
        return []

# --- Parser for simplysafedividends.com ---
def parse_simplysafedividends(soup):
    all_tickers = set()
    ticker_regex = re.compile(r'\(([A-Z]{1,5})\)')
    content = soup.find('div', class_='trix-content')
    if not content:
        print("Error (simplysafedividends): Could not find the main content div.")
        return set()
    # ... (rest of the function is unchanged)
    return all_tickers

# --- Parser for kiplinger.com ---
def parse_kiplinger(soup):
    # ... (function is unchanged)
    return set()

# --- Generic Scraper ---
def scrape_website(url, parser_func):
    print(f"Attempting to scrape source: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return parser_func(soup)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# --- Main Execution ---
def run_scraper_pipeline():
    """
    Runs the full pipeline: initializes DB, loads ETFs, scrapes all sources, and prunes old entries.
    """
    init_db()
    print("--- Starting Scraper Pipeline ---")

    # Step 1: Load ETFs from Alpha Vantage file
    etf_tickers = load_etfs_from_alphavantage()
    if etf_tickers:
        update_tickers_from_source(etf_tickers, 'etf', 'https://www.alphavantage.co')

    # Step 2: Scrape other web sources
    sources = [
        {
            "category": "monthly_dividend",
            "url": "https://www.simplysafedividends.com/world-of-dividends/posts/42-2025-monthly-dividend-stocks-list-all-76-ranked-and-analyzed",
            "parser": parse_simplysafedividends
        },
        {
            "category": "high_yield",
            "url": "https://www.kiplinger.com/investing/stocks-with-the-highest-dividend-yields-in-the-sandp-500",
            "parser": parse_kiplinger
        }
    ]

    for source in sources:
        print(f"\n--- Processing: {source['category']} from {source['url']} ---")
        scraped_tickers = scrape_website(source['url'], source['parser'])

        if scraped_tickers is not None and len(scraped_tickers) > 0:
            update_tickers_from_source(list(scraped_tickers), source['category'], source['url'])
        else:
            print(f"Scraping failed or returned no tickers for source: {source['url']}. No updates will be made from this source.")

        time.sleep(3)

    # Step 3: Prune old tickers
    print("\n--- Pruning old tickers ---")
    prune_old_tickers(days_old=90)
    print("\n--- Scraper Pipeline Finished ---")

if __name__ == '__main__':
    run_scraper_pipeline()
