# Interactive Brokers TWS API Suite

This repository contains two FastAPI applications for connecting to Interactive Brokers Trader Workstation (TWS).

## Services Overview

### 🔍 TWS Data API v2 - Port 8000
**Location**: `tws-data-api-v2/`  
**Purpose**: Real-time stock price data retrieval  
**Default Port**: 8000

**Key Features**:
- Real-time stock price data with bid/ask spreads
- Market session detection (pre-market, regular, post-market)  
- Extended hours data support
- Multiple stock symbols in single request
- Health monitoring

**Quick Start**:
```bash
cd tws-data-api-v2/
cp .env.example .env
uv sync
uv run python app/main.py  # Runs on port 8000
```

**Documentation**: http://localhost:8000/docs

---

### 📋 TWS Orders API v2 - Port 8001
**Location**: `tws-orders-api-v2/`  
**Purpose**: Order management and execution  
**Default Port**: 8001

**Key Features**:
- Create, modify, and cancel orders
- Multi-client order visibility (see orders from all client IDs)
- Mass order cancellation across all clients
- Advanced rate limiting and emergency breaker
- Account and position data access
- Comprehensive debugging endpoints

**Quick Start**:
```bash
cd tws-orders-api-v2/
cp .env.example .env
uv sync
uv run python app/main.py  # Runs on port 8001
```

**Documentation**: http://localhost:8001/docs

---

## Running Both Services

To run both APIs simultaneously:

```bash
# Terminal 1 - Data API
cd tws-data-api-v2/
uv run python app/main.py

# Terminal 2 - Orders API  
cd tws-orders-api-v2/
uv run python app/main.py
```

Or using uvicorn explicitly with ports:

```bash
# Terminal 1 - Data API on port 8000
cd tws-data-api-v2/
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Orders API on port 8001
cd tws-orders-api-v2/  
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Prerequisites

### Common Requirements
- Python 3.9+
- UV package manager
- Interactive Brokers TWS or IB Gateway running on localhost:7497

### TWS Configuration
Both APIs connect to TWS/IB Gateway. Make sure you have:
- TWS running on localhost:7497 (paper trading) or 7496 (live)
- API connections enabled in TWS (File → Global Configuration → API → Settings)
- Different CLIENT_ID values for each API to avoid conflicts

## Environment Configuration

### Data API (.env)
```
API_HOST=0.0.0.0
API_PORT=8000
TWS_HOST=localhost
TWS_PORT=7497
TWS_CLIENT_ID=10
```

### Orders API (.env)  
```
API_HOST=0.0.0.0
API_PORT=8001
TWS_HOST=localhost
TWS_PORT=7497
CLIENT_ID=11
```

## API Endpoints Summary

### Data API (Port 8000)
- `GET /health` - Health check
- `GET /stock/{symbol}` - Get single stock price
- `GET /stocks?symbols=AAPL,MSFT` - Get multiple stock prices
- `GET /docs` - API documentation

### Orders API (Port 8001)
- `GET /health` - Health check with TWS connection status
- `POST /api/v1/orders` - Create new order
- `GET /api/v1/orders` - Get orders from current client
- `GET /api/v1/orders/all` - Get ALL orders from ALL clients
- `DELETE /api/v1/orders/cancel-all` - Cancel all orders across all clients
- `GET /api/v1/positions` - Get positions
- `GET /api/v1/account` - Get account summary
- `GET /docs` - API documentation

## Technology Stack

- **FastAPI** - Modern Python web framework
- **ib_insync** - Interactive Brokers connection library
- **UV** - Fast Python package manager
- **Pydantic** - Data validation and settings
- **nest-asyncio** - Event loop compatibility

## Development

Each service has its own development workflow. See individual README files:
- [TWS Data API v2 README](./tws-data-api-v2/README.md)
- [TWS Orders API v2 CLAUDE.md](./tws-orders-api-v2/CLAUDE.md)

## Testing APIs

Quick health checks:
```bash
# Data API
curl http://localhost:8000/health

# Orders API
curl http://localhost:8001/health
```

## Troubleshooting

### Port Conflicts
If you encounter port conflicts, check:
```bash
# Check what's running on ports
netstat -an | findstr "8000"
netstat -an | findstr "8001"
```

### TWS Connection Issues
1. Ensure TWS/IB Gateway is running
2. Check API settings are enabled in TWS
3. Verify client IDs don't conflict
4. Check firewall settings

### Different Client IDs
The two APIs use different CLIENT_ID values to avoid conflicts:
- Data API: CLIENT_ID=10
- Orders API: CLIENT_ID=11

This allows both APIs to connect to TWS simultaneously without interfering with each other.

## License

MIT License - see individual project files for details.