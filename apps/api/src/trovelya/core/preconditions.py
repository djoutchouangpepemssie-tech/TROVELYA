"""Optimistic locking (section 11.1): `PATCH` requires `If-Match: <version>`."""

from trovelya.core.errors import AppError, ErrorCode


def if_match_version(header: str | None) -> int:
    """The version sent, `5`, `"5"` or `W/"5"`; 428 without the header, 412 when unreadable."""
    if header is None:
        raise AppError(ErrorCode.PRECONDITION_REQUIRED, 428)
    try:
        return int(header.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise AppError(ErrorCode.PRECONDITION_FAILED, 412) from exc
