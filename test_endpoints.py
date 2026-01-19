import unittest
from unittest.mock import MagicMock, patch
import json
import sys

# Mock dependencies
sys.modules['mysql'] = MagicMock()
sys.modules['mysql.connector'] = MagicMock()
sys.modules['yfinance'] = MagicMock()

# Patch yfinance inside modules
import yfinance as yf

# Import app after mocking
import app
from app import app as flask_app

class TestEndpoints(unittest.TestCase):
    def setUp(self):
        flask_app.testing = True
        self.client = flask_app.test_client()

        # Mock database connection
        self.db_patcher = patch('database.get_db_connection')
        self.mock_get_db = self.db_patcher.start()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_get_db.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

    def tearDown(self):
        self.db_patcher.stop()

    def test_home(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_api_signals(self):
        with patch('beta_features.calculate_smart_signals', return_value={'signal': 'Buy', 'rsi': 25, 'macd': 0.5}):
            response = self.client.get('/api/beta/signals/AAPL')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['signal'], 'Buy')

    def test_api_chat(self):
        with patch('app.get_ai_response', return_value="I am AI"):
            response = self.client.post('/api/chat', json={'message': 'Hello'})
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['response'], 'I am AI')

    def test_api_anomalies(self):
        with patch('beta_features.detect_anomalies', return_value=[{'ticker': 'TSLA', 'reason': 'Vol'}]):
            response = self.client.get('/api/beta/anomalies')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]['ticker'], 'TSLA')

    def test_portfolio_parallel_pricing(self):
        # Mock portfolio holdings
        holdings = [{'ticker': 'AAPL', 'shares': 10, 'purchase_price': 150, 'purchase_date': '2023-01-01', 'sell_flag': 0}]

        # We need to mock get_portfolio_summary and get_portfolio_holdings where they are USED (app.py)
        with patch('app.get_portfolio_summary', return_value=(1000.0, 500.0)), \
             patch('app.get_portfolio_holdings', return_value=holdings), \
             patch('app.get_from_cache', return_value=None), \
             patch('app.set_in_cache') as mock_cache_set:

            # We also need to mock yfinance.Ticker inside the threaded function
            # Since it runs in a thread, standard patching might be tricky.
            # However, we patched yfinance globally in sys.modules, so it should work.
            mock_ticker = MagicMock()
            mock_ticker.info.get.return_value = 160.0 # Current price
            yf.Ticker.return_value = mock_ticker

            response = self.client.get('/api/portfolio/main')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)

            self.assertEqual(len(data['holdings']), 1)
            self.assertEqual(data['holdings'][0]['current_price'], 160.0)
            self.assertEqual(data['holdings'][0]['current_value'], 1600.0) # 10 * 160

if __name__ == '__main__':
    unittest.main()
