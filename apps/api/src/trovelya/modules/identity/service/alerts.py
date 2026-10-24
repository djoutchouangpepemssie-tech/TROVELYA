"""Security alerts sent from domain events (section 13.2, E7 of the P1 plan).

`session.created` → e-mail when the sign-in comes from a device or a country the account has
not used in the last 90 days. No alert for the very first session (the sign-up itself).
"""

from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.modules.identity import repository
from trovelya.modules.identity.emails import new_login_message
from trovelya.shared.events import OutboxEvent, Subscription

KNOWN_CONTEXT_WINDOW = timedelta(days=90)
PARIS = ZoneInfo("Europe/Paris")


def security_link(settings: Settings) -> str:
    return f"{settings.web_origin.rstrip('/')}/fr/compte/parametres/securite"


def identity_subscriptions(queue: JobQueue, settings: Settings) -> list[Subscription]:
    async def notify_new_login(db: AsyncSession, event: OutboxEvent) -> None:
        context = await repository.find_session_context(
            db, UUID(event.payload["session_id"]), window=KNOWN_CONTEXT_WINDOW
        )
        if context is None or not context.has_previous or context.known_context:
            return
        message = new_login_message(
            to=context.email,
            when=context.created_at.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M"),
            device=context.device_label or "appareil inconnu",
            country=context.country_code or "inconnu",
            security_link=security_link(settings),
        )
        await enqueue_email(db, queue, message, settings=settings)

    return [Subscription("identity.new_login_alert", "session.created", notify_new_login)]
