from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MarketSession(str, Enum):
    """Market session types"""
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    POST_MARKET = "post_market"
    EXTENDED = "extended"  # Covers both pre and post market


class StockRequest(BaseModel):
    """Request model for stock price queries"""
    symbol: str = Field(..., min_length=1, max_length=10, description="Stock symbol (e.g., AAPL, MSFT)")
    exchange: str = Field(default="SMART", description="Exchange to use (SMART, ISLAND, NYSE, NASDAQ, etc.)")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "exchange": "SMART"
                }
            ]
        }
    }


class StockPrice(BaseModel):
    """Stock price data model"""
    symbol: str = Field(..., description="Stock symbol")
    timestamp: datetime = Field(..., description="Price timestamp")
    bid: Optional[float] = Field(None, description="Current bid price")
    ask: Optional[float] = Field(None, description="Current ask price")
    bid_size: Optional[int] = Field(None, description="Bid size")
    ask_size: Optional[int] = Field(None, description="Ask size")
    last_price: Optional[float] = Field(None, description="Last traded price")
    market_session: MarketSession = Field(..., description="Market session type")
    exchange: Optional[str] = Field(None, description="Exchange where the price is from")
    market_price: Optional[float] = Field(None, description="Calculated market price")
    spread: Optional[float] = Field(None, description="Bid-ask spread")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "bid": 150.25,
                    "ask": 150.27,
                    "bid_size": 100,
                    "ask_size": 200,
                    "last_price": 150.26,
                    "market_session": "regular",
                    "exchange": "NASDAQ",
                    "market_price": 150.26,
                    "spread": 0.02
                }
            ]
        }
    }


class StockPriceResponse(BaseModel):
    """Response model for stock price API"""
    success: bool = Field(True, description="Request success status")
    data: StockPrice = Field(..., description="Stock price data")
    message: Optional[str] = Field(None, description="Additional information or error message")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "data": {
                        "symbol": "AAPL",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "bid": 150.25,
                        "ask": 150.27,
                        "bid_size": 100,
                        "ask_size": 200,
                        "last_price": 150.26,
                        "market_session": "regular",
                        "exchange": "NASDAQ",
                        "market_price": 150.26,
                        "spread": 0.02
                    },
                    "message": "Price data retrieved successfully"
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = Field(False, description="Request success status")
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": False,
                    "error": "Symbol not found",
                    "details": "The requested stock symbol could not be found or is invalid"
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    tws_connected: bool = Field(..., description="TWS connection status")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "tws_connected": True
                }
            ]
        }
    }