from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StudentDocumentUpdate(BaseModel):
    description: str | None = Field(None, max_length=500, description="Vazio remove a descrição")


class StudentDocumentRead(ORMModel):
    id: int
    student_id: int
    filename: str = Field(description="Nome original do arquivo")
    content_type: str
    size: int = Field(description="Tamanho em bytes")
    description: str | None
    uploaded_by_name: str = Field(description="Quem enviou")
    created_at: datetime = Field(description="Quando foi enviado")
