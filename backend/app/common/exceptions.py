import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

logger = structlog.get_logger()


class BuzzerError(Exception):
    """Base application error."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(BuzzerError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__("NOT_FOUND", message, status.HTTP_404_NOT_FOUND)


class ForbiddenError(BuzzerError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__("FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


class UnauthorizedError(BuzzerError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED)


class ConflictError(BuzzerError):
    def __init__(self, message: str = "Conflict"):
        super().__init__("CONFLICT", message, status.HTTP_409_CONFLICT)


# MySQL error codes answered with 503 TRY_AGAIN (docs/plans/t8-image-support.md §D).
LOCK_WAIT_TIMEOUT = 1205
DEADLOCK = 1213
_RETRYABLE_CODES = {LOCK_WAIT_TIMEOUT, DEADLOCK}


def mysql_error_code(exc: OperationalError) -> int | None:
    """The MySQL error number of a driver error (asyncmy, like PyMySQL, puts it in
    args[0])."""
    args = getattr(exc.orig, "args", ())
    return args[0] if args and isinstance(args[0], int) else None


def _internal_error() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BuzzerError)
    async def buzzer_error_handler(request: Request, exc: BuzzerError) -> JSONResponse:
        logger.warning(
            "app_error", code=exc.code, message=exc.message, path=str(request.url)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("validation_error", errors=exc.errors(), path=str(request.url))
        # exc.errors() can embed non-JSON-serializable objects (e.g. Pydantic v2 puts the
        # raw exception in a field-validator error's `ctx`), so this must go through
        # jsonable_encoder the same way FastAPI's own default handler does -- passing it
        # straight to JSONResponse crashes with a generic 500 that hides the real error.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "VALIDATION_ERROR",
                "detail": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(OperationalError)
    async def operational_error_handler(
        request: Request, exc: OperationalError
    ) -> JSONResponse:
        """A deadlock or lock-wait timeout is a 503 the client may retry. This handler
        takes every OperationalError away from the catch-all below, so any other one
        (a lost connection, say) gets the same 500 body as an unhandled exception."""
        code = mysql_error_code(exc)
        if code in _RETRYABLE_CODES:
            logger.warning("db_lock_conflict", mysql_code=code, path=str(request.url))
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "error": "TRY_AGAIN",
                    "message": "Another change to this game was in progress; try again",
                },
            )
        logger.error("unhandled_error", exc_info=exc, path=str(request.url))
        return _internal_error()

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", exc_info=exc, path=str(request.url))
        return _internal_error()
