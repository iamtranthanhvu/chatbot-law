class AppError(Exception):
    """Business error with a stable code; the API maps it to an HTTP response in one place."""

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.headers: dict[str, str] = {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Bạn đã hỏi quá nhiều trong thời gian ngắn, vui lòng thử lại sau.")
        self.headers = {"Retry-After": str(retry_after)}
