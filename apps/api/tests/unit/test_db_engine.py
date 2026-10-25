"""The database engine's settings (sections 5.4 and 15)."""

from trovelya.core.db import make_engine


def test_engine_hides_query_parameters() -> None:
    """An SQL error's message never quotes the values (a name, an address): defence in depth
    under the redaction of logs, error reports and traces."""
    engine = make_engine("postgresql+asyncpg://user:secret@localhost:5432/db")
    assert engine.sync_engine.hide_parameters is True
