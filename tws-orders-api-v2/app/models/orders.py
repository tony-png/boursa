from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator


class OrderAction(str, Enum):
    """Order action types."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order types."""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP LMT"


class SecurityType(str, Enum):
    """Security types."""
    STOCK = "STK"
    OPTION = "OPT"
    FUTURE = "FUT"
    FOREX = "CASH"
    BOND = "BOND"
    CFD = "CFD"


class TimeInForce(str, Enum):
    """Time in force types."""
    DAY = "DAY"
    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class OrderStatus(str, Enum):
    """Order status types."""
    PENDING_SUBMIT = "PendingSubmit"
    PENDING_CANCEL = "PendingCancel"
    PRE_SUBMITTED = "PreSubmitted"
    SUBMITTED = "Submitted"
    CANCELLED = "Cancelled"
    FILLED = "Filled"
    INACTIVE = "Inactive"
    PARTIALLY_FILLED = "PartiallyFilled"


class ContractRequest(BaseModel):
    """Request model for creating a contract."""
    symbol: str = Field(..., description="Stock symbol")
    sec_type: SecurityType = Field(SecurityType.STOCK, description="Security type")
    exchange: str = Field("SMART", description="Exchange")
    currency: str = Field("USD", description="Currency")
    
    @field_validator('symbol')
    @classmethod
    def symbol_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Symbol cannot be empty - received empty or whitespace-only value')
        return v.upper().strip()


class OrderRequest(BaseModel):
    """Request model for creating an order."""
    contract: ContractRequest
    action: OrderAction = Field(..., description="Buy or Sell")
    order_type: OrderType = Field(..., description="Order type")
    total_quantity: float = Field(..., gt=0, description="Total quantity to trade")
    limit_price: Optional[float] = Field(None, ge=0, description="Limit price (required for limit orders)")
    aux_price: Optional[float] = Field(None, ge=0, description="Auxiliary price (for stop orders)")
    time_in_force: TimeInForce = Field(TimeInForce.DAY, description="Time in force")
    good_after_time: Optional[str] = Field(None, description="Good after time (YYYYMMDD HH:MM:SS)")
    good_till_date: Optional[str] = Field(None, description="Good till date (YYYYMMDD HH:MM:SS)")
    outside_rth: bool = Field(False, description="Allow trading outside regular trading hours")
    hidden: bool = Field(False, description="Hidden order")
    
    @model_validator(mode='after')
    def validate_order_prices(self):
        """
        CRITICAL VALIDATION: Ensure required prices are provided for limit and stop orders.
        This prevents financial risk from orders being created without proper price constraints.
        """
        order_type = self.order_type
        limit_price = self.limit_price
        aux_price = self.aux_price
        
        # FIXED: Use string values instead of enum objects for comparison
        order_type_str = order_type.value if hasattr(order_type, 'value') else str(order_type)
        
        if order_type_str in ["LMT", "STP LMT"] and limit_price is None:
            raise ValueError(
                f'Limit price is required for {order_type_str} orders. '
                f'Order type: {order_type_str}, Limit price: {limit_price}, '
                f'Symbol: {self.contract.symbol}, Quantity: {self.total_quantity}'
            )
        
        if order_type_str in ["STP", "STP LMT"] and aux_price is None:
            raise ValueError(
                f'Auxiliary price (stop price) is required for {order_type_str} orders. '
                f'Order type: {order_type_str}, Aux price: {aux_price}, '
                f'Symbol: {self.contract.symbol}, Quantity: {self.total_quantity}'
            )
            
        return self


class OrderModifyRequest(BaseModel):
    """Request model for modifying an order."""
    total_quantity: Optional[float] = Field(None, gt=0, description="New total quantity")
    limit_price: Optional[float] = Field(None, ge=0, description="New limit price")
    aux_price: Optional[float] = Field(None, ge=0, description="New auxiliary price")
    time_in_force: Optional[TimeInForce] = Field(None, description="New time in force")
    outside_rth: Optional[bool] = Field(None, description="Allow trading outside RTH")
    hidden: Optional[bool] = Field(None, description="Hidden order")


class ContractResponse(BaseModel):
    """Response model for contract information."""
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    local_symbol: Optional[str] = None
    trading_class: Optional[str] = None
    con_id: Optional[int] = None


class OrderResponse(BaseModel):
    """Response model for order information."""
    order_id: int
    client_id: int
    perm_id: int
    action: str
    order_type: str
    total_quantity: float
    cash_qty: Optional[float] = None
    limit_price: Optional[float] = None
    aux_price: Optional[float] = None
    time_in_force: str
    outside_rth: bool
    hidden: bool
    good_after_time: Optional[str] = None
    good_till_date: Optional[str] = None
    status: str
    filled: float = 0.0
    remaining: float = 0.0
    avg_fill_price: float = 0.0
    last_fill_price: float = 0.0
    why_held: Optional[str] = None
    contract: ContractResponse
    
    class Config:
        from_attributes = True


class TradeResponse(BaseModel):
    """Response model for trade information."""
    order: OrderResponse
    contract: ContractResponse
    order_status: Dict[str, Any]
    fills: List[Dict[str, Any]] = []
    log: List[Dict[str, Any]] = []


class PositionResponse(BaseModel):
    """Response model for position information."""
    account: str
    contract: ContractResponse
    position: float
    avg_cost: float
    
    class Config:
        from_attributes = True


class AccountSummaryResponse(BaseModel):
    """Response model for account summary."""
    account_values: Dict[str, Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.now)


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    tws_connected: bool
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorResponse(BaseModel):
    """Response model for errors."""
    error: bool = True
    message: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)