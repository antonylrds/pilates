from pathlib import Path

from app.core.config import settings
from tests.conftest import API, login

PDF = b"%PDF-1.4\n% laudo de teste\n" + b"x" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 100


def _upload(client, headers, student, content=PDF, name="laudo.pdf", description=None, mime="application/pdf"):
    data = {"description": description} if description else {}
    return client.post(
        f"{API}/students/{student['id']}/documents", files={"file": (name, content, mime)}, data=data, headers=headers
    )


def test_upload_list_download_roundtrip_and_audit(client, studio):
    student = studio.student("Ana")
    r = _upload(client, studio.h, student, description="Laudo ortopédico", name="laudo ana.pdf")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert (doc["filename"], doc["content_type"], doc["size"], doc["description"]) == (
        "laudo ana.pdf", "application/pdf", len(PDF), "Laudo ortopédico")
    assert doc["uploaded_by_name"] == "Dona" and doc["created_at"]
    assert "storage_key" not in doc  # a chave interna não vaza

    listed = client.get(f"{API}/students/{student['id']}/documents", headers=studio.h).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    got = client.get(f"{API}/students/{student['id']}/documents/{doc['id']}/download", headers=studio.h)
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert "laudo%20ana.pdf" in got.headers["content-disposition"]
    assert "no-store" in got.headers["cache-control"]

    history = client.get(f"{API}/students/{student['id']}/history", headers=studio.h).json()
    assert any(h["action"] == "document_added" for h in history)


def test_type_is_checked_by_content_not_by_name_or_declared_type(client, studio):
    student = studio.student("Ana")
    r = _upload(client, studio.h, student, content=b"MZ\x90\x00 executavel", name="laudo.pdf", mime="application/pdf")
    assert r.status_code == 400 and "não permitido" in r.json()["detail"]
    r = _upload(client, studio.h, student, content=PNG, name="foto.bin", mime="application/octet-stream")
    assert r.status_code == 201 and r.json()["content_type"] == "image/png"
    assert _upload(client, studio.h, student, content=b"").status_code == 400


def test_size_limit(client, studio, monkeypatch):
    monkeypatch.setattr(settings, "storage_max_upload_mb", 1)
    student = studio.student("Ana")
    big = b"%PDF-" + b"0" * (1024 * 1024)
    r = _upload(client, studio.h, student, content=big)
    assert r.status_code == 413
    assert not list(Path(settings.storage_local_root).rglob("*")) or all(
        p.is_dir() for p in Path(settings.storage_local_root).rglob("*"))  # nada foi gravado


def test_filename_is_sanitized_and_never_used_as_path(client, studio):
    student = studio.student("Ana")
    r = _upload(client, studio.h, student, name="..\\..\\etc/passwd.pdf")
    assert r.status_code == 201
    assert r.json()["filename"] == "passwd.pdf"
    files = [p for p in Path(settings.storage_local_root).rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].is_relative_to(Path(settings.storage_local_root).resolve())
    assert files[0].parent.name == str(student["id"]) and files[0].parents[2].name == "alpha"


def test_description_can_be_added_edited_and_removed_after_upload(client, studio):
    student = studio.student("Ana")
    doc = _upload(client, studio.h, student).json()
    assert doc["description"] is None
    url = f"{API}/students/{student['id']}/documents/{doc['id']}"

    r = client.patch(url, json={"description": "  Laudo ortopédico 03/2026 "}, headers=studio.h)
    assert r.status_code == 200 and r.json()["description"] == "Laudo ortopédico 03/2026"
    listed = client.get(f"{API}/students/{student['id']}/documents", headers=studio.h).json()
    assert listed[0]["description"] == "Laudo ortopédico 03/2026"
    assert client.patch(url, json={"description": ""}, headers=studio.h).json()["description"] is None
    assert client.patch(url, json={"description": "x" * 501}, headers=studio.h).status_code == 422
    other = studio.student("Bia")
    assert client.patch(f"{API}/students/{other['id']}/documents/{doc['id']}", json={"description": "x"},
                        headers=studio.h).status_code == 404


def test_delete_removes_file_and_record(client, studio):
    student = studio.student("Ana")
    doc = _upload(client, studio.h, student).json()
    assert len([p for p in Path(settings.storage_local_root).rglob("*") if p.is_file()]) == 1

    r = client.delete(f"{API}/students/{student['id']}/documents/{doc['id']}", headers=studio.h)
    assert r.status_code == 204
    assert [p for p in Path(settings.storage_local_root).rglob("*") if p.is_file()] == []
    assert client.get(f"{API}/students/{student['id']}/documents", headers=studio.h).json() == []
    assert client.get(f"{API}/students/{student['id']}/documents/{doc['id']}/download", headers=studio.h).status_code == 404
    history = client.get(f"{API}/students/{student['id']}/history", headers=studio.h).json()
    assert any(h["action"] == "document_removed" for h in history)


def test_document_belongs_to_its_student(client, studio):
    ana, bia = studio.student("Ana"), studio.student("Bia")
    doc = _upload(client, studio.h, ana).json()
    assert client.get(f"{API}/students/{bia['id']}/documents/{doc['id']}/download", headers=studio.h).status_code == 404
    assert client.delete(f"{API}/students/{bia['id']}/documents/{doc['id']}", headers=studio.h).status_code == 404
    assert client.get(f"{API}/students/999/documents", headers=studio.h).status_code == 404


def test_teachers_can_view_and_download_but_not_upload_or_delete(client, studio):
    student = studio.student("Ana")
    doc = _upload(client, studio.h, student).json()
    prof = studio.teacher("Prof")
    studio.post("/users", {"name": "Prof", "email": "prof@alpha.com", "password": "secret123", "role": "teacher",
                           "teacher_id": prof["id"]})
    teacher = login(client, "alpha", "prof@alpha.com")

    assert len(client.get(f"{API}/students/{student['id']}/documents", headers=teacher).json()) == 1
    got = client.get(f"{API}/students/{student['id']}/documents/{doc['id']}/download", headers=teacher)
    assert got.status_code == 200 and got.content == PDF
    assert _upload(client, teacher, student).status_code == 403
    assert client.patch(f"{API}/students/{student['id']}/documents/{doc['id']}", json={"description": "x"},
                        headers=teacher).status_code == 403
    assert client.delete(f"{API}/students/{student['id']}/documents/{doc['id']}", headers=teacher).status_code == 403


def test_requires_login_and_isolates_studios(client, platform, studio):
    from tests.conftest import make_studio

    student = studio.student("Ana")
    doc = _upload(client, studio.h, student).json()
    url = f"{API}/students/{student['id']}/documents/{doc['id']}/download"
    assert client.get(url).status_code == 401

    other = make_studio(client, platform, "beta")
    assert client.get(url, headers=other).status_code == 404  # outro estúdio não enxerga (aluno não existe lá)
