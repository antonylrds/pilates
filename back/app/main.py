from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routes import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Gestão de estúdios de pilates (multitenant: um banco por estúdio). "
    "Salas, turmas, alunos, professores, planos, chamada, reposições e remuneração de professores.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, _exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Operação conflita com dados existentes (registro duplicado ou referência inválida)"},
    )


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_prefix)
