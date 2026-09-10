import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import config, r2_storage, sessions
from .logging_config import setup as setup_logging, get_logger
from .routers import chat, documents, health, models, scrape

setup_logging()
logger = get_logger(__name__)


# Achado real, ao vivo em produção (2026-09-01): sessions._cleanup_expired_locked
# só rodava de forma reativa (dentro de create_session()/get_session()) — sem
# tráfego novo, sessões vencidas ficavam presas na memória até QUALQUER
# usuário aparecer e reativar a limpeza, dando a impressão de vazamento
# contínuo de RAM em produção mesmo com o TTL funcionando. Este loop garante
# a mesma limpeza sozinha, independente de tráfego — puramente aditivo,
# nenhum comportamento de sessão/TTL muda pra quem está de fato usando o app.
#
# 2026-09-02 (4ª rodada): também apaga, best-effort, os objetos R2 de cada
# sessão que expira (ver api/r2_storage.py) -- "documentos são armazenamento
# de trabalho da sessão atual, não uma biblioteca permanente entre sessões".
# `run_in_threadpool` porque `delete_session_objects` é uma chamada de rede
# síncrona (boto3) -- sem isso, ela bloquearia o event loop inteiro do
# processo (única instância, sem escalar horizontalmente, ver
# docs/09-deploy.md) pelo tempo da chamada ao R2.
async def _session_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(config.SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            before, removed = sessions.cleanup_expired_with_details()
            logger.info("Faxina periódica de sessões: %d sessão(ões) antes da limpeza", before)
            if removed and r2_storage.is_configured():
                for item in removed:
                    await run_in_threadpool(
                        r2_storage.delete_session_objects,
                        user_id=item["user_id"],
                        session_id=item["session_id"],
                    )
        except Exception:
            logger.exception("Falha na faxina periódica de sessões (não interrompe o loop)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Docksmith API iniciando — Groq padrão %s, CORS origins=%s",
        "configurado" if config.GROQ_API_KEY else "NÃO configurado",
        config.CORS_ORIGINS,
    )
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    cleanup_task.cancel()
    logger.info("Docksmith API encerrando")


app = FastAPI(
    title="Docksmith API",
    description="Camada de API fina sobre o motor Python do Docksmith.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # /health fica de fora pra não poluir o log com checagens de infraestrutura.
    if request.url.path == "/health":
        return await call_next(request)
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s -> %d (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(health.router)
app.include_router(models.router)
app.include_router(scrape.router)
app.include_router(documents.router)
app.include_router(chat.router)
