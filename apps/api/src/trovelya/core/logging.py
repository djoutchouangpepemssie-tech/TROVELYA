"""Structured JSON logs (structlog) with personal data redaction (GDPR, section 15).

Every line, ours or a library's (uvicorn, arq, SQLAlchemy through the standard `logging`
module), goes through `redact_pii` before it is written.
"""

import ipaddress
import logging
import re
import sys
from collections.abc import Mapping
from typing import Any, cast

import structlog
from structlog.typing import EventDict, Processor

REDACTED = "[REDACTED]"

# Any key whose name contains one of these words has its value masked, whatever the value.
_SENSITIVE_KEY = re.compile(
    r"password|token|secret|authorization|cookie|email|phone|iban|address", re.IGNORECASE
)
# Values that look like personal data are masked wherever they appear in a string.
_SENSITIVE_VALUES = (
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # e-mail
    re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+"),  # bearer token
    re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),  # IBAN
    re.compile(r"(?<![\w+])(?:\+\d{2,3}[\s.-]?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\w)"),  # phone
)


# IP address candidates; each match is confirmed with `ipaddress` before it is masked, so
# times ("11:55:25") and version numbers ("3.12.15") are left alone.
_IP_CANDIDATE = re.compile(
    r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])"  # IPv4, also after a "key:" prefix
    r"|(?<![\w.:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w.])"  # IPv6
)


def _mask_ip(match: re.Match[str]) -> str:
    try:
        ipaddress.ip_address(match.group(0))
    except ValueError:
        return match.group(0)
    return REDACTED


def _redact_text(text: str) -> str:
    for pattern in _SENSITIVE_VALUES:
        text = pattern.sub(REDACTED, text)
    return _IP_CANDIDATE.sub(_mask_ip, text)


def redact_value(value: object) -> object:
    """Mask personal data in any log or telemetry value (strings, mappings, sequences)."""
    return _redact(value)


def _redact(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            key: REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(item) for item in cast("list[object] | tuple[object, ...]", value)]
    return value


def redact_pii(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    return {
        key: REDACTED if _SENSITIVE_KEY.search(key) else _redact(value)
        for key, value in event_dict.items()
    }


_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.format_exc_info,
]


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[*_SHARED_PROCESSORS, redact_pii, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Standard library loggers (uvicorn, arq…) render through the same pipeline.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[*_SHARED_PROCESSORS, structlog.stdlib.add_logger_name],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                redact_pii,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "arq"):
        library_logger = logging.getLogger(name)
        library_logger.handlers = []
        library_logger.propagate = True
    # arq logs every cron run at INFO (the outbox relay runs every second): keep warnings
    # and failures only; our jobs log what they actually did.
    logging.getLogger("arq").setLevel(logging.WARNING)
