import logging
from contextlib import asynccontextmanager
from datetime import datetime

import nest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import orders
from app.services.ib_service import ib_service
from app.middleware.rate_limiting import RateLimitMiddleware, rate_limit_429_handler

# Apply nest_asyncio patch to allow nested event loops
nest_asyncio.apply()


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown events."""
    # Startup
    logger.info("Starting TWS Orders API v2")
    try:
        connected = await ib_service.connect()
        if connected:
            logger.info("Successfully connected to TWS")
        else:
            logger.warning("Failed to connect to TWS - API will start without TWS connection")
    except Exception as e:
        logger.error(f"Failed to connect to TWS: {e}")
        logger.warning("API will start without TWS connection")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TWS Orders API v2")
    try:
        await ib_service.disconnect()
        logger.info("Disconnected from TWS")
    except Exception as e:
        logger.error(f"Error during TWS disconnection: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
if settings.enable_rate_limiting:
    app.add_middleware(RateLimitMiddleware)
    logger.info("Rate limiting middleware enabled")

# Add exception handlers
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request, exc):
    if exc.status_code == 429:
        return await rate_limit_429_handler(request, exc)
    raise exc

# Include routers
app.include_router(orders.router, prefix="/api/v1", tags=["orders"])


@app.get("/health", tags=["health"])
async def health_check():
    """Enhanced health check endpoint with detailed system information."""
    is_connected = ib_service.is_connected()
    breaker_status = ib_service.get_emergency_breaker_status()
    
    # Try to reconnect if not connected
    if not is_connected:
        try:
            is_connected = await ib_service.connect()
            logger.info(f"Health check - reconnected to TWS: {is_connected}")
        except Exception as e:
            logger.warning(f"Health check - could not reconnect to TWS: {e}")
            is_connected = False
    
    return {
        "status": "healthy" if is_connected and not breaker_status["active"] else "degraded",
        "tws_connected": is_connected,
        "emergency_breaker": breaker_status,
        "version": settings.api_version,
        "timestamp": datetime.now().isoformat(),
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "tws_host": settings.tws_host,
        "tws_port": settings.tws_port,
        "client_id": settings.client_id,
        "debug_mode": settings.debug,
    }


@app.get("/debug/config", tags=["debug"])
async def get_api_configuration():
    """Get current API configuration for debugging."""
    return {
        "api_settings": {
            "title": settings.api_title,
            "version": settings.api_version,
            "debug": settings.debug,
            "log_level": settings.log_level,
            "host": settings.api_host,
            "port": settings.api_port,
        },
        "tws_settings": {
            "host": settings.tws_host,
            "port": settings.tws_port,
            "client_id": settings.client_id,
            "connection_timeout": settings.connection_timeout,
            "reconnect_attempts": settings.reconnect_attempts,
            "reconnect_delay": settings.reconnect_delay,
        },
        "connection_status": {
            "connected": ib_service.is_connected(),
            "emergency_breaker": ib_service.get_emergency_breaker_status(),
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/debug/validation-rules", tags=["debug"])
async def get_validation_rules():
    """Get current validation rules for order creation."""
    return {
        "order_types": {
            "MARKET": {"code": "MKT", "requires_limit_price": False, "requires_aux_price": False},
            "LIMIT": {"code": "LMT", "requires_limit_price": True, "requires_aux_price": False},
            "STOP": {"code": "STP", "requires_limit_price": False, "requires_aux_price": True},
            "STOP_LIMIT": {"code": "STP LMT", "requires_limit_price": True, "requires_aux_price": True},
        },
        "validation_fixes": {
            "critical_bug_fixed": True,
            "pydantic_v2_migration": True,
            "enhanced_error_messages": True,
            "correlation_id_tracking": True,
        },
        "supported_security_types": ["STK", "OPT", "FUT", "CASH", "BOND", "CFD"],
        "supported_exchanges": ["SMART", "NYSE", "NASDAQ", "CBOE", "etc"],
        "supported_currencies": ["USD", "EUR", "GBP", "JPY", "CAD", "etc"],
        "supported_time_in_force": ["DAY", "GTC", "IOC", "FOK"],
        "validation_notes": {
            "symbol_normalization": "Symbols are automatically converted to uppercase",
            "quantity_validation": "Must be greater than 0",
            "price_validation": "Must be greater than or equal to 0",
            "emergency_breaker": "When active, all order creation is blocked"
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/debug/system-status", tags=["debug"])
async def get_system_status():
    """Get comprehensive system status for debugging and monitoring."""
    try:
        # Get account summary if connected
        account_info = None
        if ib_service.is_connected():
            try:
                account_info = await ib_service.get_account_summary()
            except Exception as e:
                account_info = {"error": f"Could not retrieve account info: {str(e)}"}
        
        return {
            "system_health": {
                "api_running": True,
                "tws_connected": ib_service.is_connected(),
                "emergency_breaker": ib_service.get_emergency_breaker_status(),
                "timestamp": datetime.now().isoformat(),
            },
            "connection_details": {
                "tws_host": settings.tws_host,
                "tws_port": settings.tws_port,
                "client_id": settings.client_id,
                "connection_timeout": settings.connection_timeout,
            },
            "api_metrics": {
                "version": settings.api_version,
                "debug_mode": settings.debug,
                "log_level": settings.log_level,
                "docs_url": settings.docs_url,
            },
            "account_status": account_info,
            "recent_fixes": {
                "validation_bugs_fixed": "Fixed critical enum/string comparison bugs in order validation",
                "pydantic_migration": "Migrated to Pydantic V2 for better validation",
                "enhanced_logging": "Added correlation IDs and structured error logging",
                "improved_debugging": "Enhanced error messages with actionable suggestions",
            }
        }
    except Exception as e:
        return {
            "system_health": {
                "api_running": True,
                "error": f"Error retrieving system status: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }
        }


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "build_date": "2025-09-15",
        "description": settings.api_description,
        "endpoints": {
            "documentation": settings.docs_url,
            "redoc": settings.redoc_url,
            "health": "/health",
            "orders": "/api/v1/orders",
            "all_orders": "/api/v1/orders/all",
            "positions": "/api/v1/positions",
            "account": "/api/v1/account"
        },
        "github": "https://github.com/tony-png/boursa"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level,
    )