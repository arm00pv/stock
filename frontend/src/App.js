import React, { useState, useEffect } from 'react';
import { ethers } from 'ethers';
import axios from 'axios';
import { Line, Pie } from 'react-chartjs-2';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    ArcElement,
} from 'chart.js';

import './App.css';

// --- Smart Contract Details ---
// This should be updated with the actual deployed contract address and ABI
const contractAddress = 'YOUR_CONTRACT_ADDRESS';
const contractABI = [
    // A simplified ABI for the ReportGenerator contract
    "event ReportPaid(address indexed user, uint256 amount)",
    "function generateReport() public payable",
    "function reportFee() public view returns (uint256)"
];

// Register Chart.js components
ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    ArcElement
);

function App() {
    // --- State Variables ---
    const [walletAddress, setWalletAddress] = useState(null);
    const [portfolio, setPortfolio] = useState([{ ticker: '', quantity: '' }]);
    const [report, setReport] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [reportFee, setReportFee] = useState('1'); // Default to 1 MATIC

    // --- Effects ---
    // Effect to fetch the report fee from the smart contract
    useEffect(() => {
        const fetchFee = async () => {
            if (window.ethereum) {
                try {
                    const provider = new ethers.providers.Web3Provider(window.ethereum);
                    const contract = new ethers.Contract(contractAddress, contractABI, provider);
                    const fee = await contract.reportFee();
                    setReportFee(ethers.utils.formatEther(fee));
                } catch (e) {
                    console.error("Could not fetch report fee. Is the contract address correct?", e);
                    setError("Could not connect to the smart contract. Please ensure you are on the correct network (e.g., Polygon).");
                }
            }
        };
        // fetchFee(); // Uncomment when contract address is set
    }, []);


    // --- Handlers ---

    const handlePortfolioChange = (index, event) => {
        const values = [...portfolio];
        values[index][event.target.name] = event.target.value;
        setPortfolio(values);
    };

    const handleAddAsset = () => {
        setPortfolio([...portfolio, { ticker: '', quantity: '' }]);
    };

    const handleRemoveAsset = (index) => {
        const values = [...portfolio];
        values.splice(index, 1);
        setPortfolio(values);
    };

    const connectWallet = async () => {
        if (window.ethereum) {
            try {
                const provider = new ethers.providers.Web3Provider(window.ethereum);
                await provider.send('eth_requestAccounts', []);
                const signer = provider.getSigner();
                const address = await signer.getAddress();
                setWalletAddress(address);
                setError('');
            } catch (err) {
                setError('Failed to connect wallet. Please try again.');
                console.error(err);
            }
        } else {
            setError('MetaMask is not installed. Please install it to continue.');
        }
    };

    const generateReport = async () => {
        if (!walletAddress) {
            setError('Please connect your wallet first.');
            return;
        }

        setIsLoading(true);
        setError('');
        setReport(null);

        try {
            // --- Step 1: Smart Contract Interaction ---
            const provider = new ethers.providers.Web3Provider(window.ethereum);
            const signer = provider.getSigner();
            const contract = new ethers.Contract(contractAddress, contractABI, signer);

            console.log(`Attempting to send ${reportFee} MATIC...`);

            const tx = await contract.generateReport({
                value: ethers.utils.parseEther(reportFee),
            });

            // Wait for the transaction to be mined
            await tx.wait();

            console.log('Payment successful! Transaction hash:', tx.hash);

            // --- Step 2: Backend API Call ---
            const validPortfolio = portfolio.filter(p => p.ticker && p.quantity > 0);
            if(validPortfolio.length === 0) {
                throw new Error("Portfolio is empty or invalid.");
            }

            const response = await axios.post('/api/analyze', validPortfolio);

            setReport(response.data);

        } catch (err) {
            console.error('Report generation failed:', err);
            const message = err.reason || err.message || 'An unknown error occurred.';
            setError(`Failed to generate report: ${message}`);
        } finally {
            setIsLoading(false);
        }
    };

    // --- Render Helpers ---

    const isGenerateDisabled = !walletAddress || portfolio.every(p => !p.ticker || !p.quantity);

    const renderReport = () => {
        if (!report) return null;

        const { totalValue, assets, diversification } = report;

        const pieChartData = {
            labels: assets.map(a => a.ticker),
            datasets: [{
                data: assets.map(a => a.allocation),
                backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'],
            }],
        };

        const sectorChartData = {
            labels: Object.keys(diversification.bySector),
            datasets: [{
                data: Object.values(diversification.bySector),
                backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'],
            }],
        };

        return (
            <div className="report-container">
                <h2>Portfolio Analysis Report</h2>
                <h3>Total Portfolio Value: ${totalValue.toLocaleString()}</h3>

                <div className="charts-container">
                    <div className="chart">
                        <h4>Asset Allocation (%)</h4>
                        <Pie data={pieChartData} />
                    </div>
                     {Object.keys(diversification.bySector).length > 0 && (
                        <div className="chart">
                            <h4>Stock Sector Allocation (%)</h4>
                            <Pie data={sectorChartData} />
                        </div>
                     )}
                </div>

                <h4>Asset Details:</h4>
                <table className="report-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Quantity</th>
                            <th>Price (USD)</th>
                            <th>Total Value (USD)</th>
                            <th>Allocation (%)</th>
                            <th>Asset Class</th>
                            <th>Sector</th>
                        </tr>
                    </thead>
                    <tbody>
                        {assets.map((asset, index) => (
                            <tr key={index}>
                                <td>{asset.ticker}</td>
                                <td>{asset.quantity}</td>
                                <td>${asset.price.toLocaleString()}</td>
                                <td>${asset.value.toLocaleString()}</td>
                                <td>{asset.allocation}%</td>
                                <td>{asset.class}</td>
                                <td>{asset.sector}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };


    return (
        <div className="App">
            <header className="App-header">
                <h1>Crypto-Gated Portfolio Analyzer</h1>
                {!walletAddress ? (
                    <button onClick={connectWallet} className="connect-wallet-btn">Connect Wallet</button>
                ) : (
                    <p className="wallet-address">Connected: {`${walletAddress.substring(0, 6)}...${walletAddress.substring(walletAddress.length - 4)}`}</p>
                )}
            </header>

            <main>
                <div className="form-container">
                    <h2>Enter Your Portfolio</h2>
                    <p>Add your stock (e.g., AAPL) and crypto (e.g., BTC-USD) assets below.</p>
                    {portfolio.map((asset, index) => (
                        <div key={index} className="asset-input">
                            <input
                                type="text"
                                name="ticker"
                                placeholder="e.g., AAPL, BTC-USD"
                                value={asset.ticker}
                                onChange={event => handlePortfolioChange(index, event)}
                                className="ticker-input"
                            />
                            <input
                                type="number"
                                name="quantity"
                                placeholder="Quantity"
                                value={asset.quantity}
                                onChange={event => handlePortfolioChange(index, event)}
                                className="quantity-input"
                            />
                            <button onClick={() => handleRemoveAsset(index)} className="remove-btn">Remove</button>
                        </div>
                    ))}
                    <button onClick={handleAddAsset} className="add-btn">Add Asset</button>
                </div>

                <div className="generate-container">
                    <button
                        onClick={generateReport}
                        disabled={isGenerateDisabled || isLoading}
                        className="generate-btn"
                    >
                        {isLoading ? 'Generating...' : `Generate Report for ${reportFee} MATIC`}
                    </button>
                </div>

                {error && <p className="error-message">{error}</p>}

                {isLoading && <div className="loader"></div>}

                {renderReport()}
            </main>
        </div>
    );
}

export default App;