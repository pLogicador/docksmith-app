import os

from dotenv import load_dotenv

load_dotenv()

# "production" precisa ser definido explicitamente no host de produção
# (Railway/Render/etc). O default "development" é o que já funciona pra
# rodar localmente sem configurar nada além do que já era necessário.
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"


def _required_in_production(var_name: str, dev_default: str) -> str:
    """Usa o valor da env var se existir; em produção, falha alto e explícito
    se estiver ausente em vez de cair silenciosamente num default de
    localhost (que nunca existe fora do ambiente de dev)."""
    value = os.getenv(var_name)
    if value:
        return value
    if IS_PRODUCTION:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente em produção: {var_name}. "
            "Configure isso no ambiente de produção antes de subir o serviço."
        )
    return dev_default


# URL do subscription_access_api — mesma fonte da verdade usada pelo Hub e
# pelo Streamlit (docksmith/app.py lê essa mesma variável de forma
# independente, com seu próprio fallback — não alterado aqui).
API_BASE = _required_in_production("API_BASE", "http://localhost:8000")

# Chave padrão do Docksmith para o provedor Groq (usada quando o usuário não
# informa a própria). Sem default em nenhum ambiente: se faltar, só a opção
# "Groq sem chave" fica indisponível — o usuário ainda pode usar sua própria
# chave em qualquer provedor.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# TTL de sessão em memória (sem banco de dados / sem persistência).
SESSION_TTL_SECONDS = int(os.getenv("DOCKSMITH_SESSION_TTL_SECONDS", "3600"))

# Achado real, ao vivo em produção (2026-09-01): a limpeza de sessões
# vencidas (sessions._cleanup_expired_locked) só rodava de forma reativa —
# disparada dentro de create_session()/get_session(), nunca sozinha. Em
# tráfego de rajadas (uso concentrado seguido de período ocioso), a RAM
# ficava "presa" no último pico até QUALQUER usuário novo aparecer e
# reativar a limpeza — dando a impressão de vazamento contínuo mesmo com o
# TTL funcionando corretamente. Este intervalo controla uma faxina que
# roda sozinha em segundo plano (ver main.py), bem menor que o TTL pra
# garantir que a memória nunca fique presa por muito mais tempo que o TTL
# real, mesmo sem nenhum tráfego.
SESSION_CLEANUP_INTERVAL_SECONDS = int(os.getenv("DOCKSMITH_SESSION_CLEANUP_INTERVAL_SECONDS", "300"))

# Bypass só para desenvolvimento local (QA do frontend sem token real do
# Hub). Nunca deve ser "true" em produção — não existe na Vercel/Railway.
DEV_BYPASS_AUTH = os.getenv("DOCKSMITH_API_DEV_BYPASS_AUTH", "false").lower() == "true"
if IS_PRODUCTION and DEV_BYPASS_AUTH:
    raise RuntimeError(
        "DOCKSMITH_API_DEV_BYPASS_AUTH não pode ser 'true' quando ENVIRONMENT=production."
    )

# Limites de upload de documento (prompt-mestre "Docksmith" §12: "criar
# limites configuráveis por ambiente. Nunca codificar limites diretamente
# no código"). Aplicados em api/routers/documents.py -- 20MB/300 páginas
# são valores conservadores pra rodar numa instância pequena sem OCR (que
# ainda não existe nesta rodada, ver docksmith/service/document_loader.py).
#
# Teto absoluto por arquivo (2026-09-02, 5ª rodada -- revisado pra baixo,
# de 1GB pra 300MB, depois de pensar na capacidade real do R2 junto com o
# usuário). Um livro real, dentro do teto de 300 páginas já existente
# abaixo (DOCSMITH_MAX_PAGES), praticamente nunca chega perto de 300MB
# mesmo cheio de imagem -- um arquivo muito maior que isso quase sempre é
# um PDF escaneado em altíssima resolução, que o Docksmith não processa
# bem de qualquer forma (precisa de texto real extraível, não OCR -- ver
# document_loader.py). Nenhum valor de configuração, mesmo mal
# configurado, pode passar deste teto.
DOCSMITH_MAX_FILE_SIZE_MB_HARD_CAP = 300
DOCSMITH_MAX_FILE_SIZE_MB = min(
    int(os.getenv("DOCSMITH_MAX_FILE_SIZE_MB", "20")),
    DOCSMITH_MAX_FILE_SIZE_MB_HARD_CAP,
)
DOCSMITH_MAX_PAGES = int(os.getenv("DOCSMITH_MAX_PAGES", "300"))

