import logging
import uuid
from typing import List, Optional
from datetime import datetime
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException, status, Depends, Request
from ib_insync import Order

from app.models.orders import (
    OrderRequest,
    OrderResponse,
    OrderModifyRequest,
    TradeResponse,
    PositionResponse,
    AccountSummaryResponse,
    ContractResponse,
    ErrorResponse,
)
from app.services.ib_service import ib_service
from app.utils.exceptions import IBConnectionError, OrderNotFoundError, ContractError


# Context variable for request correlation ID
request_id_ctx: ContextVar[str] = ContextVar('request_id', default='')

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())[:8]


def get_enhanced_error_context(request: Request, correlation_id: str, error: Exception, 
                             additional_context: dict = None) -> dict:
    """Create enhanced error context for better debugging."""
    context = {
        "correlation_id": correlation_id,
        "timestamp": datetime.now().isoformat(),
        "method": request.method,
        "url": str(request.url),
        "user_agent": request.headers.get("user-agent", "unknown"),
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    
    if additional_context:
        context.update(additional_context)
    
    return context


def log_error_with_context(error: Exception, context: dict, level: str = "error") -> None:
    """Log error with full context for debugging."""
    log_func = getattr(logger, level, logger.error)
    log_func(
        f"API Error [ID: {context['correlation_id']}] - "
        f"{context['error_type']}: {context['error_message']} | "
        f"Method: {context['method']} | URL: {context['url']} | "
        f"Additional: {context.get('additional_context', {})}"
    )


def create_enhanced_http_exception(
    status_code: int, 
    detail: str, 
    correlation_id: str,
    error_type: str = "APIError",
    suggestions: List[str] = None,
    debug_info: dict = None
) -> HTTPException:
    """Create enhanced HTTP exception with debugging information."""
    response_detail = {
        "error": True,
        "correlation_id": correlation_id,
        "timestamp": datetime.now().isoformat(),
        "error_type": error_type,
        "message": detail,
    }
    
    if suggestions:
        response_detail["suggestions"] = suggestions
    
    if debug_info:
        response_detail["debug_info"] = debug_info
    
    return HTTPException(status_code=status_code, detail=response_detail)


def convert_trade_to_response(trade) -> TradeResponse:
    """Convert ib_insync Trade object to TradeResponse."""
    order_response = OrderResponse(
        order_id=trade.order.orderId,
        client_id=trade.order.clientId,
        perm_id=trade.order.permId,
        action=trade.order.action,
        order_type=trade.order.orderType,
        total_quantity=trade.order.totalQuantity,
        cash_qty=trade.order.cashQty,
        limit_price=trade.order.lmtPrice,
        aux_price=trade.order.auxPrice,
        time_in_force=trade.order.tif,
        outside_rth=trade.order.outsideRth,
        hidden=trade.order.hidden,
        good_after_time=trade.order.goodAfterTime,
        good_till_date=trade.order.goodTillDate,
        status=trade.orderStatus.status if trade.orderStatus else "Unknown",
        filled=trade.orderStatus.filled if trade.orderStatus else 0.0,
        remaining=trade.orderStatus.remaining if trade.orderStatus else trade.order.totalQuantity,
        avg_fill_price=trade.orderStatus.avgFillPrice if trade.orderStatus else 0.0,
        last_fill_price=trade.orderStatus.lastFillPrice if trade.orderStatus else 0.0,
        why_held=trade.orderStatus.whyHeld if trade.orderStatus else None,
        contract=ContractResponse(
            symbol=trade.contract.symbol,
            sec_type=trade.contract.secType,
            exchange=trade.contract.exchange,
            currency=trade.contract.currency,
            local_symbol=trade.contract.localSymbol,
            trading_class=trade.contract.tradingClass,
            con_id=trade.contract.conId,
        ),
    )
    
    order_status_dict = {}
    if trade.orderStatus:
        order_status_dict = {
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "remaining": trade.orderStatus.remaining,
            "avgFillPrice": trade.orderStatus.avgFillPrice,
            "lastFillPrice": trade.orderStatus.lastFillPrice,
            "whyHeld": trade.orderStatus.whyHeld,
        }
    
    return TradeResponse(
        order=order_response,
        contract=ContractResponse(
            symbol=trade.contract.symbol,
            sec_type=trade.contract.secType,
            exchange=trade.contract.exchange,
            currency=trade.contract.currency,
            local_symbol=trade.contract.localSymbol,
            trading_class=trade.contract.tradingClass,
            con_id=trade.contract.conId,
        ),
        order_status=order_status_dict,
        fills=[{
            "execution": {
                "execId": fill.execution.execId,
                "time": fill.execution.time,
                "shares": fill.execution.shares,
                "price": fill.execution.price,
                "side": fill.execution.side,
            },
            "commissionReport": {
                "commission": fill.commissionReport.commission,
                "currency": fill.commissionReport.currency,
                "realizedPNL": fill.commissionReport.realizedPNL,
            } if fill.commissionReport else None
        } for fill in trade.fills],
        log=[{
            "time": log_entry.time,
            "status": log_entry.status,
            "message": log_entry.message,
        } for log_entry in trade.log],
    )


@router.post("/orders", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_order(order_request: OrderRequest, request: Request):
    """Create a new order with enhanced error handling and debugging."""
    # Generate correlation ID for request tracking
    correlation_id = generate_correlation_id()
    request_id_ctx.set(correlation_id)
    
    # Log order creation attempt
    logger.info(f"[{correlation_id}] Order creation request - Symbol: {order_request.contract.symbol}, "
               f"Type: {order_request.order_type}, Quantity: {order_request.total_quantity}, "
               f"Action: {order_request.action}")
    
    # Check emergency breaker first
    if ib_service.is_emergency_breaker_active():
        error_context = get_enhanced_error_context(
            request, correlation_id, Exception("Emergency breaker active"),
            {"breaker_status": ib_service.get_emergency_breaker_status()}
        )
        log_error_with_context(Exception("Emergency breaker active"), error_context, "warning")
        
        raise create_enhanced_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Order creation blocked: Emergency breaker is active.",
            correlation_id=correlation_id,
            error_type="EmergencyBreakerActive",
            suggestions=[
                "Contact administrator to check emergency breaker status",
                "Check system health status at /health endpoint",
                "Review recent system alerts or notifications"
            ]
        )
    
    try:
        # Create contract with detailed logging
        logger.info(f"[{correlation_id}] Creating contract for symbol: {order_request.contract.symbol}")
        contract = await ib_service.create_contract(
            symbol=order_request.contract.symbol,
            sec_type=order_request.contract.sec_type.value,
            exchange=order_request.contract.exchange,
            currency=order_request.contract.currency,
        )
        
        # Create order object
        logger.info(f"[{correlation_id}] Creating order object with type: {order_request.order_type}")
        order = Order(
            action=order_request.action.value,
            orderType=order_request.order_type.value,
            totalQuantity=order_request.total_quantity,
            lmtPrice=order_request.limit_price,
            auxPrice=order_request.aux_price,
            tif=order_request.time_in_force.value,
            outsideRth=order_request.outside_rth,
            hidden=order_request.hidden,
            goodAfterTime=order_request.good_after_time,
            goodTillDate=order_request.good_till_date,
        )
        
        # Place order with enhanced logging
        logger.info(f"[{correlation_id}] Placing order with TWS")
        trade = await ib_service.place_order(contract, order)
        
        logger.info(f"[{correlation_id}] Order successfully created - Order ID: {trade.order.orderId}")
        return convert_trade_to_response(trade)
        
    except ConnectionError as e:
        error_context = get_enhanced_error_context(
            request, correlation_id, e,
            {
                "tws_connected": ib_service.is_connected(),
                "order_details": {
                    "symbol": order_request.contract.symbol,
                    "order_type": order_request.order_type,
                    "quantity": order_request.total_quantity
                }
            }
        )
        log_error_with_context(e, error_context)
        
        raise create_enhanced_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"TWS connection error: {str(e)}",
            correlation_id=correlation_id,
            error_type="ConnectionError",
            suggestions=[
                "Check TWS/IB Gateway is running and accessible",
                "Verify network connectivity to TWS",
                "Check TWS connection settings in configuration",
                "Review TWS logs for connection issues"
            ],
            debug_info={"tws_connected": ib_service.is_connected()}
        )
        
    except ValueError as e:
        error_context = get_enhanced_error_context(
            request, correlation_id, e,
            {
                "contract_details": {
                    "symbol": order_request.contract.symbol,
                    "sec_type": order_request.contract.sec_type.value,
                    "exchange": order_request.contract.exchange,
                    "currency": order_request.contract.currency
                }
            }
        )
        log_error_with_context(e, error_context)
        
        raise create_enhanced_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid contract or order data: {str(e)}",
            correlation_id=correlation_id,
            error_type="ValidationError",
            suggestions=[
                "Verify symbol is correct and exists",
                "Check security type is valid for the symbol",
                "Ensure exchange and currency are correct",
                "Validate all required price fields are provided"
            ],
            debug_info={"contract": order_request.contract.dict()}
        )
        
    except Exception as e:
        error_context = get_enhanced_error_context(
            request, correlation_id, e,
            {
                "order_request": order_request.dict(),
                "emergency_breaker_status": ib_service.get_emergency_breaker_status(),
                "tws_connected": ib_service.is_connected()
            }
        )
        log_error_with_context(e, error_context)
        
        raise create_enhanced_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred while creating order",
            correlation_id=correlation_id,
            error_type="InternalError",
            suggestions=[
                "Check system logs for detailed error information",
                "Verify TWS connection status",
                "Review order parameters for validity",
                "Contact support if issue persists"
            ],
            debug_info={
                "original_error": str(e),
                "error_type": type(e).__name__
            }
        )


