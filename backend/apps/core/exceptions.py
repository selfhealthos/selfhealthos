"""Domain errors that map cleanly onto HTTP.

Services raise these; the API layer turns them into RFC 9457 problem
documents. Nothing in a service should know an HTTP status code beyond picking
the right class here.
"""


class DomainError(Exception):
    """Something the caller did wrong, described in terms they can act on."""

    status_code = 400
    title = "Bad request"

    def __init__(self, detail: str = "", **extra):
        super().__init__(detail)
        self.detail = detail or self.title
        self.extra = extra


class NotFound(DomainError):
    status_code = 404
    title = "Not found"


class Conflict(DomainError):
    status_code = 409
    title = "Conflict"


class Unavailable(DomainError):
    status_code = 422
    title = "Cannot be processed"
