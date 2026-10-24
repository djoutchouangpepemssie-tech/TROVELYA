"""Create a staff account and print its passkey enrolment link (ADR-0018).

Run on the server (Railway: `railway run`), with the API's environment:
    uv run python -m trovelya.scripts.create_staff --email prenom+staff@example.org \\
        --role staff_superadmin

The link is valid 15 minutes and works once; it is printed here only, never e-mailed. Running
the script again for a staff account that has no passkey yet prints a new link.
"""

import argparse
import asyncio
import sys

from trovelya.core.config import get_settings
from trovelya.core.db import make_engine, make_sessionmaker
from trovelya.core.redis import make_redis
from trovelya.modules.identity.service.staff_accounts import (
    ENROLMENT_TTL,
    StaffAccountError,
    issue_staff_enrolment,
)
from trovelya.shared.clock import SystemClock


async def _run(email: str, role: str) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    redis = make_redis(settings.redis_url)
    try:
        enrolment = await issue_staff_enrolment(
            make_sessionmaker(engine),
            redis,
            email=email,
            role=role,
            settings=settings,
            clock=SystemClock(),
        )
    except StaffAccountError as exc:
        sys.stderr.write(f"Refusé : {exc}\n")
        return 1
    finally:
        await redis.aclose()
        await engine.dispose()
    minutes = int(ENROLMENT_TTL.total_seconds() // 60)
    state = "créé" if enrolment.created else "existant, sans passkey"
    sys.stdout.write(
        f"Compte staff {state}. Ouvrez ce lien dans les {minutes} minutes, une seule fois :\n"
        f"{enrolment.link}\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", default="staff_superadmin")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.email, args.role))


if __name__ == "__main__":
    raise SystemExit(main())