@router.get("/orders/all", response_model=List[TradeResponse])
async def get_all_orders():
    """Get all orders from all client IDs using reqAllOpenOrders."""
    try:
        trades = await ib_service.get_all_open_orders()
        return [convert_trade_to_response(trade) for trade in trades]
        
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting all orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve all orders"
        )


@router.delete("/orders/cancel-all", response_model=dict)
async def cancel_all_orders():
    """Cancel all open orders from all client IDs."""
    try:
        result = await ib_service.cancel_all_open_orders()
        return result
        
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error cancelling all orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel all orders"
        )


@router.get("/orders", response_model=List[TradeResponse])
async def get_orders():
    """Get all orders."""
    try:
        trades = await ib_service.get_orders()
        return [convert_trade_to_response(trade) for trade in trades]
        
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve orders"
        )


@router.get("/orders/{order_id}", response_model=TradeResponse)
async def get_order(order_id: int):
    """Get a specific order by ID."""
    try:
        trade = await ib_service.get_order(order_id)
        if not trade:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )
        
        return convert_trade_to_response(trade)
        
    except HTTPException:
        raise
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve order {order_id}"
        )


@router.put("/orders/{order_id}", response_model=dict)
async def modify_order(order_id: int, modify_request: OrderModifyRequest):
    """Modify an existing order."""
    try:
        # Prepare modifications
        modifications = {}
        if modify_request.total_quantity is not None:
            modifications['totalQuantity'] = modify_request.total_quantity
        if modify_request.limit_price is not None:
            modifications['lmtPrice'] = modify_request.limit_price
        if modify_request.aux_price is not None:
            modifications['auxPrice'] = modify_request.aux_price
        if modify_request.time_in_force is not None:
            modifications['tif'] = modify_request.time_in_force.value
        if modify_request.outside_rth is not None:
            modifications['outsideRth'] = modify_request.outside_rth
        if modify_request.hidden is not None:
            modifications['hidden'] = modify_request.hidden
        
        if not modifications:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No modifications provided"
            )
        
        success = await ib_service.modify_order(order_id, **modifications)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to modify order {order_id}"
            )
        
        return {"message": f"Order {order_id} modified successfully"}
        
    except HTTPException:
        raise
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except ValueError as e:
        logger.error(f"Order not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error modifying order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to modify order {order_id}"
        )


