from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantBase, TimestampMixin


class StudentDocument(TenantBase, TimestampMixin):
    """Arquivo anexado à ficha do aluno (laudos, exames). O conteúdo fica no armazenamento de arquivos
    (`app.services.storage`); aqui ficam só os metadados e a chave do arquivo."""

    __tablename__ = "student_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_by_name: Mapped[str] = mapped_column(String(120))
