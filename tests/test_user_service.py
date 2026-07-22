from unittest.mock import AsyncMock, patch

import pytest

from services.user_service import get_or_create_user


@pytest.mark.asyncio
async def test_get_or_create_user_returns_existing_when_found():
    fake_session = AsyncMock()
    fake_existing_user = object()  # stand-in, we don't need a real User here

    with patch(
        "services.user_service.get_user_by_email", return_value=fake_existing_user
    ) as mock_get:
        user, was_created = await get_or_create_user(fake_session, "test@example.com")

    mock_get.assert_awaited_once_with(fake_session, "test@example.com")
    assert user is fake_existing_user
    assert was_created is False


@pytest.mark.asyncio
async def test_get_or_create_user_creates_when_not_found():
    fake_session = AsyncMock()
    fake_new_user = object()

    with (
        patch("services.user_service.get_user_by_email", return_value=None),
        patch(
            "services.user_service.create_user", return_value=fake_new_user
        ) as mock_create,
    ):
        user, was_created = await get_or_create_user(fake_session, "new@example.com")

    mock_create.assert_awaited_once_with(fake_session, "new@example.com", None)
    assert user is fake_new_user
    assert was_created is True