@router.delete("/orders/{order_id}", response_model=dict)
async def cancel_order(order_id: int):
    """Cancel an order."""
    try:
        success = await ib_service.cancel_order(order_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to cancel order {order_id}"
            )
        
        return {"message": f"Order {order_id} cancellation requested"}
        
    except HTTPException:
        raise
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error cancelling order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order {order_id}"
        )


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions():
    """Get all positions."""
    try:
        positions = await ib_service.get_positions()
        return [
            PositionResponse(
                account=pos.account,
                contract=ContractResponse(
                    symbol=pos.contract.symbol,
                    sec_type=pos.contract.secType,
                    exchange=pos.contract.exchange,
                    currency=pos.contract.currency,
                    local_symbol=pos.contract.localSymbol,
                    trading_class=pos.contract.tradingClass,
                    con_id=pos.contract.conId,
                ),
                position=pos.position,
                avg_cost=pos.avgCost,
            )
            for pos in positions
        ]
        
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )


@router.get("/account", response_model=AccountSummaryResponse)
async def get_account_summary():
    """Get account summary."""
    try:
        summary = await ib_service.get_account_summary()
        return AccountSummaryResponse(account_values=summary)
        
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting account summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve account summary"
        )


# Emergency Breaker Endpoints
@router.post("/emergency/breaker/trigger", response_model=dict, tags=["emergency"])
async def trigger_emergency_breaker(reason: Optional[str] = None):
    """Trigger the emergency breaker to stop all new order creation."""
    try:
        trigger_reason = reason or "Manual trigger via API"
        result = ib_service.trigger_emergency_breaker(reason=trigger_reason)
        logger.critical(f"Emergency breaker triggered via API: {trigger_reason}")
        return result
        
    except Exception as e:
        logger.error(f"Error triggering emergency breaker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger emergency breaker"
        )


