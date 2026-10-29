"""Optimistic locking (section 11.1): `PATCH` requires `If-Match: <version>`."""

from trovelya.core.errors import AppError, ErrorCode


def if_match_version(header: str | None) -> int | None:
    """The version sent, `5` or `"5"`; None for `*` (any version, RFC 9110). 428 without the
    header; 412 when unreadable or weak (`W/"5"`): If-Match compares strongly."""
    if header is None:
        raise AppError(ErrorCode.PRECONDITION_REQUIRED, 428)
    value = header.strip()
    if value == "*":
        return None
    digits = value.removeprefix('"').removesuffix('"') if len(value) > 1 else value
    if not digits.isdigit() or len(digits) > 10:
        raise AppError(ErrorCode.PRECONDITION_FAILED, 412)
    return int(digits)
