class DomainException(Exception):
    """Base class for all domain-specific exceptions."""

    def __init__(self, message: str, intent: str = None):
        super().__init__(message)
        self.message = message
        self.intent = (
            intent  # Expected action intent (e.g., 'recharge', 'join_channel')
        )


class InsufficientCreditsError(DomainException):
    """Raised when a user does not have enough credits to perform an action."""

    def __init__(self, current: int, cost: int, message: str = "Insufficient credits"):
        super().__init__(message, intent="recharge")
        self.current = current
        self.cost = cost


class AccessDeniedError(DomainException):
    """Raised when a user does not have access (e.g., not in the required channel)."""

    def __init__(self, message: str = "Access denied", intent: str = "join_channel"):
        super().__init__(message, intent=intent)
