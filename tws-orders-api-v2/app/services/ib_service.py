import asyncio
import logging
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from ib_insync import IB, Contract, Order, Trade, Position, util

from app.config import settings
from app.utils.rate_limiter import TWSRateLimiter


logger = logging.getLogger(__name__)


class IBService:
    """Service class for managing Interactive Brokers TWS connection and operations."""
    
    def __init__(self):
        self.ib = IB()
        self._is_connected = False
        self._connection_lock = asyncio.Lock()
        self._emergency_breaker_file = Path("emergency_breaker.json")
        self._emergency_breaker_active = False
        self._load_breaker_state()
        
        # Initialize rate limiter if enabled
        self.rate_limiter = None
        if settings.enable_rate_limiting:
            self.rate_limiter = TWSRateLimiter(
                message_rate_limit=settings.tws_message_rate_limit,
                max_orders_per_contract=settings.max_orders_per_contract,
                queue_size=settings.rate_limit_queue_size
            )
            logger.info(f"Rate limiting enabled: {settings.tws_message_rate_limit} msg/sec, "
                       f"{settings.max_orders_per_contract} orders/contract")
        
    async def connect(self) -> bool:
        """Connect to TWS/IB Gateway."""
        async with self._connection_lock:
            if self._is_connected:
                return True
                
            # Try connecting with the configured client ID first
            client_ids_to_try = [settings.client_id]
            
            # If the configured client ID fails, try alternatives
            if settings.client_id != 0:
                client_ids_to_try.extend([0, 12, 13, 14, 15])
            else:
                client_ids_to_try.extend([12, 13, 14, 15])
                
            for client_id in client_ids_to_try:
                try:
                    if client_id != settings.client_id:
                        logger.info(f"Trying alternative client ID {client_id}")
                    
                    logger.info(f"Connecting to TWS at {settings.tws_host}:{settings.tws_port} with client ID {client_id}")
                    await self.ib.connectAsync(
                        host=settings.tws_host,
                        port=settings.tws_port,
                        clientId=client_id,
                        timeout=settings.connection_timeout
                    )
                    self._is_connected = True
                    logger.info(f"Successfully connected to TWS with client ID {client_id}")
                    
                    # Set up event handlers
                    self.ib.orderStatusEvent += self._on_order_status
                    self.ib.execDetailsEvent += self._on_execution
                    self.ib.disconnectedEvent += self._on_disconnected
                    self.ib.connectedEvent += self._on_connected
                    
                    return True
                    
                except Exception as e:
                    logger.warning(f"Failed to connect with client ID {client_id}: {e}")
                    self._is_connected = False
                    # Try the next client ID
                    continue
            
            # If all client IDs failed
            logger.error("Failed to connect to TWS with any available client ID")
            return False
    
    async def disconnect(self):
        """Disconnect from TWS/IB Gateway."""
        async with self._connection_lock:
            if self._is_connected:
                try:
                    self.ib.disconnect()
                    self._is_connected = False
                    logger.info("Disconnected from TWS")
                except Exception as e:
                    logger.error(f"Error during disconnect: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to TWS."""
        # Check if ib_insync connection is actually active
        ib_connected = self.ib.isConnected()
        
        # Sync internal state with ib_insync state if they differ
        if self._is_connected != ib_connected:
            if ib_connected:
                logger.info("TWS connection state synchronized - connected")
            else:
                logger.warning("TWS connection state synchronized - disconnected")
            self._is_connected = ib_connected
        
        return self._is_connected
    
    async def ensure_connected(self):
        """Ensure connection to TWS, attempt to reconnect if needed."""
        if not self.is_connected():
            for attempt in range(settings.reconnect_attempts):
                logger.info(f"Reconnection attempt {attempt + 1}/{settings.reconnect_attempts}")
                if await self.connect():
                    return
                await asyncio.sleep(settings.reconnect_delay)
            raise ConnectionError("Failed to establish connection to TWS after multiple attempts")
    
    async def create_contract(self, symbol: str, sec_type: str = "STK", 
                            exchange: str = "SMART", currency: str = "USD") -> Contract:
        """Create a contract object."""
        contract = Contract(
            symbol=symbol,
            secType=sec_type,
            exchange=exchange,
            currency=currency
        )
        
        # Apply rate limiting for contract qualification (it's a TWS message)
        if self.rate_limiter:
            if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                raise ConnectionError("Rate limit exceeded for contract qualification")
        
        # Qualify the contract
        await self.ensure_connected()
        qualified_contracts = await self.ib.qualifyContractsAsync(contract)
        
        if not qualified_contracts:
            raise ValueError(f"Could not qualify contract for {symbol}")
        
        return qualified_contracts[0]
    
    async def place_order(self, contract: Contract, order: Order) -> Trade:
        """Place an order and return the trade object."""
        await self.ensure_connected()
        
        # Apply rate limiting for order placement
        if self.rate_limiter:
            # Check both message rate limit and active orders per contract
            success = await self.rate_limiter.place_order_with_rate_limit(
                symbol=contract.symbol,
                action=order.action,
                account=getattr(order, 'account', 'default')
            )
            if not success:
                status = await self.rate_limiter.get_comprehensive_status()
                raise ConnectionError(
                    f"Rate limit exceeded for order placement. "
                    f"Tokens: {status['message_rate_limit']['remaining_tokens']:.1f}, "
                    f"Active orders for {contract.symbol} {order.action}: "
                    f"{status['active_orders']['per_contract'].get(f'{contract.symbol}:{order.action}:default', 0)}"
                )
        
        try:
            trade = self.ib.placeOrder(contract, order)
            logger.info(f"Order placed: {order.orderId} for {contract.symbol} {order.action} "
                       f"(Qty: {order.totalQuantity})")
            return trade
        except Exception as e:
            # If order placement failed, remove from rate limiter tracking
            if self.rate_limiter:
                await self.rate_limiter.order_completed(
                    symbol=contract.symbol,
                    action=order.action,
                    account=getattr(order, 'account', 'default')
                )
            logger.error(f"Failed to place order: {e}")
            raise
    
    async def cancel_order(self, order_id: int) -> bool:
        """Cancel an order by order ID."""
        await self.ensure_connected()
        
        try:
            # First, find the trade object for this order
            trade = await self.get_order(order_id)
            if not trade:
                logger.error(f"Order {order_id} not found, cannot cancel")
                return False
            
            # Check if order is in a cancellable state
            if hasattr(trade, 'orderStatus') and trade.orderStatus:
                status = trade.orderStatus.status
                if status in ['Cancelled', 'Filled']:
                    logger.warning(f"Order {order_id} is already {status}, cannot cancel")
                    return False
            
            # Cancel using the order object (correct ib_insync usage)
            if not hasattr(trade, 'order') or not trade.order:
                logger.error(f"Trade object for order {order_id} does not have a valid order")
                return False
            
            # Apply rate limiting for order cancellation
            if self.rate_limiter:
                if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                    raise ConnectionError("Rate limit exceeded for order cancellation")
                
            cancelled_trade = self.ib.cancelOrder(trade.order)
            
            # Remove from active order tracking
            if self.rate_limiter and hasattr(trade, 'order'):
                await self.rate_limiter.order_completed(
                    symbol=trade.contract.symbol,
                    action=trade.order.action,
                    account=getattr(trade.order, 'account', 'default')
                )
            
            # Add a small delay to allow cancellation to process
            await asyncio.sleep(0.1)
            
            logger.info(f"Order cancellation requested: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def get_orders(self) -> List[Trade]:
        """Get all orders."""
        await self.ensure_connected()
        
        # Apply rate limiting for getting orders (it's a TWS message)
        if self.rate_limiter:
            if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                raise ConnectionError("Rate limit exceeded for getting orders")
        
        return self.ib.trades()
    
    async def get_all_open_orders(self) -> List[Trade]:
        """Get all open orders from all client IDs using reqAllOpenOrders."""
        await self.ensure_connected()
        try:
            # Apply rate limiting for requesting all open orders
            if self.rate_limiter:
                if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                    raise ConnectionError("Rate limit exceeded for getting all open orders")
            
            # Request all open orders from all clients
            self.ib.reqAllOpenOrders()
            
            # Wait a moment for the orders to be populated
            await asyncio.sleep(1.0)
            
            # Return all trades (should now include orders from all clients)
            all_trades = self.ib.trades()
            logger.info(f"Retrieved {len(all_trades)} total orders from all clients")
            return all_trades
            
        except Exception as e:
            logger.error(f"Failed to get all open orders: {e}")
            return []
    
    async def cancel_all_open_orders(self) -> Dict[str, Any]:
        """Cancel all open orders across all client IDs."""
        await self.ensure_connected()
        
        try:
            # Get all open orders from all clients
            all_orders = await self.get_all_open_orders()
            
            if not all_orders:
                return {"message": "No open orders found", "cancelled": [], "failed": []}
            
            cancelled_orders = []
            failed_orders = []
            
            # Group orders by client ID
            orders_by_client = {}
            for trade in all_orders:
                if hasattr(trade, 'order') and trade.order:
                    client_id = getattr(trade.order, 'clientId', 0)
                    if client_id not in orders_by_client:
                        orders_by_client[client_id] = []
                    orders_by_client[client_id].append(trade)
            
            logger.info(f"Found orders from {len(orders_by_client)} different client IDs")
            
            # Cancel orders for each client ID
            for client_id, orders in orders_by_client.items():
                logger.info(f"Processing {len(orders)} orders from client ID {client_id}")
                
                # Connect with the appropriate client ID if different from current
                current_client_id = getattr(self.ib.client, 'clientId', settings.client_id)
                
                if client_id != current_client_id:
                    # Need to reconnect with the correct client ID
                    success = await self._reconnect_with_client_id(client_id)
                    if not success:
                        for trade in orders:
                            failed_orders.append({
                                "order_id": trade.order.orderId,
                                "client_id": client_id,
                                "reason": f"Failed to connect with client ID {client_id}"
                            })
                        continue
                
                # Cancel orders for this client
                for trade in orders:
                    try:
                        if hasattr(trade, 'orderStatus') and trade.orderStatus:
                            status = trade.orderStatus.status
                            if status in ['Cancelled', 'Filled']:
                                logger.info(f"Order {trade.order.orderId} already {status}, skipping")
                                continue
                        
                        self.ib.cancelOrder(trade.order)
                        await asyncio.sleep(0.1)  # Small delay
                        
                        cancelled_orders.append({
                            "order_id": trade.order.orderId,
                            "client_id": client_id,
                            "symbol": getattr(trade.contract, 'symbol', 'Unknown')
                        })
                        logger.info(f"Successfully cancelled order {trade.order.orderId} from client {client_id}")
                        
                    except Exception as e:
                        failed_orders.append({
                            "order_id": trade.order.orderId,
                            "client_id": client_id,
                            "reason": str(e)
                        })
                        logger.error(f"Failed to cancel order {trade.order.orderId}: {e}")
            
            return {
                "message": f"Cancelled {len(cancelled_orders)} orders, {len(failed_orders)} failed",
                "cancelled": cancelled_orders,
                "failed": failed_orders
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return {"message": f"Error: {e}", "cancelled": [], "failed": []}
    
    async def _reconnect_with_client_id(self, client_id: int) -> bool:
        """Reconnect with a specific client ID."""
        try:
            # Disconnect current connection
            if self._is_connected:
                self.ib.disconnect()
                self._is_connected = False
                await asyncio.sleep(1.0)
            
            # Connect with new client ID
            await self.ib.connectAsync(
                host=settings.tws_host,
                port=settings.tws_port,
                clientId=client_id,
                timeout=settings.connection_timeout
            )
            self._is_connected = True
            
            # Wait for connection to stabilize
            await asyncio.sleep(2.0)
            
            logger.info(f"Successfully reconnected with client ID {client_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reconnect with client ID {client_id}: {e}")
            self._is_connected = False
            return False
    
    async def get_order(self, order_id: int) -> Optional[Trade]:
        """Get a specific order by ID."""
        trades = await self.get_orders()
        for trade in trades:
            if trade.order.orderId == order_id:
                return trade
        return None
    
    async def get_positions(self) -> List[Position]:
        """Get all positions."""
        await self.ensure_connected()
        
        # Apply rate limiting for getting positions (it's a TWS message)
        if self.rate_limiter:
            if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                raise ConnectionError("Rate limit exceeded for getting positions")
        
        return self.ib.positions()
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary."""
        await self.ensure_connected()
        
        try:
            # Apply rate limiting for getting account summary (it's a TWS message)
            if self.rate_limiter:
                if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                    raise ConnectionError("Rate limit exceeded for getting account summary")
            
            # Use reqAccountSummary for better async handling
            account_values = self.ib.accountSummary()
            summary = {}
            
            for av in account_values:
                summary[av.tag] = {
                    'value': av.value,
                    'currency': av.currency,
                    'account': av.account
                }
            
            return summary
        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
            raise
    
    async def modify_order(self, order_id: int, **modifications) -> bool:
        """Modify an existing order."""
        await self.ensure_connected()
        
        trade = await self.get_order(order_id)
        if not trade:
            raise ValueError(f"Order {order_id} not found")
        
        try:
            # Apply rate limiting for order modification
            if self.rate_limiter:
                if not await self.rate_limiter.acquire_message_token(timeout=settings.rate_limit_timeout):
                    raise ConnectionError("Rate limit exceeded for order modification")
            
            # Apply modifications to the order
            for key, value in modifications.items():
                if hasattr(trade.order, key):
                    setattr(trade.order, key, value)
            
            # Re-place the modified order
            self.ib.placeOrder(trade.contract, trade.order)
            logger.info(f"Order modified: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return False
    
    def _on_order_status(self, trade: Trade):
        """Handle order status updates."""
        order = trade.order
        status = trade.orderStatus
        logger.info(f"Order {order.orderId} status: {status.status}")
        
        # Remove from rate limiter tracking if order is completed
        if self.rate_limiter and status and status.status in ['Cancelled', 'Filled']:
            asyncio.create_task(self.rate_limiter.order_completed(
                symbol=trade.contract.symbol,
                action=order.action,
                account=getattr(order, 'account', 'default')
            ))
    
    def _on_execution(self, trade: Trade, fill):
        """Handle execution reports."""
        logger.info(f"Execution: Order {trade.order.orderId}, "
                   f"Filled: {fill.execution.shares} at {fill.execution.price}")
    
    def _on_connected(self):
        """Handle connection events."""
        self._is_connected = True
        logger.info("TWS connection established")
    
    def _on_disconnected(self):
        """Handle disconnection events."""
        self._is_connected = False
        logger.warning("TWS connection lost")
    
    def _load_breaker_state(self):
        """Load emergency breaker state from file."""
        try:
            if self._emergency_breaker_file.exists():
                with open(self._emergency_breaker_file, 'r') as f:
                    data = json.load(f)
                    self._emergency_breaker_active = data.get("active", False)
                    if self._emergency_breaker_active:
                        logger.warning("Emergency breaker is ACTIVE - loaded from file")
            else:
                self._emergency_breaker_active = False
        except Exception as e:
            logger.error(f"Error loading breaker state: {e}")
            self._emergency_breaker_active = False
    
    def _save_breaker_state(self):
        """Save emergency breaker state to file."""
        try:
            data = {
                "active": self._emergency_breaker_active,
                "timestamp": datetime.now().isoformat()
            }
            with open(self._emergency_breaker_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving breaker state: {e}")
    
    def trigger_emergency_breaker(self, reason: str = "Manual trigger") -> Dict[str, Any]:
        """Trigger the emergency breaker."""
        if self._emergency_breaker_active:
            return {
                "message": "Emergency breaker was already active",
                "active": True,
                "timestamp": datetime.now().isoformat()
            }
        
        self._emergency_breaker_active = True
        self._save_breaker_state()
        
        logger.critical(f"EMERGENCY BREAKER TRIGGERED: {reason}")
        
        return {
            "message": f"Emergency breaker activated: {reason}",
            "active": True,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        }
    
    def reset_emergency_breaker(self) -> Dict[str, Any]:
        """Reset/clear the emergency breaker."""
        if not self._emergency_breaker_active:
            return {
                "message": "Emergency breaker was not active",
                "active": False,
                "timestamp": datetime.now().isoformat()
            }
        
        self._emergency_breaker_active = False
        self._save_breaker_state()
        
        logger.warning("Emergency breaker RESET - trading operations restored")
        
        return {
            "message": "Emergency breaker reset - trading operations restored",
            "active": False,
            "timestamp": datetime.now().isoformat()
        }
    
    def is_emergency_breaker_active(self) -> bool:
        """Check if emergency breaker is active."""
        return self._emergency_breaker_active
    
    def get_emergency_breaker_status(self) -> Dict[str, Any]:
        """Get emergency breaker status."""
        try:
            breaker_data = {}
            if self._emergency_breaker_file.exists():
                with open(self._emergency_breaker_file, 'r') as f:
                    breaker_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading breaker status: {e}")
            breaker_data = {}
        
        return {
            "active": self._emergency_breaker_active,
            "timestamp": breaker_data.get("timestamp", datetime.now().isoformat()),
            "tws_connected": self.is_connected(),
            "rate_limiting_enabled": self.rate_limiter is not None,
            "message": "TRADING BLOCKED" if self._emergency_breaker_active else "Trading operational"
        }
    
    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get comprehensive rate limit status."""
        if not self.rate_limiter:
            return {
                "enabled": False,
                "message": "Rate limiting is disabled"
            }
        
        return await self.rate_limiter.get_comprehensive_status()


# Global IB service instance
ib_service = IBService()