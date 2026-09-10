import time

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from .. import auth, config, rate_limit, sessions
from ..bootstrap import RAGService
from ..index_cache import evict_to_fit, total_indexed_chunks
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
    rate_limit.check_rate_limit(user_id, "chat")
    session = sessions.get_session(payload.session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão expirada. Refaça a extração.")

    # Multicontexto (Fase H, 2026-09-10) -- `collection_names` (1-3 nomes,
    # teto validado pelo schema) tem precedência sobre `collection_name`
    # pra decidir QUAIS coleções combinar; ausente/vazio = modo de sempre
    # (só `collection_name`, `names == [payload.collection_name]`, ZERO
    # mudança de comportamento pra quem nunca soube que este campo existe).
    names = payload.collection_names if payload.collection_names else [payload.collection_name]
    is_multi = len(names) > 1
    missing = [name for name in names if name not in session["collections"]]
    if missing:
        # Mensagem genérica (idêntica à de sempre) só quando o chamador
        # nem usou `collection_names` -- preserva o texto exato do modo
        # single pra qualquer chamador antigo. Quando `collection_names`
        # foi de fato usado, nomear qual(is) falta(m) é mais útil (o
        # usuário não saberia dizer qual das 2-3 coleções pedidas sumiu).
        detail = (
            f"Coleção(ões) não encontrada(s) nesta sessão: {', '.join(missing)}."
            if payload.collection_names
            else "Coleção não encontrada nesta sessão."
        )
        raise HTTPException(status_code=404, detail=detail)

    provider = (payload.provider or "groq").lower()
    resolved_key = resolve_api_key(provider, payload.api_key)
    if not resolved_key:
        raise HTTPException(status_code=400, detail="Informe uma chave de API para este provedor.")

    # Cache LRU por sessão (Fase E, 2026-09-10) -- `loaded_indices` pode
    # ter várias coleções residentes ao mesmo tempo agora (antes, só 1
    # slot fixo); só reindexa (etapa cara: embeddings + FAISS) quando a
    # signature exata (coleção(ões) + provider + modelo + presença de
    # chave própria + profundidade) não está no cache, seja porque é a 1ª
    # vez ou porque foi evictada. Em modo multicontexto, a signature usa
    # uma TUPLA ordenada de nomes (não uma string) -- `index_cache.
    # invalidate_collection` já sabe procurar dentro dela (ver Fase E).
    loaded_indices = session.setdefault("loaded_indices", {})
    combined_name = tuple(sorted(names)) if is_multi else names[0]
    signature = (combined_name, provider, payload.model, bool(payload.api_key), payload.depth)
    was_cached = signature in loaded_indices

    if not was_cached:
        if is_multi:
            # Concatena docs/labels/estrutura das N coleções, na ordem
            # pedida (não a ordenada de `combined_name`, que é só pra
            # chave de cache determinística) -- a busca híbrida sobre o
            # índice combinado ainda só recupera top-k chunks relevantes,
            # exatamente como 1 coleção só; combinar fontes muda de ONDE o
            # contexto pode vir, nunca quanto contexto é enviado por
            # pergunta (princípio "nunca documento inteiro pro LLM"
            # continua valendo, reaproveitado sem lógica nova).
            docs: list[str] = []
            source_labels: list[str] = []
            structure_metadata: list[dict] = []
            for name in names:
                name_docs = session["collections"][name]
                name_labels = session.get("collection_labels", {}).get(name)
                name_structure = session.get("collection_structure", {}).get(name)
                docs.extend(name_docs)
                # Rótulo sempre prefixado pelo nome da coleção de origem em
                # modo multi (diferente do modo single, que deixa
                # `load_collection` aplicar seu próprio default
                # "documento_{i}") -- sem isso, 2 coleções sem rótulo
                # próprio (ex.: raspadas por URL) combinadas teriam
                # "documento_0"/"documento_1" repetidos e indistinguíveis
                # nas citações, perdendo a proveniência que §11 exige.
                source_labels.extend(
                    name_labels if name_labels else [f"{name} - documento_{i}" for i in range(len(name_docs))]
                )
                structure_metadata.extend(
                    name_structure
                    if name_structure
                    else [{"chapter": None, "section": None, "page_start": None, "page_end": None} for _ in name_docs]
                )
        else:
            docs = session["collections"][names[0]]
            source_labels = session.get("collection_labels", {}).get(names[0])
            structure_metadata = session.get("collection_structure", {}).get(names[0])

        display_name = " + ".join(names)  # só pra log/mensagem -- nunca decide o que é carregado
        estimate = resource_estimate(docs)
        if estimate["status"] == "bloqueado" and not payload.confirm_large_collection:
            logger.warning(
                "Indexação bloqueada por estimativa de memória: coleção(ões)='%s' chunks=%d estimativa_mb=%.1f disponivel_mb=%.1f",
                display_name, estimate["estimated_chunks"], estimate["estimated_indexing_mb"],
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

        # Orçamento CUMULATIVO de chunks por sessão (Fase E, pedido
        # explícito do usuário, "OBSERVAÇÕES FINAIS") -- diferente do
        # bloqueio acima, que olha só ESTA coleção isolada: soma o que já
        # está residente no cache desta sessão + esta coleção nova, antes
        # de indexar. Mesmo padrão 413 + `requires_confirmation` já usado
        # acima, reaproveitado (não duplicado) -- `confirm_large_collection`
        # serve pros 2 casos.
        cumulative_chunks = total_indexed_chunks(loaded_indices) + estimate["estimated_chunks"]
        if cumulative_chunks > config.DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION and not payload.confirm_large_collection:
            logger.warning(
                "Indexação bloqueada por orçamento cumulativo de chunks: sessão=%s coleção(ões)='%s' "
                "chunks_pedidos=%d chunks_ja_residentes=%d teto=%d",
                payload.session_id, display_name, estimate["estimated_chunks"],
                total_indexed_chunks(loaded_indices), config.DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION,
            )
            raise HTTPException(
                status_code=413,
                detail={
                    "message": "O documento ultrapassa o limite de processamento desta sessão. Deseja continuar?",
                    "resource_estimate": estimate,
                    "requires_confirmation": True,
                },
            )

        # Cache LRU (Fase E) -- evicta a(s) entrada(s) menos usada(s)
        # recentemente até que memória E quantidade voltem a caber pra
        # esta coleção nova, ANTES de indexar. Nunca bloqueia a pergunta
        # atual, só derruba o que faz menos sentido manter residente
        # (mesmo princípio já usado nas cotas do R2).
        evict_to_fit(loaded_indices, incoming_mb=estimate["estimated_indexing_mb"])

        logger.info(
            "Indexando coleção(ões) '%s': provider=%s model=%s depth=%s",
            display_name, provider, payload.model, payload.depth,
        )
        # Checkpoint (Fase F): "embedding" cobre chunking+embeddings+
        # FAISS+BM25 num estado só -- `RAGService.load_collection` faz tudo
        # isso numa única chamada síncrona hoje, sem reportar progresso
        # intermediário (ver Fase G no plano: embeddings em lote é o que
        # abriria espaço pra um estado "chunking" genuinamente distinto,
        # reportando progresso lote a lote -- não implementado nesta fase).
        # Em modo multicontexto, todas as coleções combinadas compartilham
        # o mesmo índice -- todas recebem a mesma transição de estado
        # juntas (são indexadas/falham como uma unidade só).
        status_by_collection = session.setdefault("collection_status", {})
        for name in names:
            status_by_collection[name] = "embedding"
        rag_service = RAGService()
        # source_labels/structure_metadata já computados acima (bloco
        # if/else de `is_multi`) -- 2026-09-02: rótulo real por documento
        # quando a coleção veio de upload de PDF/DOCX (ex.: "arquivo.pdf -
        # página 3"). Ausente (None) pra coleções raspadas por URL em modo
        # single (`load_collection` cai no rótulo genérico `documento_{i}`
        # sozinho, comportamento 100% preservado); em modo multi, sempre
        # prefixado pelo nome da coleção de origem (ver acima).
        try:
            ok = await run_in_threadpool(
                rag_service.load_collection,
                docs,
                None,
                provider,
                payload.model,
                resolved_key,
                payload.depth,
                source_labels,
                structure_metadata,
                config.DOCSMITH_EMBEDDING_BATCH_SIZE,
            )
        except HTTPException:
            raise  # nunca deveria acontecer aqui, mas preserva o status/detail original se acontecer
        except Exception as exc:
            # Checkpoint (Fase F): qualquer exceção capturada aqui vira
            # "failed", visível até a PRÓXIMA pergunta real tentar de novo
            # -- nunca reescrita sozinha, nunca escondida, e sem nenhum
            # loop de retry automático (o usuário decide reenviar a
            # pergunta ou desistir, mesmo princípio já usado no bloqueio de
            # coleção grande acima).
            for name in names:
                status_by_collection[name] = "failed"
            logger.error("Falha ao indexar coleção(ões) '%s' (provider=%s): %s", display_name, provider, exc)
            raise HTTPException(status_code=500, detail="Falha ao indexar a coleção.") from exc
        if not ok:
            for name in names:
                status_by_collection[name] = "failed"
            logger.error("Falha ao indexar coleção(ões) '%s' (provider=%s)", display_name, provider)
            raise HTTPException(status_code=500, detail="Falha ao indexar a coleção.")
        # "indexed" -> "ready": 2 estados do enum (ver schemas.py::
        # CollectionStatus) escritos em sequência -- distintos em
        # princípio ("indexed" = a estrutura RAG existe; "ready" = já está
        # guardada no cache e disponível pra responder), mesmo que hoje
        # aconteçam nas mesmas poucas linhas de código.
        for name in names:
            status_by_collection[name] = "indexed"
        loaded_indices[signature] = {
            "rag_service": rag_service,
            "estimated_mb": estimate["estimated_indexing_mb"],
            "chunk_count": estimate["estimated_chunks"],
            "last_used": time.time(),
        }
        for name in names:
            status_by_collection[name] = "ready"
    else:
        loaded_indices[signature]["last_used"] = time.time()

    rag_service = loaded_indices[signature]["rag_service"]
    result = await run_in_threadpool(rag_service.ask_question_with_sources, payload.question)
    response_collection_name = " + ".join(names)
    logger.info(
        "Chat respondido: coleção(ões)=%s provider=%s fontes=%d cache=%s",
        response_collection_name, provider, len(result["sources"]), was_cached,
    )

    return ChatResponse(
        answer=result["answer"],
        sources=[SourceExcerpt(**s) for s in result["sources"]],
        collection_name=response_collection_name,
        provider=provider,
        model=payload.model or "",
        # intent (3ª rodada, §17): qual caminho de leitura/busca respondeu
        # esta pergunta -- ausente (None) pra chamadores antigos que não
        # esperam esse campo (Pydantic aceita default None sem quebrar
        # nada existente).
        intent=result.get("intent"),
        notice=result.get("notice"),
        # was_cached (Fase E, 2026-09-10): False quando esta pergunta
        # precisou (re)indexar a coleção agora -- 1ª vez OU porque tinha
        # sido evictada do cache LRU. O frontend usa isso pra decidir se
        # mostra "Pensando..." (já estava pronto) ou uma mensagem mais
        # transparente sobre reprocessamento.
        was_cached=was_cached,
    )
