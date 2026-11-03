from pathlib import Path

from app.core.config import settings
from app.db.engines import tenant_url
from tests.conftest import API, login, make_studio


def test_each_studio_has_its_own_database(client, platform):
    alpha = make_studio(client, platform, "alpha")
    beta = make_studio(client, platform, "beta-studio")

    client.post(f"{API}/students", json={"name": "Aluna do Alpha"}, headers=alpha)

    assert [s["name"] for s in client.get(f"{API}/students", headers=alpha).json()] == ["Aluna do Alpha"]
    assert client.get(f"{API}/students", headers=beta).json() == []

    # arquivos de banco separados
    for slug in ("alpha", "beta_studio"):
        path = tenant_url(slug).removeprefix("sqlite:///")
        assert Path(path).exists(), path
    assert "{slug}" in settings.tenant_database_url_template


def test_login_requires_matching_studio(client, platform):
    make_studio(client, platform, "alpha")
    make_studio(client, platform, "beta")
    r = client.post(f"{API}/auth/login", json={"studio": "beta", "email": "admin@alpha.com", "password": "secret123"})
    assert r.status_code == 401
    r = client.post(f"{API}/auth/login", json={"studio": "nao-existe", "email": "admin@alpha.com", "password": "x"})
    assert r.status_code == 401


def test_me_returns_user_and_studio(client, admin):
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert me["user"]["role"] == "admin"
    assert me["studio"]["slug"] == "alpha"
    assert me["studio"]["open_hour"] == 6 and me["studio"]["close_hour"] == 19


def test_inactive_studio_is_blocked(client, platform):
    headers = make_studio(client, platform, "alpha")
    studio_id = client.get(f"{API}/platform/studios", headers=platform).json()[0]["id"]
    client.patch(f"{API}/platform/studios/{studio_id}", json={"is_active": False}, headers=platform)
    assert client.get(f"{API}/students", headers=headers).status_code == 403
    r = client.post(f"{API}/auth/login", json={"studio": "alpha", "email": "admin@alpha.com", "password": "secret123"})
    assert r.status_code == 403


def test_tokens_are_not_interchangeable(client, platform, admin):
    assert client.get(f"{API}/platform/studios", headers=admin).status_code == 401
    assert client.get(f"{API}/students", headers=platform).status_code == 401


def test_duplicate_and_invalid_slug(client, platform):
    make_studio(client, platform, "alpha")
    body = {"name": "Outro", "slug": "alpha", "admin_name": "Admin","admin_email": "a@a.com", "admin_password": "secret123"}
    assert client.post(f"{API}/platform/studios", json=body, headers=platform).status_code == 409
    body["slug"] = "Invalid Slug!"
    assert client.post(f"{API}/platform/studios", json=body, headers=platform).status_code == 422


def test_teacher_user_permissions(client, admin):
    teacher = client.post(f"{API}/teachers", json={"name": "Bia"}, headers=admin).json()
    r = client.post(
        f"{API}/users",
        json={"name": "Bia", "email": "bia@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": teacher["id"]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    bia = login(client, "alpha", "bia@alpha.com")
    assert client.get(f"{API}/students", headers=bia).status_code == 200
    assert client.post(f"{API}/plans", json={"name": "X", "sessions_per_week": 1, "total_classes": 4, "price": "1"}, headers=bia).status_code == 403
    assert client.post(f"{API}/students", json={"name": "Novo"}, headers=bia).status_code == 403
