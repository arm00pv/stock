import random
import re
from beta_features import generate_trade_thesis, calculate_smart_signals, get_pro_details

class AIAssistant:
    def __init__(self):
        self.intents = {
            'price': r'price of (\w+)',
            'analysis': r'analyze (\w+)',
            'news': r'news on (\w+)',
            'risk': r'risk for (\w+)',
            'compare': r'compare (\w+) and (\w+)',
            'greeting': r'(hi|hello|hey)'
        }

    def process_query(self, query):
        query = query.lower()

        for intent, pattern in self.intents.items():
            match = re.search(pattern, query)
            if match:
                if intent == 'price':
                    return self.handle_price(match.group(1))
                elif intent == 'analysis':
                    return self.handle_analysis(match.group(1))
                elif intent == 'risk':
                    return self.handle_risk(match.group(1))
                elif intent == 'greeting':
                    return "Hello! I am your AI Investment Assistant. Ask me about stock prices, analysis, or risk."
                # ... add other handlers

        return "I'm not sure I understand. Try asking 'analyze AAPL' or 'price of TSLA'."

    def handle_price(self, ticker):
        ticker = ticker.upper()
        # In a real scenario, fetch real price. Mocking here or import yfinance
        import yfinance as yf
        try:
            p = yf.Ticker(ticker).info.get('regularMarketPrice')
            return f"The current price of {ticker} is ${p}"
        except:
            return f"Could not fetch price for {ticker}."

    def handle_analysis(self, ticker):
        ticker = ticker.upper()
        try:
            thesis = generate_trade_thesis(ticker)
            return f"{thesis['thesis']} (Confidence: {thesis['confidence']})"
        except:
            return f"Could not analyze {ticker}."

    def handle_risk(self, ticker):
        ticker = ticker.upper()
        details = get_pro_details(ticker)
        beta = details.get('beta')
        if beta:
            risk_level = "High" if beta > 1.2 else "Low" if beta < 0.8 else "Moderate"
            return f"{ticker} has a Beta of {beta}, indicating {risk_level} market volatility relative to the S&P 500."
        return f"Risk data unavailable for {ticker}."

assistant = AIAssistant()

def get_ai_response(user_message):
    return assistant.process_query(user_message)
