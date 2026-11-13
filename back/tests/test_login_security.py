"""Segurança do login: limite de tentativas, resposta uniforme e segredos de produção."""

import pytest
from pydantic import ValidationError

from app.core.config import DEV_PLATFORM_ADMIN_PASSWORD, DEV_SECRET_KEY, Settings, settings
from app.core import security
from tests.conftest import API

GOOD_KEY = "k" * 48
GOOD_PASSWORD = "uma-senha-forte-123"


def _login(client, slug="alpha", email="admin@alpha.com", password="errada-errada"):
    return client.post(f"{API}/auth/login", json={"studio": slug, "email": email, "password": password})


# ---------- Segredos de produção ----------
def test_production_refuses_development_secrets():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, environment="production")
    message = str(exc.value)
    assert "SECRET_KEY" in message and "PLATFORM_ADMIN_PASSWORD" in message


def test_production_requires_long_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, environment="production", secret_key="curta", platform_admin_password=GOOD_PASSWORD)


def test_production_accepts_real_secrets_and_dev_accepts_defaults():
    prod = Settings(_env_file=None, environment="production", secret_key=GOOD_KEY, platform_admin_password=GOOD_PASSWORD)
    assert prod.environment == "production"
    dev = Settings(_env_file=None)
    assert (dev.secret_key, dev.platform_admin_password) == (DEV_SECRET_KEY, DEV_PLATFORM_ADMIN_PASSWORD)


# ---------- Limite de tentativas ----------
def test_studio_login_locks_after_repeated_failures(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    for _ in range(3):
        assert _login(client).status_code == 401
    blocked = _login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # mesmo com a senha certa, enquanto durar o bloqueio
    assert _login(client, password="secret123").status_code == 429


def test_success_resets_the_counter(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    for _ in range(2):
        assert _login(client).status_code == 401
    assert _login(client, password="secret123").status_code == 200
    for _ in range(2):  # recomeça do zero
        assert _login(client).status_code == 401


def test_lock_is_per_account_not_global(client, admin, monkeypatch):
    """Errar a senha de uma conta não bloqueia outras contas do mesmo IP."""
    monkeypatch.setattr(settings, "login_max_attempts", 2)
    for _ in range(2):
        assert _login(client, email="outro@alpha.com").status_code == 401
    assert _login(client, email="outro@alpha.com").status_code == 429
    assert _login(client, password="secret123").status_code == 200


def test_ip_limit_covers_guessing_many_accounts(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts_per_ip", 4)
    for n in range(4):
        assert _login(client, email=f"alvo{n}@alpha.com").status_code == 401
    assert _login(client, email="alvo99@alpha.com").status_code == 429


def test_platform_login_is_limited_too(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts", 2)
    body = {"email": "root@test.com", "password": "errada-errada"}
    for _ in range(2):
        assert client.post(f"{API}/platform/auth/login", json=body).status_code == 401
    assert client.post(f"{API}/platform/auth/login", json=body).status_code == 429


# ---------- Resposta uniforme ----------
def test_unknown_studio_user_and_wrong_password_look_the_same(client, admin):
    unknown_studio = _login(client, slug="nao-existe", password="secret123")
    unknown_user = _login(client, email="ninguem@alpha.com")
    wrong_password = _login(client)
    assert {r.status_code for r in (unknown_studio, unknown_user, wrong_password)} == {401}
    assert unknown_studio.json() == unknown_user.json() == wrong_password.json()


def test_inactive_studio_is_only_revealed_with_correct_password(client, platform, admin):
    studio = client.get(f"{API}/platform/studios", headers=platform).json()[0]
    assert client.patch(f"{API}/platform/studios/{studio['id']}", json={"is_active": False}, headers=platform).status_code == 200
    assert _login(client).status_code == 401  # senha errada: não revela que está inativo
    assert _login(client, password="secret123").status_code == 403


def test_unknown_user_still_verifies_a_hash(client, admin, monkeypatch):
    """E-mail inexistente gasta o mesmo custo de hash (não revela quem tem conta pelo tempo de resposta)."""
    calls = []
    original = security.password_hash.verify
    monkeypatch.setattr(security.password_hash, "verify", lambda *a: calls.append(a) or original(*a))
    assert _login(client, email="ninguem@alpha.com").status_code == 401
    assert len(calls) == 1


# ---------- Senha mínima ----------
def test_password_minimum_length_is_8(client, admin, platform):
    body = {"name": "Prof", "email": "p@alpha.com", "role": "admin"}
    assert client.post(f"{API}/users", json={**body, "password": "1234567"}, headers=admin).status_code == 422
    assert client.post(f"{API}/users", json={**body, "password": "12345678"}, headers=admin).status_code == 201
