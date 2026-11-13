"""Ver como: o usuário da plataforma vê (e age) o estúdio como admin ou professor, com auditoria."""

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.engines import central_session
from app.models.central import ImpersonationLog, PlatformUser
from tests.conftest import API, make_studio


def _studio_id(client, platform, slug="alpha"):
    return next(s["id"] for s in client.get(f"{API}/platform/studios", headers=platform).json() if s["slug"] == slug)


def _users(client, platform, studio_id):
    r = client.get(f"{API}/platform/studios/{studio_id}/users", headers=platform)
    assert r.status_code == 200, r.text
    return r.json()


def _impersonate(client, platform, studio_id, user_id):
    return client.post(f"{API}/platform/studios/{studio_id}/impersonate", json={"user_id": user_id}, headers=platform)


def _as(token):
    return {"Authorization": f"Bearer {token}"}


def _add_teacher_user(client, admin, name="Bia"):
    teacher = client.post(f"{API}/teachers", json={"name": name}, headers=admin).json()
    r = client.post(
        f"{API}/users",
        json={
            "name": name,
            "email": f"{name.lower()}@alpha.com",
            "password": "secret123",
            "role": "teacher",
            "teacher_id": teacher["id"],
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_platform_lists_studio_users_and_sees_as_admin(client, platform, admin):
    sid = _studio_id(client, platform)
    users = _users(client, platform, sid)
    assert [(u["name"], u["role"]) for u in users] == [("Dona", "admin")]

    r = _impersonate(client, platform, sid, users[0]["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["impersonated_by"] == "Root" and body["user"]["role"] == "admin" and body["studio"]["slug"] == "alpha"

    headers = _as(body["access_token"])
    assert client.get(f"{API}/students", headers=headers).status_code == 200
    assert client.get(f"{API}/payments", headers=headers).status_code == 200  # visão de admin
    me = client.get(f"{API}/auth/me", headers=headers).json()
    assert me["impersonated_by"] == "Root" and me["user"]["name"] == "Dona"


def test_platform_sees_as_teacher_with_teacher_permissions(client, platform, admin):
    bia = _add_teacher_user(client, admin)
    sid = _studio_id(client, platform)
    headers = _as(_impersonate(client, platform, sid, bia["id"]).json()["access_token"])
    assert client.get(f"{API}/students", headers=headers).status_code == 200
    assert client.get(f"{API}/payments", headers=headers).status_code == 403  # professor não vê pagamentos
    plan = {"name": "X", "sessions_per_week": 1, "total_classes": 4, "price": "1"}
    assert client.post(f"{API}/plans", json=plan, headers=headers).status_code == 403


def test_normal_login_has_no_impersonation_marker(client, admin):
    assert client.get(f"{API}/auth/me", headers=admin).json()["impersonated_by"] is None


def test_actions_are_recorded_with_the_operator_name(client, platform, admin):
    sid = _studio_id(client, platform)
    headers = _as(_impersonate(client, platform, sid, _users(client, platform, sid)[0]["id"]).json()["access_token"])
    student = client.post(f"{API}/students", json={"name": "Ana"}, headers=headers)
    assert student.status_code == 201, student.text
    history = client.get(f"{API}/students/{student.json()['id']}/history", headers=headers).json()
    assert history[0]["user_name"] == "Dona (plataforma: Root)"


def test_every_impersonation_is_logged_centrally(client, platform, admin):
    sid = _studio_id(client, platform)
    user = _users(client, platform, sid)[0]
    _impersonate(client, platform, sid, user["id"])
    _impersonate(client, platform, sid, user["id"])
    with central_session() as db:
        logs = db.scalars(select(ImpersonationLog)).all()
    assert len(logs) == 2
    first = logs[0]
    assert (first.platform_user_name, first.studio_slug, first.as_user_name, first.as_role) == (
        "Root",
        "alpha",
        "Dona",
        "admin",
    )


def test_passwords_cannot_be_changed_while_impersonating(client, platform, admin):
    bia = _add_teacher_user(client, admin)
    sid = _studio_id(client, platform)
    dona = next(u for u in _users(client, platform, sid) if u["role"] == "admin")
    headers = _as(_impersonate(client, platform, sid, dona["id"]).json()["access_token"])
    change = {"current_password": "secret123", "new_password": "outra-senha-1"}
    assert client.post(f"{API}/auth/me/password", json=change, headers=headers).status_code == 403
    assert client.patch(f"{API}/users/{bia['id']}", json={"password": "outra-senha-1"}, headers=headers).status_code == 403
    # outras edições de usuário continuam permitidas
    assert client.patch(f"{API}/users/{bia['id']}", json={"name": "Bia Souza"}, headers=headers).status_code == 200


def test_only_the_platform_can_impersonate(client, platform, admin):
    sid = _studio_id(client, platform)
    user_id = _users(client, platform, sid)[0]["id"]
    url = f"{API}/platform/studios/{sid}/impersonate"
    assert client.post(url, json={"user_id": user_id}, headers=admin).status_code == 401
    assert client.post(url, json={"user_id": user_id}).status_code == 401
    assert client.get(f"{API}/platform/studios/{sid}/users", headers=admin).status_code == 401


def test_cannot_impersonate_unknown_inactive_or_foreign_users(client, platform, admin):
    make_studio(client, platform, "beta")
    alpha, beta = _studio_id(client, platform, "alpha"), _studio_id(client, platform, "beta")
    assert _impersonate(client, platform, alpha, 9999).status_code == 404  # usuário inexistente
    assert _impersonate(client, platform, 9999, 1).status_code == 404  # estúdio inexistente

    bia = _add_teacher_user(client, admin)
    assert client.patch(f"{API}/users/{bia['id']}", json={"is_active": False}, headers=admin).status_code == 200
    assert _impersonate(client, platform, alpha, bia["id"]).status_code == 404  # inativo

    # o id de um usuário de alpha não serve em beta: a busca é no banco do estúdio escolhido
    ze = _add_teacher_user(client, admin, "Ze")
    assert ze["id"] not in {u["id"] for u in _users(client, platform, beta)}  # beta só tem o admin dele
    assert _impersonate(client, platform, beta, ze["id"]).status_code == 404


def test_inactive_studio_cannot_be_viewed(client, platform, admin):
    sid = _studio_id(client, platform)
    user_id = _users(client, platform, sid)[0]["id"]
    assert client.patch(f"{API}/platform/studios/{sid}", json={"is_active": False}, headers=platform).status_code == 200
    assert _impersonate(client, platform, sid, user_id).status_code == 403


def test_token_dies_when_the_platform_user_is_deactivated(client, platform, admin):
    sid = _studio_id(client, platform)
    headers = _as(_impersonate(client, platform, sid, _users(client, platform, sid)[0]["id"]).json()["access_token"])
    assert client.get(f"{API}/students", headers=headers).status_code == 200
    with central_session() as db:
        db.scalar(select(PlatformUser)).is_active = False
        db.commit()
    assert client.get(f"{API}/students", headers=headers).status_code == 401


def test_impersonation_token_is_short_lived(client, platform, admin):
    sid = _studio_id(client, platform)
    token = _impersonate(client, platform, sid, _users(client, platform, sid)[0]["id"]).json()["access_token"]
    claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    remaining = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(timezone.utc)
    minutes = settings.impersonation_expire_minutes
    assert timedelta(minutes=minutes - 2) < remaining <= timedelta(minutes=minutes)
    assert remaining < timedelta(minutes=settings.access_token_expire_minutes)
