"""Conexões por estúdio (pool mínimo e descarte de ociosos), cache do cadastro de estúdios e migração em lote."""

import time

import pytest
from sqlalchemy import select

import app.cli as cli
from app.core.config import settings
from app.db import migrations
from app.db.engines import _make_engine, central_session, registry, tenant_url
from app.db.studio_cache import studio_cache
from app.models.central import Studio
from tests.conftest import API, make_studio


# ---------- Engines ----------
def _urls(*slugs):
    return [tenant_url(slug) for slug in slugs]


def test_idle_tenant_engines_are_disposed_but_central_is_kept():
    central = registry.get(settings.central_database_url)
    for url in _urls("a", "b"):
        registry.get(url)
    removed = registry.sweep(now=time.monotonic() + settings.tenant_engine_idle_seconds + 1)
    assert removed == 2
    assert registry.get(settings.central_database_url) is central


def test_recently_used_engines_stay_cached():
    first = registry.get(tenant_url("a"))
    assert registry.sweep() == 0
    assert registry.get(tenant_url("a")) is first


def test_engine_cache_is_capped_removing_least_recently_used(monkeypatch):
    monkeypatch.setattr(settings, "tenant_engine_max_cached", 2)
    urls = _urls("a", "b", "c", "d")
    for url in urls:
        registry.get(url)
    for age, url in enumerate(urls):  # a é o mais antigo, d o mais recente
        registry._last_used[url] = 1000.0 + age
    assert registry.sweep(now=1004.0) == 2
    assert set(registry._engines) == {urls[2], urls[3]} | {settings.central_database_url} & set(registry._engines)


def test_engine_with_open_connection_is_not_disposed():
    engine = registry.get(tenant_url("a"))
    with engine.connect():
        assert registry.sweep(now=time.monotonic() + 10_000) == 0
    assert registry.sweep(now=time.monotonic() + 10_000) == 1


def test_postgres_tenant_pool_is_small_and_central_pool_is_larger():
    pytest.importorskip("psycopg")
    tenant = _make_engine("postgresql+psycopg://u:p@localhost/pilates_x")
    central = _make_engine("postgresql+psycopg://u:p@localhost/pilates_central", central=True)
    assert (tenant.pool.size(), tenant.pool._max_overflow) == (settings.tenant_pool_size, settings.tenant_pool_max_overflow)
    assert central.pool.size() > tenant.pool.size()


# ---------- Cache do cadastro de estúdios ----------
def _deactivate_in_central(slug="alpha"):
    with central_session() as db:
        db.scalar(select(Studio).where(Studio.slug == slug)).is_active = False
        db.commit()


def test_studio_is_cached_between_requests(client, admin):
    assert client.get(f"{API}/studio", headers=admin).status_code == 200
    _deactivate_in_central()  # mudança "por fora" (outro processo): ainda não é vista
    assert client.get(f"{API}/studio", headers=admin).status_code == 200
    studio_cache.invalidate()
    assert client.get(f"{API}/studio", headers=admin).status_code == 403


def test_cache_can_be_disabled(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "studio_cache_seconds", 0)
    assert client.get(f"{API}/studio", headers=admin).status_code == 200
    _deactivate_in_central()
    assert client.get(f"{API}/studio", headers=admin).status_code == 403


def test_platform_deactivation_takes_effect_immediately(client, admin, platform):
    assert client.get(f"{API}/studio", headers=admin).status_code == 200  # aquece o cache
    studio_id = client.get(f"{API}/platform/studios", headers=platform).json()[0]["id"]
    assert client.patch(f"{API}/platform/studios/{studio_id}", json={"is_active": False}, headers=platform).status_code == 200
    assert client.get(f"{API}/studio", headers=admin).status_code == 403


def test_studio_settings_change_is_seen_immediately(client, admin):
    assert client.get(f"{API}/studio", headers=admin).json()["close_hour"] == 19
    assert client.patch(f"{API}/studio", json={"close_hour": 21}, headers=admin).status_code == 200
    assert client.get(f"{API}/studio", headers=admin).json()["close_hour"] == 21


# ---------- Migração em lote ----------
def test_migrate_continues_after_a_studio_fails(client, platform, monkeypatch, capsys):
    make_studio(client, platform, "alpha")
    make_studio(client, platform, "beta")
    original = migrations.migrate_tenant

    def flaky(slug):
        if slug == "alpha":
            raise RuntimeError("banco corrompido")
        original(slug)

    monkeypatch.setattr(migrations, "migrate_tenant", flaky)
    assert cli.migrate() == 1
    captured = capsys.readouterr()
    assert "Estúdio alpha FALHOU: RuntimeError: banco corrompido" in captured.out
    assert "Estúdio beta migrado." in captured.out
    assert "1 de 2 estúdios falharam: alpha" in captured.err


def test_migrate_succeeds_and_can_run_in_parallel_processes(client, platform, monkeypatch, capsys):
    for slug in ("alpha", "beta", "gama"):
        make_studio(client, platform, slug)
    # os processos filhos leem a configuração do ambiente
    monkeypatch.setenv("CENTRAL_DATABASE_URL", settings.central_database_url)
    monkeypatch.setenv("TENANT_DATABASE_URL_TEMPLATE", settings.tenant_database_url_template)
    assert cli.migrate(jobs=2) == 0
    out = capsys.readouterr().out
    assert all(f"Estúdio {slug} migrado." in out for slug in ("alpha", "beta", "gama"))