# Armazenamento durável opcional em Cloudflare R2 (2026-09-02, 4ª rodada --
# resolve o achado "documentos ainda somem a cada reinício do servidor",
# registrado como pendência nas 2 rodadas anteriores). Ver
# docs/CONFIGURAR_R2.md para o passo a passo completo de configuração.
#
# Deliberadamente opcional em tempo de execução (nunca `_required_in_
# production`, nem em produção): sem estas 4 variáveis, `r2_storage.
# is_configured()` fica False e toda a camada vira no-op segura -- upload/
# chat continuam funcionando exatamente como sempre funcionaram. R2 é uma
# melhoria de durabilidade, nunca um pré-requisito pra a ferramenta
# funcionar.
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

# Override opcional de endpoint/região (2026-09-03 -- pesquisa confirmou que
# a Cloudflare exige cartão de crédito pra ativar o R2 mesmo no nível
# gratuito; Backblaze B2 é uma alternativa real, com nível gratuito
# equivalente/permanente e SEM exigir cartão, e fala a mesma API
# S3-compatível que este módulo já usa via boto3). Sem estas 2 variáveis,
# o comportamento é 100% idêntico a antes (endpoint derivado de
# R2_ACCOUNT_ID, região "auto" -- os valores certos pro Cloudflare R2).
# Setando as duas, o mesmo código (r2_storage.py, zero mudança de lógica)
# passa a falar com Backblaze B2 ou qualquer outro provedor S3-compatível
# -- só R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME continuam
# obrigatórias (conceitos universais de credencial S3: usam o Key ID/
# Application Key do B2 no lugar do Access Key/Secret do R2). Ver
# docs/CONFIGURAR_ARMAZENAMENTO.md para o passo a passo de cada provedor.
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_REGION = os.getenv("R2_REGION", "auto")

# Cotas de segurança do R2 (2026-09-02, 5ª rodada -- "pra nunca mandar
# 10GB pro R2"). O teto de 300MB por arquivo acima já reduz o pior caso de
# UM upload, mas não impede uma única conta de acumular vários uploads
# (a mesma pessoa enviando dezenas de arquivos, cada um dentro do teto
# individual) nem impede que MUITOS usuários diferentes, ao mesmo tempo,
# somem além do plano gratuito -- por isso 2 camadas adicionais, checadas
# em `api/r2_storage.py` ANTES de cada upload novo:
#
# 1) Cota por usuário: soma de tudo que uma única conta tem guardado no
#    R2 agora (todas as sessões ativas dela) nunca passa disso.
# 2) Cota global do bucket: soma de TUDO que está no bucket (todos os
#    usuários somados) nunca passa disso -- a rede de segurança final,
#    mesmo que muitas contas diferentes estejam ativas ao mesmo tempo.
#
# As duas seguem o mesmo princípio de sempre: nunca bloqueiam o upload em
# si (o documento continua sendo processado e indexado normalmente) --
# só pulam a cópia de segurança no R2 daquela vez específica, com um log
# claro do motivo. O padrão de 6GB pro bucket inteiro deixa 4GB de folga
# real abaixo do teto gratuito de 10GB (margem pra qualquer imprecisão de
# contagem e pra nunca chegar perto do limite de verdade).
R2_MAX_BYTES_PER_USER = int(os.getenv("DOCSMITH_R2_MAX_MB_PER_USER", "1024")) * 1024 * 1024
R2_MAX_TOTAL_BUCKET_BYTES = int(os.getenv("DOCSMITH_R2_MAX_MB_TOTAL_BUCKET", "6144")) * 1024 * 1024

