import yfinance as yf

def screen_stocks(criteria):
    # This is a placeholder for a more sophisticated stock screener.
    # For now, we'll just use a predefined list of tickers.
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "JPM", "JNJ", "V", "NVDA", "O"]

    results = []
    for ticker_symbol in tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info

            # Apply filters
            market_cap = info.get('marketCap', 0)
            pe_ratio = info.get('trailingPE')
            dividend_yield = info.get('dividendYield', 0)
            sector = info.get('sector', '')

            if criteria['market_cap_min'] and market_cap < float(criteria['market_cap_min']):
                continue
            if criteria['market_cap_max'] and market_cap > float(criteria['market_cap_max']):
                continue
            if pe_ratio and criteria['pe_ratio_min'] and pe_ratio < float(criteria['pe_ratio_min']):
                continue
            if pe_ratio and criteria['pe_ratio_max'] and pe_ratio > float(criteria['pe_ratio_max']):
                continue
            if dividend_yield and criteria['dividend_yield_min'] and dividend_yield < float(criteria['dividend_yield_min']):
                continue
            if dividend_yield and criteria['dividend_yield_max'] and dividend_yield > float(criteria['dividend_yield_max']):
                continue
            if criteria['sector'] and sector != criteria['sector']:
                continue

            results.append({
                "ticker": ticker_symbol,
                "name": info.get('shortName', ''),
                "market_cap": f"${market_cap:,}",
                "pe_ratio": f"{pe_ratio:.2f}" if pe_ratio else "N/A",
                "dividend_yield": f"{(dividend_yield or 0) * 100:.2f}%",
                "sector": sector,
            })
        except Exception as e:
            print(f"Could not process {ticker_symbol}: {e}")
            continue

    return results