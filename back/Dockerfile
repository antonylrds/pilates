# Imagem da API (multi-arch: roda em ARM64 no Oracle Cloud e em amd64).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
# A imagem é de produção: recusa subir com SECRET_KEY / senha de admin de desenvolvimento (veja app/core/config.py).
ENV ENVIRONMENT=production
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra postgres --extra s3

COPY . .
ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --system --uid 10001 app && mkdir -p /app/data && chown -R app /app/data
USER app

EXPOSE 8000
# Migra os bancos (central + estúdios), garante o usuário da plataforma e sobe a API.
CMD ["sh", "-c", "python -m app.cli migrate && python -m app.cli init && exec fastapi run app/main.py --host 0.0.0.0 --port 8000 --proxy-headers"]
