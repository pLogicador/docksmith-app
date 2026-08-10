from fastapi import APIRouter, Depends, HTTPException

from .. import auth, sessions
from ..bootstrap import ScrapingService
from ..logging_config import get_logger
from ..resource_estimate import resource_estimate
from ..schemas import ScrapeRequest, ScrapeResponse, SessionCollectionInfo, SessionStatusResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def session_status(
    session_id: str,
    user: dict = Depends(auth.get_current_user),
) -> SessionStatusResponse:
    user_id = user["user"].get("id")
    session = sessions.get_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou expirada.")
    return SessionStatusResponse(
        session_id=session_id,
        collections=[
            SessionCollectionInfo(name=name, document_count=len(docs))
            for name, docs in session["collections"].items()
        ],
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(
    payload: ScrapeRequest,
    user: dict = Depends(auth.get_current_user),
) -> ScrapeResponse:
    user_id = user["user"].get("id")
    session_id, session = sessions.get_or_create_session(payload.session_id, user_id)

    logger.info("Scraping iniciado: url=%s max_depth=%s", payload.url, payload.max_depth)
    scraper = ScrapingService(max_depth=payload.max_depth, concurrency=payload.concurrency)
    result = await scraper.scrape_website_async(payload.url)

    if not result["success"]:
        logger.warning("Scraping falhou: url=%s erro=%s", payload.url, result["error"])
        raise HTTPException(status_code=422, detail=result["error"])

    session["collections"][payload.collection_name] = result["data"]
    logger.info("Scraping concluído: url=%s documentos=%d", payload.url, len(result["data"]))

    estimate = resource_estimate(result["data"])
    if estimate["status"] in ("muito_grande", "bloqueado"):
        logger.warning(
            "Coleção '%s' com estimativa de recursos alta: status=%s chunks=%d estimativa_mb=%.1f",
            payload.collection_name, estimate["status"], estimate["estimated_chunks"], estimate["estimated_indexing_mb"],
        )

    return ScrapeResponse(
        session_id=session_id,
        collection_name=payload.collection_name,
        document_count=len(result["data"]),
        preview=[doc[:400] for doc in result["data"][:2]],
        resource_estimate=estimate,
    )
