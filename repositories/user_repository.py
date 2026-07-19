from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, email: str, org_id: UUID | None = None) -> User:
    user = User(email=email, org_id=org_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user