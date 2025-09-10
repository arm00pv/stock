import requests
from bs4 import BeautifulSoup
import re

def scrape_monthly_dividend_stocks():
    """
    Scrapes a list of monthly dividend stock tickers from the simplysafedividends article.
    """
    URL = "https://www.simplysafedividends.com/world-of-dividends/posts/42-2025-monthly-dividend-stocks-list-all-76-ranked-and-analyzed"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(URL, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')

    all_tickers = set()
    ticker_regex = re.compile(r'\(([A-Z]{1,5})\)')

    content = soup.find('div', class_='trix-content')
    if not content:
        print("Could not find the main content div.")
        return []

    # --- Scrape the main list of stocks ---
    headings = content.find_all('h2')

    for heading in headings:
        if "Monthly Dividend Stock #" in heading.get_text():
            # Search the next few sibling elements for the ticker
            for sibling in heading.find_next_siblings(limit=5):
                if sibling.name == 'div':
                    strong_tag = sibling.find('strong')
                    if strong_tag:
                        match = ticker_regex.search(strong_tag.get_text())
                        if match:
                            all_tickers.add(match.group(1))
                            # Once found, break to avoid finding other tickers
                            # in the same section and move to the next heading
                            break
                # Stop if we hit the next h2
                if sibling.name == 'h2':
                    break

    # --- Scrape the Micro-Cap and OTC list ---
    micro_cap_heading = content.find('h2', string=re.compile(r'Micro-Cap and OTC Monthly Dividend Stocks'))
    if micro_cap_heading:
        # The stocks are in <ul> tags that follow this heading
        for sibling in micro_cap_heading.find_next_siblings():
            if sibling.name == 'ul':
                li = sibling.find('li')
                if li:
                    strong_tag = li.find('strong')
                    if strong_tag:
                        match = ticker_regex.search(strong_tag.get_text())
                        if match:
                            all_tickers.add(match.group(1))
            if sibling.name == 'h2':
                break

    return sorted(list(all_tickers))

if __name__ == '__main__':
    scraped_tickers = scrape_monthly_dividend_stocks()
    if scraped_tickers:
        print("Scraped Monthly Dividend Stock Tickers:")
        print(str(scraped_tickers))
    else:
        print("Could not scrape any tickers.")
