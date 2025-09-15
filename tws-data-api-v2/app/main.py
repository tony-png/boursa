import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Path, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .models.stock_models import (
    StockPriceResponse, 
    ErrorResponse, 
    HealthResponse, 
    MarketSession
)
from .services.ib_client import get_ib_service, cleanup_ib_service, IBClientService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting TWS Data API...")
    
    try:
        # Test IB connection on startup
        ib_service = get_ib_service()
        connected = await ib_service.connect()
        if connected:
            logger.info("Successfully connected to TWS on startup")
        else:
            logger.warning("Could not connect to TWS on startup - will retry on first request")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TWS Data API...")
    await cleanup_ib_service()


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(ConnectionError)
async def connection_error_handler(request, exc: ConnectionError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error="TWS Connection Error",
            details=str(exc)
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            details="An unexpected error occurred"
        ).model_dump()
    )


# Dependency to get IB service
async def get_ib_client() -> IBClientService:
    return get_ib_service()


@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "description": settings.api_description,
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(ib_client: IBClientService = Depends(get_ib_client)):
    """Health check endpoint"""
    tws_connected = ib_client.is_connected()
    
    # Try to connect if not connected
    if not tws_connected:
        try:
            tws_connected = await ib_client.connect()
        except Exception as e:
            logger.warning(f"Health check - could not connect to TWS: {e}")
            tws_connected = False
    
    status = "healthy" if tws_connected else "degraded"
    
    return HealthResponse(
        status=status,
        timestamp=datetime.now(),
        tws_connected=tws_connected
    )


@app.get("/stock/{symbol}", response_model=StockPriceResponse, responses={
    404: {"model": ErrorResponse, "description": "Stock symbol not found"},
    503: {"model": ErrorResponse, "description": "TWS connection error"}
})
async def get_stock_price(
    symbol: str = Path(..., description="Stock symbol (e.g., AAPL, MSFT)", min_length=1, max_length=10),
    exchange: str = Query(default="SMART", description="Exchange to use (SMART, ISLAND, NYSE, NASDAQ, etc.)"),
    market_session: Optional[MarketSession] = Query(None, description="Filter by market session"),
    ib_client: IBClientService = Depends(get_ib_client)
):
    """
    Get real-time stock price data including bid, ask, and market session information.
    
    This endpoint provides comprehensive stock price data including:
    - Current bid and ask prices with sizes
    - Last traded price
    - Market session (pre-market, regular, post-market)
    - Exchange information
    - Calculated market price and spread
    
    The data includes both regular trading hours and extended hours (pre/post market) information.
    """
    try:
        # Get stock price data
        stock_data = await ib_client.get_stock_price(symbol.upper(), exchange)
        
        if not stock_data:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    error="Stock symbol not found",
                    details=f"Could not retrieve data for symbol: {symbol.upper()}"
                ).model_dump()
            )
        
        # Filter by market session if requested
        if market_session and stock_data.market_session != market_session:
            # Note: This is more of a metadata filter since we return current data
            # In a real implementation, you might want to store historical data
            pass
        
        return StockPriceResponse(
            success=True,
            data=stock_data,
            message="Stock price data retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stock price for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Failed to retrieve stock data",
                details=str(e)
            ).model_dump()
        )


@app.get("/stocks", response_model=dict)
async def get_multiple_stock_prices(
    symbols: str = Query(..., description="Comma-separated list of stock symbols (e.g., AAPL,MSFT,GOOGL)"),
    exchange: str = Query(default="SMART", description="Exchange to use (SMART, ISLAND, NYSE, NASDAQ, etc.)"),
    ib_client: IBClientService = Depends(get_ib_client)
):
    """
    Get real-time stock price data for multiple symbols.
    
    Returns a dictionary with symbol as key and StockPrice data as value.
    If a symbol cannot be found, its value will be null.
    """
    try:
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        
        if not symbol_list:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Invalid symbols parameter",
                    details="Please provide at least one valid symbol"
                ).model_dump()
            )
        
        if len(symbol_list) > 20:  # Limit to prevent abuse
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Too many symbols",
                    details="Maximum 20 symbols allowed per request"
                ).model_dump()
            )
        
        # Get data for all symbols
        results = await ib_client.get_multiple_stock_prices(symbol_list, exchange)
        
        # Format response
        response_data = {}
        for symbol, data in results.items():
            if data:
                response_data[symbol] = StockPriceResponse(
                    success=True,
                    data=data,
                    message="Stock price retrieved successfully"
                ).model_dump()
            else:
                response_data[symbol] = StockPriceResponse(
                    success=False,
                    data=None,
                    message=f"Could not retrieve data for {symbol}"
                ).model_dump()
        
        return {
            "success": True,
            "count": len(symbol_list),
            "data": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting multiple stock prices: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Failed to retrieve stock data",
                details=str(e)
            ).model_dump()
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower()
    )