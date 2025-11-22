import re
import yfinance as yf
from database import get_portfolio_summary, get_portfolio_holdings
from ai_picker import get_stock_analysis, get_latest_news
from ai_trader import audit_portfolio

def process_chat_message(user_id, message):
    """
    Parses user message and returns a structured response.
    """
    message = message.lower().strip()

    # Helper to extract ticker
    # Looks for upper case words in original message or common patterns
    # But since we lowercased, we rely on regex patterns

    # Regex for Ticker (1-5 letters)
    # We'll look for "analyze $TICKER" or just words that match known tickers if possible
    # For simplicity, let's require the user to type the ticker clearly

    # Intent: PRICE
    match = re.search(r'price (of |for )?([a-zA-Z\.]+)', message)
    if match:
        ticker = match.group(2).upper()
        try:
            stock = yf.Ticker(ticker)
            price = stock.history(period='1d')['Close'].iloc[-1]
            return f"The current price of {ticker} is ${price:.2f}."
        except:
            return f"Could not fetch price for {ticker}."

    # Intent: ANALYZE / FORECAST
    match = re.search(r'(analyze|forecast|predict) (of |for )?([a-zA-Z\.]+)', message)
    if match:
        ticker = match.group(3).upper()
        analysis = get_stock_analysis(ticker)
        if analysis:
            return analysis['summary']
        else:
            return f"Could not analyze {ticker}."

    # Intent: NEWS
    match = re.search(r'news (of |for |about )?([a-zA-Z\.]+)', message)
    if match:
        ticker = match.group(2).upper()
        news = get_latest_news(ticker)
        if news:
            top_article = news[0]
            return f"Latest news for {ticker}: <a href='{top_article['url']}' target='_blank'>{top_article['title']}</a> ({top_article['source']})"
        else:
            return f"No recent news found for {ticker}."

    # Intent: PORTFOLIO / AUDIT
    if 'portfolio' in message or 'audit' in message:
        # Check 'main' portfolio by default for now
        summary = get_portfolio_summary('main')
        holdings = get_portfolio_holdings('main')

        response = f"<b>Main Portfolio Status:</b><br>Cash: ${summary[0]:.2f}<br>Invested: ${summary[1]:.2f}<br>"
        if holdings:
            response += "Holdings: " + ", ".join([f"{h['ticker']} ({float(h['shares']):.2f} sh)" for h in holdings])
        else:
            response += "No holdings."

        if 'audit' in message:
            report = audit_portfolio('main')
            recommendations = [f"{r['ticker']}: {r['recommendation']}" for r in report if r['recommendation'] != 'HOLD']
            if recommendations:
                response += "<br><br><b>Audit Actions:</b><br>" + "<br>".join(recommendations)
            else:
                response += "<br><br>Audit: All positions look stable."

        return response

    # Intent: HELLO / HELP
    if 'hello' in message or 'hi' in message or 'help' in message:
        return "Hello! I am your AI Investment Assistant. You can ask me to:<br>- 'Price AAPL'<br>- 'Analyze TSLA'<br>- 'News for GOOG'<br>- 'Check Portfolio'"

    return "I didn't understand that. Try asking for 'Price [Ticker]', 'Analyze [Ticker]', or 'Portfolio'."
