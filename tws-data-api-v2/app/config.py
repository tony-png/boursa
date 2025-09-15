import logging
from datetime import time
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class TWSConfig(BaseModel):
    """TWS Connection Configuration"""
    host: str = Field(default="localhost", description="TWS host address")
    port: int = Field(default=7497, description="TWS port number")
    client_id: int = Field(default=1, description="TWS client ID")
    timeout: int = Field(default=10, description="Connection timeout in seconds")


class MarketHours(BaseModel):
    """Market hours configuration"""
    pre_market_start: time = Field(default=time(4, 0), description="Pre-market start time (EST)")
    regular_market_start: time = Field(default=time(9, 30), description="Regular market start time (EST)")
    regular_market_end: time = Field(default=time(16, 0), description="Regular market end time (EST)")
    post_market_end: time = Field(default=time(20, 0), description="Post-market end time (EST)")




class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", env="API_HOST", description="API host")
    api_port: int = Field(default=8000, env="API_PORT", description="API port")
    
    # TWS Configuration
    tws_host: str = Field(default="localhost", env="TWS_HOST", description="TWS host")
    tws_port: int = Field(default=7497, env="TWS_PORT", description="TWS port")
    tws_client_id: int = Field(default=1, env="TWS_CLIENT_ID", description="TWS client ID")
    
    # Market Data Configuration
    market_data_type: int = Field(default=1, description="Market data type: 1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen")
    
    # API Configuration
    api_title: str = Field(default="TWS Stock Data API", description="API title")
    api_version: str = Field(default="1.0.0", description="API version")
    api_description: str = Field(
        default="FastAPI application for retrieving real-time stock prices from Interactive Brokers TWS",
        description="API description"
    )
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    
    # CORS Configuration
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @property
    def tws_config(self) -> TWSConfig:
        """Get TWS configuration"""
        return TWSConfig(
            host=self.tws_host,
            port=self.tws_port,
            client_id=self.tws_client_id
        )
    
    @property
    def market_hours(self) -> MarketHours:
        """Get market hours configuration"""
        return MarketHours()
    
    
    def setup_logging(self) -> None:
        """Setup logging configuration"""
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
            ]
        )
        
        # Set specific loggers
        logging.getLogger("ib_insync").setLevel(log_level)
        logging.getLogger("fastapi").setLevel(log_level)
        logging.getLogger("uvicorn").setLevel(log_level)


# Global settings instance
settings = Settings()

# Setup logging when module is imported
settings.setup_logging()