from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from repositories.user_repository import create_user, get_user_by_email


async def get_or_create_user(
    session: AsyncSession, email: str, org_id: UUID | None = None
) -> tuple[User, bool]:
    """Returns (user, was_created)."""
    existing = await get_user_by_email(session, email)
    if existing:
        return existing, False

    user = await create_user(session, email, org_id)
    return user, True