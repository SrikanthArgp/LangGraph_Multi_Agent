import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Every error response - expected (HTTPException) or not - returns the same
    {"detail": ...} envelope; only the unhandled case logs a full server-side traceback.
    Without this, an uncaught exception in a router would leak a raw traceback to the client.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("unhandled_exception", extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal server error"},
        )
