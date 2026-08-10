from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from .. import auth, sessions
from ..bootstrap import RAGService
from ..logging_config import get_logger
from ..providers import resolve_api_key
from ..resource_estimate import resource_estimate
from ..schemas import ChatRequest, ChatResponse, SourceExcerpt

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: dict = Depends(auth.get_current_user),
) -> ChatResponse:
    user_id = user["user"].get("id")
    session = sessions.get_session(payload.session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão expirada. Refaça a extração.")
    if payload.collection_name not in session["collections"]:
        raise HTTPException(status_code=404, detail="Coleção não encontrada nesta sessão.")

    provider = (payload.provider or "groq").lower()
    resolved_key = resolve_api_key(provider, payload.api_key)
    if not resolved_key:
        raise HTTPException(status_code=400, detail="Informe uma chave de API para este provedor.")

    # Só reindexa (etapa cara: embeddings + FAISS) quando a coleção ou o
    # modelo mudam — mesma lógica de "recarregar ao trocar de coleção" que
    # docksmith/presentation/chat.py já usa.
    signature = (payload.collection_name, provider, payload.model, bool(payload.api_key), payload.depth)
    if session["rag_service"] is None or session.get("loaded_signature") != signature:
        docs = session["collections"][payload.collection_name]
        estimate = resource_estimate(docs)
        if estimate["status"] == "bloqueado" and not payload.confirm_large_collection:
            logger.warning(
                "Indexação bloqueada por estimativa de memória: coleção='%s' chunks=%d estimativa_mb=%.1f disponivel_mb=%.1f",
                payload.collection_name, estimate["estimated_chunks"], estimate["estimated_indexing_mb"],
                estimate["available_memory_mb"],
            )
            raise HTTPException(
                status_code=413,
                detail={
                    "message": "Esta coleção pode exigir mais memória do que a instância tem disponível com segurança.",
                    "resource_estimate": estimate,
                    "requires_confirmation": True,
                },
            )
        logger.info(
            "Indexando coleção '%s': provider=%s model=%s depth=%s",
            payload.collection_name, provider, payload.model, payload.depth,
        )
        rag_service = RAGService()
        docs = session["collections"][payload.collection_name]
        ok = await run_in_threadpool(
            rag_service.load_collection,
            docs,
            None,
            provider,
            payload.model,
            resolved_key,
            payload.depth,
        )
        if not ok:
            logger.error("Falha ao indexar coleção '%s' (provider=%s)", payload.collection_name, provider)
            raise HTTPException(status_code=500, detail="Falha ao indexar a coleção.")
        session["rag_service"] = rag_service
        session["loaded_signature"] = signature

    result = await run_in_threadpool(session["rag_service"].ask_question_with_sources, payload.question)
    logger.info(
        "Chat respondido: coleção=%s provider=%s fontes=%d",
        payload.collection_name, provider, len(result["sources"]),
    )

    return ChatResponse(
        answer=result["answer"],
        sources=[SourceExcerpt(**s) for s in result["sources"]],
        collection_name=payload.collection_name,
        provider=provider,
        model=payload.model or "",
    )
