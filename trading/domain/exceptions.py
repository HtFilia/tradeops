class TradingError(Exception):
    """Base exception for trading agent errors."""


class InsufficientBalanceError(TradingError):
    """Raised when a user lacks cash to execute an order."""


class InsufficientPositionError(TradingError):
    """Raised when a user lacks inventory to sell."""


class OrderValidationError(TradingError):
    """Raised when an order fails validation checks."""


class InstrumentNotFoundError(TradingError):
    """Raised when a requested instrument does not exist in market data."""
