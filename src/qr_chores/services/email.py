"""Email notification service."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion
from qr_chores.models.user import User, UserRole

logger = logging.getLogger("qr_chores.email")

# In-memory outbox for testing when SMTP host is empty
_outbox: list[dict[str, Any]] = []


def get_outbox() -> list[dict[str, Any]]:
    """Return recorded outbox emails (for tests)."""
    return list(_outbox)


def clear_outbox() -> None:
    """Clear recorded outbox emails (for tests)."""
    _outbox.clear()


def _send_smtp_email(
    settings: Settings,
    to_addresses: list[str],
    subject: str,
    body: str,
) -> None:
    """Send email via SMTP synchronously."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = ", ".join(to_addresses)
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def send_email(
    settings: Settings,
    to_addresses: list[str],
    subject: str,
    body: str,
) -> None:
    """Send an email using configured SMTP settings or record in test outbox."""
    if not to_addresses:
        return

    record = {
        "to": to_addresses,
        "subject": subject,
        "body": body,
        "from": settings.smtp_from_email,
    }
    _outbox.append(record)

    if not settings.smtp_host:
        logger.info(
            "SMTP_HOST not configured. Recorded email to %s: %s",
            to_addresses,
            subject,
        )
        return

    try:
        await asyncio.to_thread(
            _send_smtp_email,
            settings,
            to_addresses,
            subject,
            body,
        )
        logger.info("Sent email to %s: %s", to_addresses, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_addresses, exc)


async def send_completion_note_email(
    db: AsyncSession,
    settings: Settings,
    completion: ChoreCompletion,
    chore: Chore,
    child: User,
    notes: str,
) -> None:
    """Send an email notification to parents when a child includes notes on chore completion."""
    clean_notes = notes.strip()
    if not clean_notes:
        return

    to_emails: list[str] = []

    if child.parent_id is not None:
        parent_res = await db.execute(
            select(User).where(User.id == child.parent_id, User.is_active.is_(True))
        )
        parent = parent_res.scalar_one_or_none()
        if parent and parent.email:
            to_emails.append(parent.email)

    if not to_emails:
        parents_res = await db.execute(
            select(User.email).where(User.role == UserRole.parent, User.is_active.is_(True))
        )
        to_emails = [e for e in parents_res.scalars().all() if e]

    if not to_emails:
        logger.warning("No parent emails found for child completion note.")
        return

    child_name = child.display_name or child.first_name or "Child"
    chore_title = chore.title

    subject = f"[QR Chores] Note from {child_name} on {chore_title}"
    body = (
        f"Hi,\n\n"
        f'{child_name} left a note when completing "{chore_title}":\n\n'
        f'"{clean_notes}"\n\n'
        f"--\n"
        f"QR Chores\n"
    )

    await send_email(settings, to_emails, subject, body)
