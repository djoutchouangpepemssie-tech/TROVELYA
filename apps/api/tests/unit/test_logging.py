import json
import logging

import pytest
import structlog

from trovelya.core.logging import REDACTED, configure_logging, redact_pii


@pytest.fixture(autouse=True)
def _reset_structlog():  # pyright: ignore[reportUnusedFunction]
    yield
    structlog.reset_defaults()


def _last_json_line(text: str) -> dict[str, object]:
    return json.loads(text.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "secret",
    [
        "jean.dupont@gmail.com",
        "06 12 34 56 78",
        "+33 6 12 34 56 78",
        "FR76 3000 6000 0112 3456 7890 189",
        "Bearer abc.def",
    ],
)
def test_redact_email_phone_iban_token(secret: str, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    structlog.get_logger().info(f"contact {secret} now", detail={"note": [f"x {secret}"]})
    out = capsys.readouterr().out
    assert secret not in out
    assert REDACTED in out


def test_redact_sensitive_keys() -> None:
    event = redact_pii(
        None,
        "info",
        {
            "event": "login",
            "password": "hunter2",
            "Authorization": "Basic Zm9vOmJhcg==",
            "user_email": "x",
            "ip_address": "203.0.113.7",
            "nested": {"refresh_token": "abc", "count": 3},
        },
    )
    assert event["password"] == REDACTED
    assert event["Authorization"] == REDACTED
    assert event["user_email"] == REDACTED
    assert event["ip_address"] == REDACTED
    assert event["nested"] == {"refresh_token": REDACTED, "count": 3}
    assert event["event"] == "login"


def test_ordinary_values_are_kept() -> None:
    event = redact_pii(
        None,
        "info",
        {"event": "relay", "published": 12, "request_id": "req_0192ab", "amount_minor": 24000},
    )
    assert event == {
        "event": "relay",
        "published": 12,
        "request_id": "req_0192ab",
        "amount_minor": 24000,
    }


def test_log_line_has_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    with structlog.contextvars.bound_contextvars(request_id="req_abc"):
        structlog.get_logger().info("hello")
    line = _last_json_line(capsys.readouterr().out)
    assert line["request_id"] == "req_abc"
    assert line["event"] == "hello"


def test_stdlib_logs_are_json_and_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    logging.getLogger("uvicorn.access").info("GET /v1/x?email=jean.dupont@gmail.com 200")
    out = capsys.readouterr().out + capsys.readouterr().err
    line = _last_json_line(out)
    assert "jean.dupont@gmail.com" not in json.dumps(line)
    assert line["logger"] == "uvicorn.access"


@pytest.mark.parametrize("ip", ["92.170.253.181", "2a01:e0a:1f5:8c40::7b3"])
def test_redact_ip_addresses(ip: str) -> None:
    event = redact_pii(None, "info", {"event": f'{ip}:0 - "GET /v1/x HTTP/1.1" 500'})
    assert ip not in str(event["event"])


@pytest.mark.parametrize("text", ["11:55:25", "CPython 3.12.15", "req_01a16dc406fe7777"])
def test_times_and_versions_are_not_mistaken_for_ips(text: str) -> None:
    assert redact_pii(None, "info", {"event": text}) == {"event": text}


def test_access_log_lines_have_no_query_string(capsys: pytest.CaptureFixture[str]) -> None:
    """uvicorn writes the full request target; a searched address or a position stays out."""
    configure_logging()
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.9:5123",
        "GET",
        "/v1/geo/search?q=17%20rue%20des%20Capucins",
        "1.1",
        200,
    )
    line = _last_json_line(capsys.readouterr().out)
    assert "/v1/geo/search HTTP/1.1" in str(line["event"])
    assert "Capucins" not in json.dumps(line)


def _database_error(message: str) -> Exception:
    """An exception from a database driver's module, as asyncpg raises them."""
    error_type = type("DataError", (Exception,), {"__module__": "asyncpg.exceptions"})
    return error_type(message)


def test_database_error_messages_are_withheld(capsys: pytest.CaptureFixture[str]) -> None:
    """Drivers quote the values of a failed query; the traceback keeps the types only."""
    configure_logging()
    driver = _database_error("invalid input for query argument $1: 'Ambroisine Quintal'")
    try:
        try:
            raise driver
        except Exception as exc:
            raise RuntimeError("the request failed") from exc
    except RuntimeError:
        structlog.get_logger().exception("unhandled_error")
    line = _last_json_line(capsys.readouterr().out)
    rendered = str(line["exception"])
    assert "Ambroisine" not in rendered
    assert "asyncpg.exceptions.DataError: [REDACTED]" in rendered
    assert "RuntimeError: the request failed" in rendered  # other messages are kept
