import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.models import Base
from workers.celery_app import celery_app


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url)

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection, expire_on_commit=False
        )
        session = session_factory()

        yield session

        await session.close()
        await transaction.rollback()

    await engine.dispose()

@pytest.fixture(autouse=True)
def celery_eager_mode():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False