@router.post("/emergency/breaker/reset", response_model=dict, tags=["emergency"])
async def reset_emergency_breaker():
    """Reset the emergency breaker to allow order creation."""
    try:
        result = ib_service.reset_emergency_breaker()
        logger.warning("Emergency breaker reset via API")
        return result
        
    except Exception as e:
        logger.error(f"Error resetting emergency breaker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset emergency breaker"
        )


@router.get("/emergency/breaker/status", response_model=dict, tags=["emergency"])
async def get_emergency_breaker_status():
    """Get current emergency breaker status."""
    try:
        return ib_service.get_emergency_breaker_status()
        
    except Exception as e:
        logger.error(f"Error getting emergency breaker status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get emergency breaker status"
        )


@router.post("/emergency/breaker/test", response_model=dict, tags=["emergency"])
async def test_emergency_breaker():
    """Test emergency breaker by attempting to create a test order (should fail if breaker is active)."""
    try:
        if ib_service.is_emergency_breaker_active():
            return {
                "test": "PASSED",
                "message": "Emergency breaker is active - order creation correctly blocked",
                "breaker_active": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "test": "WARNING", 
                "message": "Emergency breaker is NOT active - order creation would be allowed",
                "breaker_active": False,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error testing emergency breaker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test emergency breaker"
        )


# Rate Limiting Monitoring Endpoints
@router.get("/rate-limits/status", response_model=dict, tags=["rate-limits"])
async def get_rate_limit_status():
    """Get comprehensive rate limit status and usage metrics."""
    try:
        status_data = await ib_service.get_rate_limit_status()
        return status_data
        
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rate limit status"
        )


@router.get("/rate-limits/health", response_model=dict, tags=["rate-limits"])
async def get_rate_limit_health():
    """Get rate limit health check - simplified status for monitoring."""
    try:
        status_data = await ib_service.get_rate_limit_status()
        
        if not status_data.get("enabled", False):
            return {
                "status": "disabled",
                "message": "Rate limiting is disabled",
                "healthy": True
            }
        
        msg_rate = status_data.get("message_rate_limit", {})
        remaining_tokens = msg_rate.get("remaining_tokens", 0)
        max_tokens = msg_rate.get("max_tokens", 45)
        
        # Consider healthy if we have at least 20% of tokens available
        token_health = remaining_tokens >= (max_tokens * 0.2)
        
        active_orders = status_data.get("active_orders", {})
        total_active = active_orders.get("total_tracked", 0)
        max_per_contract = active_orders.get("max_per_contract", 18)
        
        # Simple health check for active orders
        order_health = total_active < (max_per_contract * 10)  # Rough estimate
        
        overall_healthy = token_health and order_health
        
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "message": "Rate limits within acceptable ranges" if overall_healthy else "Rate limits approaching limits",
            "healthy": overall_healthy,
            "metrics": {
                "token_utilization_percent": ((max_tokens - remaining_tokens) / max_tokens) * 100,
                "total_active_orders": total_active,
                "remaining_tokens": remaining_tokens
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting rate limit health: {e}")
        return {
            "status": "error",
            "message": f"Error checking rate limit health: {str(e)}",
            "healthy": False
        }


@router.post("/rate-limits/test", response_model=dict, tags=["rate-limits"])
async def test_rate_limits():
    """Test rate limiting by attempting to acquire tokens."""
    try:
        status_data = await ib_service.get_rate_limit_status()
        
        if not status_data.get("enabled", False):
            return {
                "test": "SKIPPED",
                "message": "Rate limiting is disabled",
                "timestamp": datetime.now().isoformat()
            }
        
        # Try to acquire a token
        if ib_service.rate_limiter:
            acquired = await ib_service.rate_limiter.acquire_message_token(timeout=1.0)
            
            return {
                "test": "PASSED" if acquired else "LIMITED",
                "message": "Successfully acquired rate limit token" if acquired else "Rate limit active - token not available",
                "token_acquired": acquired,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "test": "ERROR",
                "message": "Rate limiter not initialized",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error testing rate limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test rate limits"
        )