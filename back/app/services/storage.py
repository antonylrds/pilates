"""Armazenamento de arquivos (laudos dos alunos) atrás de uma interface única.

- ``local``: pasta no disco do servidor (``STORAGE_LOCAL_ROOT``); serve para desenvolvimento e para um único servidor.
- ``s3``: qualquer serviço compatível com S3 (AWS S3, Cloudflare R2, Backblaze B2, MinIO). Requer ``uv sync --extra s3``.

Os arquivos nunca são públicos: o download passa pela API, que checa login e permissão. Trocar de backend
é só configuração; rotas, front e mobile não mudam.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings

CHUNK = 64 * 1024


class Storage(Protocol):
    def save(self, key: str, data: BinaryIO, content_type: str) -> None: ...

    def open(self, key: str) -> Iterator[bytes]: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:  # a chave nunca deve sair da raiz
            raise ValueError("Chave de arquivo inválida")
        return path

    def save(self, key: str, data: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            while chunk := data.read(CHUNK):
                out.write(chunk)

    def open(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)

        def stream() -> Iterator[bytes]:
            with path.open("rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk

        return stream()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Backend s3 requer: uv sync --extra s3") from exc
        self.bucket = settings.storage_s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_s3_endpoint_url,
            region_name=settings.storage_s3_region,
            aws_access_key_id=settings.storage_s3_access_key,
            aws_secret_access_key=settings.storage_s3_secret_key,
        )

    def save(self, key: str, data: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={"ContentType": content_type})

    def open(self, key: str) -> Iterator[bytes]:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except self.client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        return body.iter_chunks(CHUNK)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_local_root)