# Fase E (evolução "livros grandes", 2026-09-10): teto real de RAM pros
# índices RAG residentes na memória de uma sessão -- antes desta fase só
# existia 1 slot fixo por sessão (session["rag_service"]), sem controle
# de memória real nem múltiplas coleções residentes ao mesmo tempo.
# Controla só o peso de índices/embeddings/estruturas RAG em memória,
# nunca o processo inteiro -- a margem de segurança pro resto do processo
# (FastAPI, workers, bibliotecas, SO) fica implícita no fato de que este
# teto é bem menor que a RAM real disponível, não uma tentativa de usar
# 100% da máquina. Aplicado em api/index_cache.py.
DOCSMITH_MAX_SESSION_INDEX_MB = int(os.getenv("DOCSMITH_MAX_SESSION_INDEX_MB", "800"))

# 2º controle independente do teto de memória acima (pedido explícito do
# usuário, "AJUSTES FINAIS"): mesmo havendo memória disponível, nunca
# mantém mais que N coleções residentes ao mesmo tempo por sessão --
# evita que muitas coleções pequenas (cada uma cabendo tranquilamente no
# teto de memória) se acumulem sem limite nenhum de quantidade. A
# evicção LRU (api/index_cache.py::evict_to_fit) dispara quando QUALQUER
# um dos 2 tetos é ultrapassado, o que vier primeiro.
DOCSMITH_MAX_CACHED_COLLECTIONS = int(os.getenv("DOCSMITH_MAX_CACHED_COLLECTIONS", "3"))

# Orçamento CUMULATIVO de chunks por sessão (pedido explícito do usuário,
# "OBSERVAÇÕES FINAIS") -- diferente do bloqueio de coleção grande já
# existente em api/resource_estimate.py (status "bloqueado"), que olha só
# UMA coleção isolada: este soma `estimated_chunks` de TODAS as coleções
# já residentes no cache desta sessão + a nova, ANTES de indexar --
# bloqueia com pedido de confirmação (mesmo padrão 413 já usado pra
# coleção grande isolada) em vez de indexar automaticamente. Default
# calibrado pra ficar coerente com DOCSMITH_MAX_SESSION_INDEX_MB acima
# (800MB / ~85KB por chunk, ver resource_estimate.BYTES_PER_CHUNK, dá
# margem folgada sem duplicar essa constante aqui).
DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION = int(os.getenv("DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION", "20000"))

# Fase G (evolução "livros grandes", 2026-09-10): tamanho do lote de
# chunks usado por RAGService.load_collection pra construir o índice
# FAISS aos poucos, em vez de `FAISS.from_documents(texts, embeddings)`
# de uma tacada só (docksmith/service/rag.py::_build_vector_store_in_
# batches) -- limita o pico de memória de vetores retidos simultaneamente
# antes de entrar no índice. Configurável (§12: "nunca codificar limites
# diretamente no código"), nunca lido direto por docksmith/service/rag.py
# (que fica livre de qualquer dependência de api/ -- mesmo princípio já
# usado por DOCSMITH_MAX_PAGES/document_loader.py: docksmith/service/*
# recebe configuração como parâmetro, api/ resolve o valor real do
# ambiente e repassa).
DOCSMITH_EMBEDDING_BATCH_SIZE = int(os.getenv("DOCSMITH_EMBEDDING_BATCH_SIZE", "100"))

# Rate limiting por usuário (prompt-mestre "Docksmith" §48) -- 0 desliga a
# categoria (nunca usar em produção, só testes/ambientes especiais). Chat
# tem limite mais alto que scrape/upload por ser a operação mais barata e
# mais frequente numa sessão normal de uso.
DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE = int(os.getenv("DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", "10"))
DOCSMITH_RATE_LIMIT_UPLOAD_PER_MINUTE = int(os.getenv("DOCSMITH_RATE_LIMIT_UPLOAD_PER_MINUTE", "10"))
DOCSMITH_RATE_LIMIT_CHAT_PER_MINUTE = int(os.getenv("DOCSMITH_RATE_LIMIT_CHAT_PER_MINUTE", "30"))

# Origens liberadas para chamar a API. Obrigatória em produção: sem isso, o
# navegador bloqueia por CORS todas as chamadas do frontend novo.
CORS_ORIGINS = [
    origin.strip()
    for origin in _required_in_production(
        "DOCKSMITH_API_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:5175",
    ).split(",")
    if origin.strip()
]
