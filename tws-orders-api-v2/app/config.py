from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # FastAPI Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    debug: bool = True
    log_level: str = "info"
    
    # Interactive Brokers TWS Configuration
    tws_host: str = "localhost"
    tws_port: int = 7497
    client_id: int = 1
    
    # API Configuration
    api_title: str = "TWS Orders API v2"
    api_description: str = "Interactive Brokers TWS Order Management API"
    api_version: str = "1.0.1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    
    # Connection Settings
    connection_timeout: int = 10
    reconnect_attempts: int = 3
    reconnect_delay: int = 5

    # Order Acknowledgment Settings
    order_acknowledgment_timeout: float = 2.0  # seconds to wait for TWS order acknowledgment
    order_cancellation_timeout: float = 0.5    # seconds to wait for cancellation confirmation
    
    # Rate Limiting Settings
    enable_rate_limiting: bool = True
    tws_message_rate_limit: int = 45  # Messages per second (safety margin from 50)
    max_orders_per_contract: int = 18  # Max orders per contract/side/account (safety margin from 20)
    rate_limit_queue_size: int = 100  # Maximum queued operations
    rate_limit_timeout: float = 30.0  # Maximum wait time for rate limit tokens (seconds)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()