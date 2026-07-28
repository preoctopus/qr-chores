"""Photo policy, upload, and serving tests."""

from datetime import time
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token
from qr_chores.services.storage import sniff_content_type

# 1x1 PNG
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Clean bathroom",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(20, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


async def _login_child(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )


async def _login_parent(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )


def test_sniff_png() -> None:
    assert sniff_content_type(TINY_PNG, "image/png") == "image/png"


def test_sniff_rejects_garbage() -> None:
    from qr_chores.services.storage import StorageError

    with pytest.raises(StorageError):
        sniff_content_type(b"not-an-image", "image/png")


@pytest.mark.asyncio
async def test_required_photo_blocks_without_file(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.required,
        title="Mop floor",
        assignee_user_id=child_user.id,
    )
    await _login_child(client, child_user)
    response = await client.post(f"/c/{chore.qr_token}")
    assert response.status_code == 400
    assert "photo is required" in response.text.lower()

    async with app.state.session_factory() as session:
        count = len((await session.execute(select(ChoreCompletion))).scalars().all())
        assert count == 0


@pytest.mark.asyncio
async def test_required_photo_succeeds_with_png(
    client: AsyncClient, child_user: User, parent_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.required,
        title="Wipe sink",
        base_points=20,
        assignee_user_id=child_user.id,
    )
    await _login_child(client, child_user)
    response = await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert response.status_code == 200
    assert "+20" in response.text or "20" in response.text

    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.photo_object_key is not None
        assert completion.photo_object_key.endswith(".png")
        completion_id = completion.id

    photo = await client.get(f"/photos/{completion_id}")
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/")
    assert photo.content[:8] == b"\x89PNG\r\n\x1a\n"

    # Parent can view too
    await _login_parent(client, parent_user)
    parent_photo = await client.get(f"/photos/{completion_id}")
    assert parent_photo.status_code == 200
    today = await client.get("/today")
    assert "Wipe sink" in today.text
    assert "View photo" in today.text or f"/photos/{completion_id}" in today.text

    history = await client.get("/history")
    assert history.status_code == 200
    assert "Wipe sink" in history.text


@pytest.mark.asyncio
async def test_optional_photo_works_without_file(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.optional, assignee_user_id=child_user.id
    )
    await _login_child(client, child_user)
    response = await client.post(f"/c/{chore.qr_token}")
    assert response.status_code == 200
    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.photo_object_key is None


@pytest.mark.asyncio
async def test_optional_photo_saves_when_provided(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.optional, assignee_user_id=child_user.id
    )
    await _login_child(client, child_user)
    response = await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("shot.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert response.status_code == 200
    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.photo_object_key is not None


@pytest.mark.asyncio
async def test_none_policy_ignores_need_for_photo(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.none, assignee_user_id=child_user.id
    )
    await _login_child(client, child_user)
    page = await client.get(f"/c/{chore.qr_token}")
    assert page.status_code == 200
    assert 'name="photo"' not in page.text

    response = await client.post(f"/c/{chore.qr_token}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_photo_requires_auth(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.required, assignee_user_id=child_user.id
    )
    await _login_child(client, child_user)
    await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("p.png", BytesIO(TINY_PNG), "image/png")},
    )
    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        cid = completion.id

    # New client without cookies
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.get(f"/photos/{cid}")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_photo_storage_error_maps_to_400(
    client: AsyncClient, child_user: User, parent_user: User, app
) -> None:
    from qr_chores.services.storage import StorageError

    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.required,
        title="Water plants",
        assignee_user_id=child_user.id,
    )
    await _login_child(client, child_user)
    await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        completion_id = completion.id

    def _boom(self, key: str):
        raise StorageError("Corrupt photo key.", "bad_key")

    from qr_chores.services.storage import LocalPhotoStorage

    original_open = LocalPhotoStorage.open
    LocalPhotoStorage.open = _boom
    try:
        await _login_parent(client, parent_user)
        html_resp = await client.get(f"/photos/{completion_id}")
        assert html_resp.status_code == 400
        assert "Corrupt photo key." in html_resp.text

        api_resp = await client.get(f"/api/v1/photos/{completion_id}")
        assert api_resp.status_code == 400
        assert api_resp.json()["detail"] == "Corrupt photo key."
    finally:
        LocalPhotoStorage.open = original_open


@pytest.mark.asyncio
async def test_reject_non_image_upload(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.required, assignee_user_id=child_user.id
    )
    await _login_child(client, child_user)
    response = await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("evil.txt", BytesIO(b"not-image-data"), "text/plain")},
    )
    assert response.status_code == 400
    assert (
        "jpeg" in response.text.lower()
        or "png" in response.text.lower()
        or "webp" in response.text.lower()
    )
