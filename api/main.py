import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config, sessions
from .logging_config import setup as setup_logging, get_logger
from .routers import chat, health, models, scrape

setup_logging()
logger = get_logger(__name__)


# Achado real, ao vivo em produção (2026-09-01): sessions._cleanup_expired_locked
# só rodava de forma reativa (dentro de create_session()/get_session()) — sem
# tráfego novo, sessões vencidas ficavam presas na memória até QUALQUER
# usuário aparecer e reativar a limpeza, dando a impressão de vazamento
# contínuo de RAM em produção mesmo com o TTL funcionando. Este loop garante
# a mesma limpeza sozinha, independente de tráfego — puramente aditivo,
# nenhum comportamento de sessão/TTL muda pra quem está de fato usando o app.
async def _session_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(config.SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            before = sessions.cleanup_expired()
            logger.info("Faxina periódica de sessões: %d sessão(ões) antes da limpeza", before)
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
app.include_router(chat.router)
