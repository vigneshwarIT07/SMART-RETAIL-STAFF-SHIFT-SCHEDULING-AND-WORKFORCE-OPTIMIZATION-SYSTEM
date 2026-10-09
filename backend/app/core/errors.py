"""Application error type and the unified JSON response envelope.

Every response the API returns - success or failure - uses the same shape so the
frontend has exactly one parsing rule:

``{"success": true, "data": {...}, "message": "..."}``
``{"success": false, "data": null, "message": "Human readable reason"}``

FastAPI's own ``HTTPException`` and unhandled exceptions are converted to the
same envelope by the handlers registered in :func:`register_exception_handlers`,
so Swagger examples stay consistent with real responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def success(
    data: Any = None, message: str = "", status_code: int = 200
) -> dict[str, Any]:
    """Build a successful envelope.

    Args:
        data: The payload to place under the ``data`` key.
        message: A short human-readable summary.
        status_code: Only used by callers that convert this into a response.

    Returns:
        The envelope dictionary.
    """
    del status_code  # kept for call-site readability
    return {"success": True, "data": data, "message": message}


def failure(
    message: str,
    status_code: int = 400,
    data: Any = None,
) -> dict[str, Any]:
    """Build a failure envelope.

    Args:
        message: Human-readable reason for the failure.
        status_code: HTTP status the response should use.
        data: Optional structured detail (e.g. field validation errors).

    Returns:
        The envelope dictionary.
    """
    del status_code
    return {"success": False, "data": data, "message": message}


class AppError(Exception):
    """Domain error that maps directly onto an HTTP response.

    Services raise this instead of ``HTTPException`` so that business rules stay
    independent of the web framework.
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
    ) -> None:
        """Initialise the error.

        Args:
            message: Human-readable reason shown to the user.
            status_code: HTTP status code to respond with.
            data: Optional structured detail for the client.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data


class NotFoundError(AppError):
    """Raised when a requested record does not exist or is out of scope."""

    def __init__(self, message: str = "Resource not found") -> None:
        """Initialise with a 404 status."""
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class ForbiddenError(AppError):
    """Raised when the caller is authenticated but not permitted."""

    def __init__(self, message: str = "You do not have permission to do that") -> None:
        """Initialise with a 403 status."""
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class UnauthorizedError(AppError):
    """Raised when the caller cannot be authenticated at all."""

    def __init__(self, message: str = "Not authenticated") -> None:
        """Initialise with a 401 status."""
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class ConflictError(AppError):
    """Raised when a request collides with the current state of the data."""

    def __init__(self, message: str, data: Any = None) -> None:
        """Initialise with a 409 status."""
        super().__init__(message, status.HTTP_409_CONFLICT, data)


def _envelope(message: str, status_code: int, data: Any = None) -> JSONResponse:
    """Render an envelope as a JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"success": False, "data": data, "message": message}),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so every error path emits the unified envelope.

    Args:
        app: The FastAPI application to register handlers on.
    """

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        """Convert a domain error into the failure envelope."""
        return _envelope(exc.message, exc.status_code, exc.data)

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        """Convert FastAPI/Starlette HTTP errors into the failure envelope."""
        detail = exc.detail
        data: Any = None
        if isinstance(detail, dict):
            message = str(detail.get("message") or "Request failed")
            data = detail.get("data")
        else:
            message = str(detail)
        return _envelope(message, exc.status_code, data)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert request-body/query validation errors into the envelope.

        The message names the first offending field so the UI can show a short,
        human-readable message instead of a raw Pydantic dump.
        """
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        reason = first.get("msg", "Invalid input")
        message = f"{field}: {reason}" if field else reason
        return _envelope(message, status.HTTP_422_UNPROCESSABLE_ENTITY, errors)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_request: Request, exc: IntegrityError) -> JSONResponse:
        """Translate a database constraint violation into a 409.

        The raw driver message is never returned because it can name columns,
        indexes, and constraint names that clients have no business knowing.
        """
        detail = str(exc.orig) if getattr(exc, "orig", None) else ""
        if detail:
            lowered = detail.lower()
            if "unique" in lowered or "duplicate" in lowered:
                message = "That value is already in use and must be unique."
            elif "foreign key" in lowered:
                message = "A referenced record is missing or still in use."
            else:
                message = "The change conflicts with existing data."
        else:  # pragma: no cover - defensive
            message = "The change conflicts with existing data."
        return _envelope(message, status.HTTP_409_CONFLICT)

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Return a generic 500 for unexpected database failures."""
        return _envelope(
            "A database error occurred. Please try again.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
