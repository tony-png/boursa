"""Custom exceptions for the TWS Orders API."""


class TWSAPIError(Exception):
    """Base exception for all TWS API related errors."""
    
    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class IBConnectionError(TWSAPIError):
    """Raised when there's an issue connecting to Interactive Brokers."""
    pass


class OrderNotFoundError(TWSAPIError):
    """Raised when an order cannot be found."""
    pass


class ContractError(TWSAPIError):
    """Raised when there's an issue with contract creation or qualification."""
    pass


class OrderPlacementError(TWSAPIError):
    """Raised when an order cannot be placed."""
    pass


class OrderCancellationError(TWSAPIError):
    """Raised when an order cannot be cancelled."""
    pass


class OrderModificationError(TWSAPIError):
    """Raised when an order cannot be modified."""
    pass


class AccountDataError(TWSAPIError):
    """Raised when account data cannot be retrieved."""
    pass


class PositionDataError(TWSAPIError):
    """Raised when position data cannot be retrieved."""
    pass