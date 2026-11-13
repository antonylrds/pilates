"""Documentos do aluno (laudos, exames): envio, listagem, download e exclusão.

O arquivo fica no armazenamento (`app.services.storage`) e nunca é público: o download passa por aqui,
com login. Admin e professores consultam e baixam; só o admin envia e apaga.
"""

import re
import tempfile
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import Admin, Staff, get_or_404
from app.core.config import settings
from app.models.tenant import Student, StudentDocument
from app.schemas.documents import StudentDocumentRead, StudentDocumentUpdate
from app.services import audit
from app.services.storage import get_storage

router = APIRouter(prefix="/students/{student_id}/documents", tags=["documents"])

# Tipos aceitos, conferidos pelo conteúdo (assinatura do arquivo) e não pelo nome ou pelo tipo informado.
SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
CHUNK = 64 * 1024


def _student(ctx, student_id: int) -> Student:
    return get_or_404(ctx.db, Student, student_id, "Aluno")


def _document(ctx, student_id: int, document_id: int) -> StudentDocument:
    document = get_or_404(ctx.db, StudentDocument, document_id, "Documento")
    if document.student_id != student_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado")
    return document


def _clean_filename(name: str | None) -> str:
    name = (name or "arquivo").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "arquivo")[:255]


@router.get("", response_model=list[StudentDocumentRead], summary="Lista os documentos do aluno")
def list_documents(student_id: int, ctx: Staff):
    _student(ctx, student_id)
    return ctx.db.scalars(
        select(StudentDocument)
        .where(StudentDocument.student_id == student_id)
        .order_by(StudentDocument.created_at.desc(), StudentDocument.id.desc())
    ).all()


@router.post(
    "",
    response_model=StudentDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Envia um documento (PDF, JPG ou PNG) para a ficha do aluno",
    description="Multipart: `file` (obrigatório) e `description` (opcional). Tamanho máximo em "
    "`STORAGE_MAX_UPLOAD_MB` (padrão 10 MB). O tipo é verificado pelo conteúdo do arquivo.",
)
def upload_document(
    student_id: int,
    ctx: Admin,
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=500)] = None,
):
    student = _student(ctx, student_id)
    limit = settings.storage_max_upload_mb * 1024 * 1024
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as buffer:
        size = 0
        while chunk := file.file.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise HTTPException(
                    413,
                    f"Arquivo maior que o limite de {settings.storage_max_upload_mb} MB",
                )
            buffer.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")
        buffer.seek(0)
        head = buffer.read(16)
        content_type = next((mime for magic, mime in SIGNATURES if head.startswith(magic)), None)
        if content_type is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de arquivo não permitido. Envie PDF, JPG ou PNG.")
        buffer.seek(0)

        storage = get_storage()
        key = f"{ctx.studio.slug}/students/{student.id}/{uuid.uuid4().hex}"
        storage.save(key, buffer, content_type)

    document = StudentDocument(
        student_id=student.id,
        filename=_clean_filename(file.filename),
        content_type=content_type,
        size=size,
        storage_key=key,
        description=(description or "").strip() or None,
        uploaded_by_id=ctx.user.id,
        uploaded_by_name=ctx.actor_name,
    )
    try:
        ctx.db.add(document)
        ctx.db.flush()
        audit.log(ctx, student.id, audit.Action.DOCUMENT_ADDED, f"Documento anexado: {document.filename}")
        ctx.db.commit()
    except Exception:
        ctx.db.rollback()
        storage.delete(key)  # não deixa arquivo órfão se o registro falhar
        raise
    return document


@router.patch(
    "/{document_id}",
    response_model=StudentDocumentRead,
    summary="Altera a descrição do documento (também depois do envio)",
)
def update_document(student_id: int, document_id: int, data: StudentDocumentUpdate, ctx: Admin):
    _student(ctx, student_id)
    document = _document(ctx, student_id, document_id)
    document.description = (data.description or "").strip() or None
    ctx.db.commit()
    return document


@router.get("/{document_id}/download", summary="Baixa o documento (exige login; o acesso é registrado no histórico)")
def download_document(student_id: int, document_id: int, ctx: Staff):
    _student(ctx, student_id)
    document = _document(ctx, student_id, document_id)
    try:
        stream = get_storage().open(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado no armazenamento")
    # Laudo é dado de saúde (LGPD): todo acesso fica registrado (quem e quando) e, sem o registro, não há acesso.
    audit.log(ctx, student_id, audit.Action.DOCUMENT_ACCESSED, f"Documento acessado: {document.filename}")
    ctx.db.commit()
    return StreamingResponse(
        stream,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}",
            "Content-Length": str(document.size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Apaga o documento")
def delete_document(student_id: int, document_id: int, ctx: Admin):
    _student(ctx, student_id)
    document = _document(ctx, student_id, document_id)
    key, filename = document.storage_key, document.filename
    ctx.db.delete(document)
    audit.log(ctx, student_id, audit.Action.DOCUMENT_REMOVED, f"Documento removido: {filename}")
    ctx.db.commit()
    get_storage().delete(key)
