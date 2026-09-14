class DomainError(Exception):
    error_code: str = "DOMAIN_ERROR"


class InvalidTimeWindowError(DomainError):
    error_code = "INVALID_TIME_WINDOW"


class OverlappingBookingError(DomainError):
    error_code = "OVERLAPPING_BOOKING"


class ResourceNotFoundError(DomainError):
    error_code = "RESOURCE_NOT_FOUND"


class BookingNotFoundError(DomainError):
    error_code = "BOOKING_NOT_FOUND"


class BookingAlreadyStartedError(DomainError):
    error_code = "BOOKING_ALREADY_STARTED"


class BookingAlreadyCancelledError(DomainError):
    error_code = "BOOKING_ALREADY_CANCELLED"


class BookingQuotaExceededError(DomainError):
    error_code = "BOOKING_QUOTA_EXCEEDED"
