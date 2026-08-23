"""RFC 9457 problem+json error responses.

One shape for every failure, so the frontend and MCP tools have exactly one
error format to handle instead of guessing per endpoint.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from ninja.errors import AuthenticationError, ValidationError

from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)


def problem(
    *,
    status: int,
    title: str,
    detail: str = "",
    type_: str = "about:blank",
    **extra,
) -> JsonResponse:
    body = {"type": type_, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body.update({key: value for key, value in extra.items() if value is not None})
    return JsonResponse(body, status=status, content_type="application/problem+json")


def register_exception_handlers(api) -> None:
    @api.exception_handler(DomainError)
    def _domain_error(request, exc: DomainError):
        # Services raise these deliberately; they carry a message meant to be
        # shown to a person, so no logging noise.
        return problem(
            status=exc.status_code,
            title=exc.title,
            detail=str(exc.detail),
            **exc.extra,
        )

    @api.exception_handler(Http404)
    def _not_found(request, exc):
        return problem(status=404, title="Not found", detail="No such resource.")

    @api.exception_handler(AuthenticationError)
    def _unauthenticated(request, exc):
        return problem(
            status=401,
            title="Authentication required",
            detail="Sign in to use this endpoint.",
        )

    @api.exception_handler(ValidationError)
    def _invalid(request, exc: ValidationError):
        return problem(
            status=422,
            title="Invalid request",
            detail="One or more fields failed validation.",
            errors=exc.errors,
        )

    @api.exception_handler(Exception)
    def _unhandled(request, exc):
        logger.exception("unhandled error on %s %s", request.method, request.path)
        if settings.DEBUG:
            return problem(
                status=500,
                title="Server error",
                detail=f"{type(exc).__name__}: {exc}",
            )
        return problem(
            status=500,
            title="Server error",
            detail="Something went wrong. The error has been logged.",
        )
