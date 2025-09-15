import asyncio
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitStatus:
    """Status information for rate limiting."""
    remaining_tokens: float
    reset_time: datetime
    queue_size: int
    is_limited: bool


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for controlling TWS API message rate.
    
    Implements a token bucket algorithm to ensure we don't exceed the
    TWS API limit of 50 messages per second.
    """
    
    def __init__(self, max_tokens: int = 45, refill_rate: float = 45.0):
        """
        Initialize the rate limiter.
        
        Args:
            max_tokens: Maximum tokens in bucket (default: 45 for safety margin)
            refill_rate: Rate at which tokens are refilled per second (default: 45/sec)
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = float(max_tokens)
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
        
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_refill
            
            # Refill tokens based on time passed
            self.tokens = min(
                self.max_tokens,
                self.tokens + (time_passed * self.refill_rate)
            )
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    async def wait_for_tokens(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """
        Wait until tokens are available, with timeout.
        
        Args:
            tokens: Number of tokens needed
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if tokens were acquired, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.acquire(tokens):
                return True
            
            # Calculate how long to wait for next token
            async with self._lock:
                if self.tokens < tokens:
                    needed_tokens = tokens - self.tokens
                    wait_time = min(needed_tokens / self.refill_rate, 0.1)
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(0.01)
        
        return False
    
    async def get_status(self) -> RateLimitStatus:
        """Get current rate limiter status."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_refill
            
            # Calculate current tokens (without modifying state)
            current_tokens = min(
                self.max_tokens,
                self.tokens + (time_passed * self.refill_rate)
            )
            
            # Calculate when bucket will be full
            if current_tokens >= self.max_tokens:
                reset_time = datetime.now()
            else:
                tokens_to_full = self.max_tokens - current_tokens
                seconds_to_full = tokens_to_full / self.refill_rate
                reset_time = datetime.now() + timedelta(seconds=seconds_to_full)
            
            return RateLimitStatus(
                remaining_tokens=current_tokens,
                reset_time=reset_time,
                queue_size=0,  # Simple rate limiter doesn't have queue
                is_limited=current_tokens < 1
            )


class ActiveOrderTracker:
    """
    Tracks active orders per contract/side/account to enforce the 
    20 orders per contract per side per account limit.
    """
    
    def __init__(self, max_orders_per_contract: int = 18):
        """
        Initialize the active order tracker.
        
        Args:
            max_orders_per_contract: Maximum orders per contract/side/account (default: 18 for safety)
        """
        self.max_orders_per_contract = max_orders_per_contract
        self._active_orders: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    def _get_key(self, symbol: str, action: str, account: str = "default") -> str:
        """Generate key for tracking orders by contract/side/account."""
        return f"{symbol}:{action.upper()}:{account}"
    
    async def can_place_order(self, symbol: str, action: str, account: str = "default") -> bool:
        """
        Check if we can place another order for this contract/side/account.
        
        Args:
            symbol: Contract symbol
            action: Order action (BUY/SELL)
            account: Account identifier
            
        Returns:
            True if order can be placed, False otherwise
        """
        key = self._get_key(symbol, action, account)
        
        async with self._lock:
            current_count = self._active_orders.get(key, 0)
            return current_count < self.max_orders_per_contract
    
    async def add_order(self, symbol: str, action: str, account: str = "default") -> bool:
        """
        Add an order to the tracking system.
        
        Args:
            symbol: Contract symbol
            action: Order action (BUY/SELL)
            account: Account identifier
            
        Returns:
            True if order was added, False if limit would be exceeded
        """
        key = self._get_key(symbol, action, account)
        
        async with self._lock:
            current_count = self._active_orders.get(key, 0)
            
            if current_count >= self.max_orders_per_contract:
                logger.warning(
                    f"Cannot add order: {current_count} active orders for {key} "
                    f"(limit: {self.max_orders_per_contract})"
                )
                return False
            
            self._active_orders[key] = current_count + 1
            logger.debug(f"Added order for {key}: {current_count + 1}/{self.max_orders_per_contract}")
            return True
    
    async def remove_order(self, symbol: str, action: str, account: str = "default"):
        """
        Remove an order from tracking when it's cancelled or filled.
        
        Args:
            symbol: Contract symbol
            action: Order action (BUY/SELL)  
            account: Account identifier
        """
        key = self._get_key(symbol, action, account)
        
        async with self._lock:
            current_count = self._active_orders.get(key, 0)
            if current_count > 0:
                self._active_orders[key] = current_count - 1
                logger.debug(f"Removed order for {key}: {current_count - 1}/{self.max_orders_per_contract}")
                
                # Clean up zero counts
                if self._active_orders[key] == 0:
                    del self._active_orders[key]
    
    async def get_active_count(self, symbol: str, action: str, account: str = "default") -> int:
        """Get current active order count for contract/side/account."""
        key = self._get_key(symbol, action, account)
        async with self._lock:
            return self._active_orders.get(key, 0)
    
    async def get_all_counts(self) -> Dict[str, int]:
        """Get all active order counts."""
        async with self._lock:
            return self._active_orders.copy()


class TWSRateLimiter:
    """
    Main rate limiter that combines token bucket and active order tracking
    to ensure compliance with all TWS API limits.
    """
    
    def __init__(self, 
                 message_rate_limit: int = 45,
                 max_orders_per_contract: int = 18,
                 queue_size: int = 100):
        """
        Initialize the TWS rate limiter.
        
        Args:
            message_rate_limit: Messages per second limit (default: 45)
            max_orders_per_contract: Max orders per contract/side/account (default: 18)
            queue_size: Maximum queued operations (default: 100)
        """
        self.token_bucket = TokenBucketRateLimiter(
            max_tokens=message_rate_limit,
            refill_rate=float(message_rate_limit)
        )
        self.order_tracker = ActiveOrderTracker(max_orders_per_contract)
        self.queue_size = queue_size
        self._operation_queue = asyncio.Queue(maxsize=queue_size)
        self._processing_queue = False
        self._queue_lock = asyncio.Lock()
        
    async def can_place_order(self, symbol: str, action: str, account: str = "default") -> Tuple[bool, str]:
        """
        Check if an order can be placed considering all limits.
        
        Returns:
            (can_place, reason) - True/False and reason if blocked
        """
        # Check active order limit
        if not await self.order_tracker.can_place_order(symbol, action, account):
            active_count = await self.order_tracker.get_active_count(symbol, action, account)
            return False, f"Too many active orders for {symbol} {action}: {active_count}/{self.order_tracker.max_orders_per_contract}"
        
        # Check token bucket
        if not await self.token_bucket.acquire(1):
            status = await self.token_bucket.get_status()
            return False, f"Rate limit exceeded. Tokens: {status.remaining_tokens:.1f}, Reset: {status.reset_time}"
        
        return True, "OK"
    
    async def place_order_with_rate_limit(self, symbol: str, action: str, account: str = "default") -> bool:
        """
        Place an order with rate limiting. Will wait for tokens if needed.
        
        Returns:
            True if order can proceed, False if rejected
        """
        # Check active order limit first (non-waiting check)
        if not await self.order_tracker.can_place_order(symbol, action, account):
            return False
        
        # Wait for tokens (up to 30 seconds)
        if not await self.token_bucket.wait_for_tokens(1, timeout=30.0):
            return False
        
        # Add to order tracker
        if await self.order_tracker.add_order(symbol, action, account):
            return True
        
        return False
    
    async def order_completed(self, symbol: str, action: str, account: str = "default"):
        """Mark an order as completed (filled or cancelled) to free up the slot."""
        await self.order_tracker.remove_order(symbol, action, account)
    
    async def acquire_message_token(self, timeout: float = 30.0) -> bool:
        """
        Acquire a token for sending a message to TWS.
        
        Args:
            timeout: Maximum time to wait for token
            
        Returns:
            True if token acquired, False if timeout
        """
        return await self.token_bucket.wait_for_tokens(1, timeout)
    
    async def get_comprehensive_status(self) -> Dict:
        """Get comprehensive status of all rate limiters."""
        token_status = await self.token_bucket.get_status()
        active_orders = await self.order_tracker.get_all_counts()
        
        return {
            "message_rate_limit": {
                "remaining_tokens": token_status.remaining_tokens,
                "max_tokens": self.token_bucket.max_tokens,
                "refill_rate": self.token_bucket.refill_rate,
                "reset_time": token_status.reset_time.isoformat(),
                "is_limited": token_status.is_limited
            },
            "active_orders": {
                "per_contract": active_orders,
                "max_per_contract": self.order_tracker.max_orders_per_contract,
                "total_tracked": sum(active_orders.values())
            },
            "queue_status": {
                "current_size": self._operation_queue.qsize(),
                "max_size": self.queue_size
            },
            "timestamp": datetime.now().isoformat()
        }