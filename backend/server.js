const express = require('express');
const cors = require('cors');
const axios = require('axios');

// Load environment variables
require('dotenv').config();

const app = express();
const port = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

// --- API Keys ---
// IMPORTANT: You need to get a free API key from Alpha Vantage and add it to a .env file.
const ALPHA_VANTAGE_API_KEY = process.env.ALPHA_VANTAGE_API_KEY;
// CoinGecko API does not strictly require a key for public endpoints, but it's good practice for higher rate limits.
// We will use the public API for this example.

// --- API Endpoints ---
const ALPHA_VANTAGE_URL = 'https://www.alphavantage.co/query';
const COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price';

// --- Helper Functions ---

/**
 * Determines if a ticker is a cryptocurrency.
 * @param {string} ticker - The asset ticker (e.g., 'AAPL', 'BTC-USD').
 * @returns {boolean} - True if it's a crypto ticker.
 */
const isCrypto = (ticker) => ticker.includes('-USD');

/**
 * Fetches the current price for a stock from Alpha Vantage.
 * @param {string} ticker - The stock ticker (e.g., 'AAPL').
 * @returns {Promise<number|null>} - The current price or null if an error occurs.
 */
async function getStockPrice(ticker) {
    if (!ALPHA_VANTAGE_API_KEY) {
        console.error("Alpha Vantage API key is missing.");
        // Return a dummy price for development if no key is provided
        return 100 + Math.random() * 200;
    }
    try {
        const response = await axios.get(ALPHA_VANTAGE_URL, {
            params: {
                function: 'GLOBAL_QUOTE',
                symbol: ticker,
                apikey: ALPHA_VANTAGE_API_KEY,
            },
        });
        const data = response.data['Global Quote'];
        if (data && data['05. price']) {
            return parseFloat(data['05. price']);
        }
        console.warn(`Could not fetch price for stock: ${ticker}`);
        return null;
    } catch (error) {
        console.error(`Error fetching stock price for ${ticker}:`, error.message);
        return null;
    }
}

/**
 * Fetches the sector for a stock from Alpha Vantage.
 * @param {string} ticker - The stock ticker (e.g., 'AAPL').
 * @returns {Promise<string|null>} - The sector or null if an error occurs.
 */
async function getStockSector(ticker) {
    if (!ALPHA_VANTAGE_API_KEY) {
        return "Technology"; // Dummy sector
    }
    try {
        const response = await axios.get(ALPHA_VANTAGE_URL, {
            params: {
                function: 'OVERVIEW',
                symbol: ticker,
                apikey: ALPHA_VANTAGE_API_KEY,
            },
        });
        const data = response.data;
        if (data && data['Sector']) {
            return data['Sector'];
        }
        return 'N/A';
    } catch (error) {
        console.error(`Error fetching sector for ${ticker}:`, error.message);
        return 'N/A';
    }
}

/**
 * Fetches the current price for a cryptocurrency from CoinGecko.
 * @param {string} ticker - The crypto ticker (e.g., 'BTC-USD').
 * @returns {Promise<number|null>} - The current price or null if an error occurs.
 */
async function getCryptoPrice(ticker) {
    const coingeckoId = ticker.split('-')[0].toLowerCase(); // e.g., 'BTC-USD' -> 'bitcoin'
    // A simple map for common tickers, a more robust solution would be needed for a real app
    const idMap = {
        'btc': 'bitcoin',
        'eth': 'ethereum',
        'matic': 'matic-network'
        // Add more mappings as needed
    };
    const finalId = idMap[coingeckoId] || coingeckoId;

    try {
        const response = await axios.get(COINGECKO_URL, {
            params: {
                ids: finalId,
                vs_currencies: 'usd',
            },
        });
        const data = response.data[finalId];
        if (data && data.usd) {
            return data.usd;
        }
        console.warn(`Could not fetch price for crypto: ${ticker}`);
        return null;
    } catch (error) {
        console.error(`Error fetching crypto price for ${ticker}:`, error.message);
        return null;
    }
}

// --- Main API Endpoint ---

app.post('/api/analyze', async (req, res) => {
    const portfolio = req.body; // Expected format: [{ ticker: 'AAPL', quantity: 10 }, ...]

    if (!portfolio || !Array.isArray(portfolio) || portfolio.length === 0) {
        return res.status(400).json({ error: 'Invalid portfolio data.' });
    }

    if (!ALPHA_VANTAGE_API_KEY) {
        console.warn("ALPHA_VANTAGE_API_KEY not set. Using dummy data for stocks.");
    }

    try {
        let totalValue = 0;
        const assetsWithData = [];

        // Process all assets concurrently
        const assetPromises = portfolio.map(async (asset) => {
            const { ticker, quantity } = asset;
            let price, assetClass, sector;

            if (isCrypto(ticker)) {
                price = await getCryptoPrice(ticker);
                assetClass = 'Cryptocurrency';
                sector = 'N/A';
            } else {
                price = await getStockPrice(ticker);
                assetClass = 'Stock';
                sector = await getStockSector(ticker);
            }

            if (price !== null) {
                const value = price * quantity;
                return { ...asset, price, value, class: assetClass, sector };
            }
            return null; // Return null for assets where price fetch failed
        });

        const resolvedAssets = (await Promise.all(assetPromises)).filter(Boolean); // Filter out nulls

        // Calculate total value
        resolvedAssets.forEach(asset => {
            totalValue += asset.value;
        });

        // Calculate allocation and final structure
        const finalAssets = resolvedAssets.map(asset => ({
            ...asset,
            allocation: totalValue > 0 ? parseFloat(((asset.value / totalValue) * 100).toFixed(2)) : 0,
        }));

        // Calculate diversification
        const diversification = { byClass: {}, bySector: {} };
        finalAssets.forEach(asset => {
            // By Class (Stock, Crypto)
            diversification.byClass[asset.class] = (diversification.byClass[asset.class] || 0) + asset.allocation;
            // By Sector (only for stocks)
            if (asset.class === 'Stock') {
                diversification.bySector[asset.sector] = (diversification.bySector[asset.sector] || 0) + asset.value;
            }
        });

        // Normalize sector diversification to be out of 100% of the stock portion
        const totalStockValue = Object.values(diversification.bySector).reduce((sum, val) => sum + val, 0);
        if(totalStockValue > 0) {
            for(const sector in diversification.bySector) {
                diversification.bySector[sector] = parseFloat(((diversification.bySector[sector] / totalStockValue) * 100).toFixed(2));
            }
        }


        res.json({
            totalValue: parseFloat(totalValue.toFixed(2)),
            assets: finalAssets,
            diversification,
        });

    } catch (error) {
        console.error('Analysis failed:', error);
        res.status(500).json({ error: 'Failed to analyze portfolio.' });
    }
});

app.listen(port, () => {
    console.log(`Server is running on port: ${port}`);
});