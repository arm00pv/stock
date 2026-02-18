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

class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        flask_app.testing = True
        self.client = flask_app.test_client()

        # Mock database connection
        self.db_patcher = patch('database.get_db_connection')
        self.mock_get_db = self.db_patcher.start()
        self.mock_conn = MagicMock()
        self.mock_get_db.return_value = self.mock_conn

    def tearDown(self):
        self.db_patcher.stop()

    def test_compare_endpoint(self):
        with patch('beta_features.compare_stocks', return_value={'ticker1': {'price': 100}, 'ticker2': {'price': 200}}):
            response = self.client.get('/api/beta/compare?ticker1=AAPL&ticker2=MSFT')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['ticker1']['price'], 100)

    def test_history_endpoint(self):
        with patch('beta_features.get_history_data', return_value={'labels': ['2023-01-01'], 'data': [150]}):
            response = self.client.get('/api/history/AAPL')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['data'][0], 150)

if __name__ == '__main__':
    unittest.main()
