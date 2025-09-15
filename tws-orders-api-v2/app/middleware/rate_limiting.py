import time
from typing import Callable
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Middleware to add rate limit headers to responses and provide
    additional rate limiting information.
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Add rate limit headers to all responses
                headers = dict(message.get("headers", []))
                
                # Try to get rate limit info from ib_service
                try:
                    from app.services.ib_service import ib_service
                    
                    if ib_service.rate_limiter:
                        status_data = await ib_service.rate_limiter.get_comprehensive_status()
                        msg_limit = status_data.get("message_rate_limit", {})
                        
                        # Add standard rate limit headers
                        headers[b"x-ratelimit-limit"] = str(msg_limit.get("max_tokens", 45)).encode()
                        headers[b"x-ratelimit-remaining"] = str(int(msg_limit.get("remaining_tokens", 0))).encode()
                        
                        # Add reset time
                        reset_time = msg_limit.get("reset_time", "")
                        if reset_time:
                            # Convert ISO timestamp to epoch seconds
                            try:
                                from datetime import datetime
                                dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
                                reset_timestamp = int(dt.timestamp())
                                headers[b"x-ratelimit-reset"] = str(reset_timestamp).encode()
                            except Exception:
                                pass
                        
                        # Add custom headers for order limits
                        active_orders = status_data.get("active_orders", {})
                        headers[b"x-ratelimit-orders-max"] = str(active_orders.get("max_per_contract", 18)).encode()
                        headers[b"x-ratelimit-orders-total"] = str(active_orders.get("total_tracked", 0)).encode()
                        
                        # Add rate limiting status
                        headers[b"x-ratelimit-enabled"] = b"true"
                    else:
                        headers[b"x-ratelimit-enabled"] = b"false"
                        
                except Exception as e:
                    logger.debug(f"Could not add rate limit headers: {e}")
                    headers[b"x-ratelimit-enabled"] = b"error"
                
                message["headers"] = [(k.encode() if isinstance(k, str) else k, v.encode() if isinstance(v, str) else v) 
                                    for k, v in headers.items()]
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


async def rate_limit_429_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Custom handler for 429 Too Many Requests responses with enhanced information.
    """
    try:
        from app.services.ib_service import ib_service
        
        retry_after = 1  # Default retry after 1 second
        
        if ib_service.rate_limiter:
            status_data = await ib_service.rate_limiter.get_comprehensive_status()
            msg_limit = status_data.get("message_rate_limit", {})
            
            # Calculate retry-after based on token refill rate
            remaining = msg_limit.get("remaining_tokens", 0)
            refill_rate = msg_limit.get("refill_rate", 45)
            
            if remaining < 1 and refill_rate > 0:
                retry_after = max(1, int((1 - remaining) / refill_rate))
        
        headers = {
            "Retry-After": str(retry_after),
            "X-RateLimit-Retry-After": str(retry_after)
        }
        
        content = {
            "error": True,
            "message": "Rate limit exceeded",
            "status_code": 429,
            "retry_after_seconds": retry_after,
            "timestamp": time.time()
        }
        
        return JSONResponse(
            status_code=429,
            content=content,
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Error in rate limit handler: {e}")
        return JSONResponse(
            status_code=429,
            content={
                "error": True,
                "message": "Rate limit exceeded",
                "status_code": 429,
                "timestamp": time.time()
            },
            headers={"Retry-After": "1"}
        )