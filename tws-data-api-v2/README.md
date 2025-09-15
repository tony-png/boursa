# TWS Data API v2

A FastAPI application for retrieving real-time stock price data from Interactive Brokers TWS.

## Features

- Real-time stock price data with bid/ask spreads
- Market session detection (pre-market, regular, post-market)
- Extended hours data support
- Multiple stock symbols in a single request
- Comprehensive API documentation
- Health check endpoints

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Configure environment variables in `.env` (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your settings:
   ```
   API_HOST=0.0.0.0
   API_PORT=8000
   TWS_HOST=localhost
   TWS_PORT=7497
   TWS_CLIENT_ID=1
   ```

3. Start the application:
   ```bash
   # Using the configured settings from .env
   uv run python app/main.py
   
   # Or explicitly specify port 8000
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

## API Endpoints

- `GET /stock/{symbol}` - Get stock price data for a single symbol
- `GET /stocks?symbols=AAPL,MSFT,GOOGL` - Get data for multiple symbols
- `GET /health` - Health check
- `GET /docs` - API documentation

## Requirements

- Python 3.9+
- Interactive Brokers TWS or IB Gateway running on localhost:7497
- This API runs on port 8000 by default