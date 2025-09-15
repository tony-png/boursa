import logging
from datetime import datetime, time
from typing import Optional
import asyncio
from ib_insync import IB, Stock, Ticker, Contract
from ib_insync.util import startLoop

from ..config import Settings, TWSConfig, MarketHours
from ..models.stock_models import StockPrice, MarketSession


logger = logging.getLogger(__name__)


class IBClientService:
    """Interactive Brokers client service for stock data retrieval"""
    
    def __init__(self, config: TWSConfig, market_hours: MarketHours, market_data_type: int = 1):
        self.config = config
        self.market_hours = market_hours
        self.market_data_type = market_data_type
        self.ib: Optional[IB] = None
        self._connection_lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """Connect to TWS/Gateway"""
        async with self._connection_lock:
            if self.ib and self.ib.isConnected():
                return True
            
            try:
                if not self.ib:
                    self.ib = IB()
                
                # Connect to TWS
                await self.ib.connectAsync(
                    host=self.config.host,
                    port=self.config.port,
                    clientId=self.config.client_id,
                    timeout=self.config.timeout
                )
                
                # Set market data type after connection
                self.ib.reqMarketDataType(self.market_data_type)
                logger.info(f"Connected to TWS at {self.config.host}:{self.config.port}, market data type set to {self.market_data_type}")
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to TWS: {e}")
                self.ib = None
                return False
    
    async def disconnect(self):
        """Disconnect from TWS"""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from TWS")
    
    def is_connected(self) -> bool:
        """Check if connected to TWS"""
        return self.ib is not None and self.ib.isConnected()
    
    def _determine_market_session(self, current_time: Optional[datetime] = None) -> MarketSession:
        """Determine current market session based on time"""
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Market hours in EST (assuming current_time is in local timezone)
        if (self.market_hours.pre_market_start <= current_time_only < 
            self.market_hours.regular_market_start):
            return MarketSession.PRE_MARKET
        elif (self.market_hours.regular_market_start <= current_time_only <= 
              self.market_hours.regular_market_end):
            return MarketSession.REGULAR
        elif (self.market_hours.regular_market_end < current_time_only <= 
              self.market_hours.post_market_end):
            return MarketSession.POST_MARKET
        else:
            return MarketSession.EXTENDED
    
    def _is_market_open(self, current_time: Optional[datetime] = None) -> bool:
        """Check if regular market is currently open"""
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        return (self.market_hours.regular_market_start <= current_time_only <= 
                self.market_hours.regular_market_end)
    
    def _get_optimal_market_data_type(self, current_time: Optional[datetime] = None) -> int:
        """Get optimal market data type based on current time and market hours"""
        if self._is_market_open(current_time):
            # During market hours, use LIVE data (Type 1)
            return 1
        else:
            # Outside market hours, use FROZEN data (Type 2) to get last available quotes
            return 2
    
    def _calculate_spread(self, bid: Optional[float], ask: Optional[float]) -> Optional[float]:
        """Calculate bid-ask spread"""
        if bid is not None and ask is not None:
            return round(ask - bid, 4)
        return None
    
    async def get_stock_price(self, symbol: str, exchange: str = 'SMART') -> Optional[StockPrice]:
        """Get stock price data with smart market data type switching"""
        if not await self.connect():
            raise ConnectionError("Failed to connect to TWS")
        
        ticker = None
        contract = None
        
        try:
            # Create stock contract with specified exchange
            contract = Stock(symbol, exchange, 'USD')
            
            # Qualify the contract to get full details
            qualified_contracts = await self.ib.qualifyContractsAsync(contract)
            if not qualified_contracts:
                logger.warning(f"Could not qualify contract for symbol: {symbol} on exchange: {exchange}")
                return None
            
            contract = qualified_contracts[0]
            
            # Determine current time and optimal market data type
            current_time = datetime.now()
            optimal_data_type = self._get_optimal_market_data_type(current_time)
            
            # Set optimal market data type
            self.ib.reqMarketDataType(optimal_data_type)
            logger.debug(f"Using market data type {optimal_data_type} for {symbol}")
            
            # Use legal generic ticks for stocks
            # 233=Time&Sales (RTVolume), 293=TradeCount, 294=TradeRate, 295=VolumeRate
            # For stocks, bid/ask/last are provided by default, we just need extended data
            generic_ticks = '233'
            
            # Request streaming market data
            ticker = self.ib.reqMktData(contract, generic_ticks, snapshot=False, regulatorySnapshot=False)
            
            # Wait for data to arrive, with retry mechanism like trading-capo
            await asyncio.sleep(0.5)
            
            # Check if we have ticker data
            if not ticker:
                logger.warning(f"No ticker data received for symbol: {symbol}")
                return None
            
            # Determine market session
            market_session = self._determine_market_session(current_time)
            
            # Extract bid/ask data with validation like trading-capo
            bid = ticker.bid if ticker.bid and not (ticker.bid != ticker.bid) and ticker.bid > 0 else None
            ask = ticker.ask if ticker.ask and not (ticker.ask != ticker.ask) and ticker.ask > 0 else None
            bid_size = int(ticker.bidSize) if ticker.bidSize and ticker.bidSize > 0 else None
            ask_size = int(ticker.askSize) if ticker.askSize and ticker.askSize > 0 else None
            last_price = ticker.last if ticker.last and not (ticker.last != ticker.last) else None
            close_price = ticker.close if ticker.close and not (ticker.close != ticker.close) else None
            
            # If no bid/ask after first attempt, wait and retry like trading-capo
            if (bid is None or ask is None) and last_price is None:
                await asyncio.sleep(1)
                bid = ticker.bid if ticker.bid and not (ticker.bid != ticker.bid) and ticker.bid > 0 else None
                ask = ticker.ask if ticker.ask and not (ticker.ask != ticker.ask) and ticker.ask > 0 else None
                last_price = ticker.last if ticker.last and not (ticker.last != ticker.last) else None
                close_price = ticker.close if ticker.close and not (ticker.close != ticker.close) else None
            
            # Market price calculation with fallback like trading-capo
            market_price = None
            if bid is not None and ask is not None:
                market_price = (bid + ask) / 2
            elif last_price is not None:
                market_price = last_price
            elif close_price is not None:
                market_price = close_price
            
            # Calculate spread
            spread = self._calculate_spread(bid, ask)
            
            # Use the originally requested exchange, not the contract's resolved exchange
            # This preserves the user's intent (e.g., "SMART" should stay "SMART")
            exchange_info = exchange
            
            return StockPrice(
                symbol=symbol.upper(),
                timestamp=current_time,
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last_price=last_price,
                market_session=market_session,
                exchange=exchange_info,
                market_price=market_price,
                spread=spread
            )
            
        except Exception as e:
            logger.error(f"Error getting stock price for {symbol}: {e}")
            return None
        
        finally:
            # Cancel market data request
            if ticker and contract:
                try:
                    self.ib.cancelMktData(contract)
                except Exception as e:
                    logger.debug(f"Error canceling market data for {symbol}: {e}")
    
    async def get_multiple_stock_prices(self, symbols: list[str], exchange: str = 'SMART') -> dict[str, Optional[StockPrice]]:
        """Get stock prices for multiple symbols"""
        if not await self.connect():
            raise ConnectionError("Failed to connect to TWS")
        
        results = {}
        
        # Process symbols concurrently (but limit concurrency to avoid overwhelming TWS)
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
        
        async def get_single_price(symbol: str):
            async with semaphore:
                try:
                    price_data = await self.get_stock_price(symbol, exchange)
                    results[symbol] = price_data
                except Exception as e:
                    logger.error(f"Error getting price for {symbol}: {e}")
                    results[symbol] = None
        
        # Create tasks for all symbols
        tasks = [get_single_price(symbol) for symbol in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results


# Global service instance
_ib_service: Optional[IBClientService] = None


def get_ib_service() -> IBClientService:
    """Get or create IB service instance"""
    global _ib_service
    if _ib_service is None:
        from ..config import settings
        _ib_service = IBClientService(settings.tws_config, settings.market_hours, settings.market_data_type)
    return _ib_service


async def cleanup_ib_service():
    """Cleanup IB service on shutdown"""
    global _ib_service
    if _ib_service:
        await _ib_service.disconnect()
        _ib_service = None