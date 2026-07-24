from repositories.user_repository import create_user, get_user_by_email


async def test_create_and_fetch_user(db_session):
    created = await create_user(db_session, "integration@example.com")

    fetched = await get_user_by_email(db_session, "integration@example.com")

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.email == "integration@example.com"


async def test_get_user_by_email_returns_none_when_not_found(db_session):
    result = await get_user_by_email(db_session, "doesnotexist@example.com")

    assert result is None