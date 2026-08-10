import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .logging_config import setup as setup_logging, get_logger
from .routers import chat, health, models, scrape

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Docksmith API iniciando — Groq padrão %s, CORS origins=%s",
        "configurado" if config.GROQ_API_KEY else "NÃO configurado",
        config.CORS_ORIGINS,
    )
    yield
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
