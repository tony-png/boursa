# TWS Orders API v2

FastAPI application for Interactive Brokers TWS order management with multi-client support.

## Tech Stack
- **FastAPI** - Modern Python web framework
- **ib_insync** - Interactive Brokers TWS/Gateway connection library  
- **UV** - Fast Python package manager (REQUIRED)
- **Pydantic** - Data validation and settings management
- **nest-asyncio** - Event loop compatibility for ib_insync

## Quick Start

### Prerequisites
- Python 3.8+
- UV package manager installed
- Interactive Brokers TWS or IB Gateway running on localhost:7497

### Setup
```bash
# Install dependencies
uv sync

# Copy environment file
cp .env.example .env

# Edit .env with your TWS settings
# CLIENT_ID=0 (for master access to all orders)
# TWS_PORT=7497 (or 7496 for live trading)
```

### Development Server
```bash
# Start development server
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Or use specific port
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app

# Run specific test file
uv run pytest tests/test_orders.py -v
```

## API Endpoints

### Core Order Management
- `GET /api/v1/orders` - Get orders from current client
- `GET /api/v1/orders/all` - **Get orders from ALL client IDs** 
- `POST /api/v1/orders` - Create new order
- `GET /api/v1/orders/{id}` - Get specific order
- `PUT /api/v1/orders/{id}` - Modify order
- `DELETE /api/v1/orders/{id}` - Cancel single order
- `DELETE /api/v1/orders/cancel-all` - **Cancel ALL orders across ALL clients**

### Account & Position Data
- `GET /api/v1/positions` - Get all positions
- `GET /api/v1/account` - Get account summary
- `GET /health` - Health check with TWS connection status

### Documentation
- `GET /docs` - Interactive Swagger UI
- `GET /redoc` - ReDoc documentation

## Multi-Client Order Management

This API supports advanced multi-client scenarios using `reqAllOpenOrders()`:

### Key Features
- **Cross-Client Visibility**: See orders from all client IDs
- **Smart Cancellation**: Automatically connects with correct client ID to cancel orders
- **Master Client Mode**: Use CLIENT_ID=0 for broad order visibility

### Example Usage
```bash
# See ALL orders from ALL clients
curl http://localhost:8001/api/v1/orders/all

# Cancel ALL orders across ALL client IDs
curl -X DELETE http://localhost:8001/api/v1/orders/cancel-all
```

## Environment Configuration

Key `.env` variables:

### TWS Connection
```
TWS_HOST=localhost
TWS_PORT=7497          # Paper trading (7496 for live)
CLIENT_ID=0            # Use 0 for master client access
CONNECTION_TIMEOUT=10
```

### API Settings  
```
API_HOST=0.0.0.0
API_PORT=8001
DEBUG=true
LOG_LEVEL=info
```

## Project Structure
```
app/
├── main.py              # FastAPI app with lifespan management
├── config.py            # Pydantic settings from .env
├── models/
│   └── orders.py        # Order request/response models
├── services/
│   └── ib_service.py    # TWS connection & order management
├── routers/
│   └── orders.py        # API endpoints
└── utils/
    └── exceptions.py    # Custom exceptions
```

## Troubleshooting

### "This event loop is already running" Error
- **Fixed automatically** with `nest_asyncio.apply()` in `main.py`
- Common when using ib_insync with FastAPI

### Connection Issues
```bash
# Check TWS is running
netstat -an | find "7497"

# Test connection manually
curl http://localhost:8001/health
```

### Order Not Found Across Clients
- Use `GET /api/v1/orders/all` instead of `/orders`
- Check CLIENT_ID configuration
- Verify order wasn't created by different client

### Client ID Conflicts  
- Use unique CLIENT_ID for each API instance
- CLIENT_ID=0 provides master access but is view-only for cross-client orders
- Orders can only be modified/cancelled by the client that created them

## Development Commands

### Code Quality
```bash
# If you have linting/formatting tools
uv run black app/
uv run ruff check app/
```

### Database/Migrations (if applicable)
```bash
# No database - this API connects directly to TWS
```

### Background Services
```bash
# Start multiple instances for testing
uv run python -m uvicorn app.main:app --port 8001 &
uv run python -m uvicorn app.main:app --port 8002 &
```

## Claude Code Integration

### Recommended Commands
```bash
# Start development server
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# Run tests
uv run pytest

# Quick API test
curl http://localhost:8001/health
```

### Testing Multi-Client Features
1. Start API with CLIENT_ID=0: `uv run python -m uvicorn app.main:app --port 8001`
2. Create orders from different clients using the API
3. Test cross-client visibility: `curl http://localhost:8001/api/v1/orders/all`
4. Test mass cancellation: `curl -X DELETE http://localhost:8001/api/v1/orders/cancel-all`

## Production Considerations

- Use `CLIENT_ID=0` for monitoring/management instances
- Set appropriate `CONNECTION_TIMEOUT` for your network
- Monitor `TWS_PORT` (7496 for live trading)
- Consider rate limiting for production deployment
- Implement proper logging and monitoring

## Dependencies

Core production dependencies managed by UV:
- `fastapi>=0.104.0` - Web framework
- `ib-insync>=0.9.86` - TWS connection library
- `nest-asyncio>=1.5.0` - Event loop compatibility
- `pydantic-settings>=2.0.0` - Environment management

Development dependencies:
- `pytest>=7.4.0` - Testing framework  
- `pytest-asyncio>=0.21.0` - Async test support
- `httpx>=0.25.0` - HTTP client for testing