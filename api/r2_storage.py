"""Armazenamento durável (opcional) dos arquivos originais enviados por
upload, em Cloudflare R2 -- prompt-mestre "Docksmith", achado registrado
como pendência nas 2 rodadas anteriores desta sessão: "documentos ainda
somem a cada reinício do servidor" (api/sessions.py guarda tudo em
memória do processo, sem banco de dados nem disco -- ver o próprio
docstring desse arquivo). Vive em `api/` (não em `docksmith/service/`) de
propósito -- é infraestrutura de sessão/requisição (mesmo nível de
`api/sessions.py`/`api/rate_limit.py`), não lógica de RAG; mantém
`docksmith/service/` livre de qualquer dependência de `api/`, mesma
separação que `rag.py` já preserva (recebe config como parâmetro, nunca
lê variável de ambiente sozinho).

Por que R2 (pesquisado antes de escrever qualquer código, 2026-09-02):
camada gratuita real, permanente (não expira depois de 12 meses como a da
AWS) e generosa pro tamanho desta ferramenta -- 10GB de armazenamento por
mês, 1 milhão de operações de escrita e 10 milhões de leitura por mês,
ZERO custo de saída de dados (egress), confirmado na documentação oficial
da Cloudflare em 2026-09-02. O único ponto de atenção real encontrado na
pesquisa: a Cloudflare exige um cartão cadastrado pra *ativar* o produto
R2, mesmo que o uso nunca saia do nível gratuito.

Atualização (2026-09-03, pesquisa nova): esse cartão continua sendo
exigido hoje -- confirmado de novo, não presumido. Backblaze B2 foi
pesquisado como alternativa e é genuinamente equivalente pro tamanho desta
ferramenta: 10GB de armazenamento grátis e permanente, egress grátis até
3x a média mensal armazenada (bem acima do padrão de uso real de backup
efêmero deste módulo), chamadas de upload/listagem/leitura grátis pra
contas pay-as-you-go, API S3-compatível (mesmo boto3, zero mudança de
lógica aqui) -- e a própria página de cadastro do Backblaze afirma "no
credit card required". `R2_ENDPOINT_URL`/`R2_REGION` (config.py) são o que
permite trocar de provedor sem tocar em nenhuma linha deste arquivo. Ver
docs/CONFIGURAR_ARMAZENAMENTO.md pro passo a passo completo dos 2
provedores (Backblaze B2 recomendado por não exigir cartão; Cloudflare R2
documentado à parte em docs/CONFIGURAR_R2.md pra quem preferir/já tiver
cartão cadastrado).

Design deliberadamente tolerante a falha, do início ao fim: se as 4
variáveis de ambiente R2_* não estiverem configuradas
(`is_configured()` == False), toda função pública aqui vira um no-op
seguro -- upload/chat continuam funcionando exatamente como funcionavam
antes desta rodada, como se este arquivo nunca tivesse existido. O mesmo
vale se as variáveis existirem mas a chamada de rede falhar (timeout,
credencial errada, bucket incorreto): cada função pública captura a
exceção, loga, e devolve um valor "vazio" (None/[]/0) em vez de propagar
-- R2 é uma melhoria de durabilidade, nunca pode ser o motivo de um
upload ou uma pergunta falharem.

Os arquivos ficam sob a chave `docksmith/{hash(user_id)}/{session_id}/
{uuid_do_objeto}`, com o nome real do arquivo e da coleção guardados como
metadado do objeto (nunca no próprio caminho -- evita qualquer problema
de caractere especial/sanitização e mantém o caminho 100% opaco). O hash
do `user_id` (não o valor em si) compõe o prefixo por 2 motivos: (1) nunca
expor o identificador real do usuário num caminho de objeto, mesmo que o
bucket seja privado; (2) o mesmo hash, recomputado a partir do `user_id`
autenticado da requisição atual, funciona como verificação de posse na
restauração (ver `list_session_objects` abaixo) -- ninguém consegue
"herdar" os documentos de outra pessoa reaproveitando um `session_id`
antigo, porque o prefixo dele nunca vai bater com o hash calculado a
partir da identidade de quem está pedindo.

Todo objeto é apagado quando a sessão que o criou expira (mesmo TTL de
sempre, ver api/sessions.py + api/main.py) -- não é uma biblioteca
permanente de documentos entre sessões, é armazenamento de trabalho da
sessão atual, só sobrevivendo a um reinício/deploy do servidor no meio
dela. Isso mantém o uso real do R2 sempre dentro do nível gratuito,
nunca crescendo sem limite conforme o tráfego acumula.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from urllib.parse import quote, unquote

from . import config
from .logging_config import get_logger

logger = get_logger(__name__)

_OBJECT_KEY_PREFIX = "docksmith"
_client: Any = None


def is_configured() -> bool:
    """True quando há credencial+bucket, e um jeito de saber o endpoint --
    ou `R2_ACCOUNT_ID` (deriva o endpoint padrão do Cloudflare R2) ou
    `R2_ENDPOINT_URL` (endpoint explícito, usado pra Backblaze B2 ou
    qualquer outro provedor S3-compatível). Chamado antes de qualquer
    operação -- nunca tenta construir um client com credenciais
    parciais/ausentes."""
    return bool(
        config.R2_ACCESS_KEY_ID
        and config.R2_SECRET_ACCESS_KEY
        and config.R2_BUCKET_NAME
        and (config.R2_ACCOUNT_ID or config.R2_ENDPOINT_URL)
    )


def _get_client():
    """Client boto3 (S3-compatível -- R2 e Backblaze B2 expõem a mesma API)
    construído uma única vez (lazy singleton) e reaproveitado. `boto3.
    client(...)` em si não faz nenhuma chamada de rede -- só a 1ª operação
    real dispara a conexão, então criar o client aqui é seguro mesmo
    quando o armazenamento nunca chega a ser usado de fato numa execução
    do processo.

    `R2_ENDPOINT_URL` (se definido) sempre vence sobre o endpoint derivado
    de `R2_ACCOUNT_ID` -- é assim que Backblaze B2 (ou outro provedor)
    entra em cena sem precisar de nenhum código novo, só variáveis de
    ambiente diferentes (ver docs/CONFIGURAR_ARMAZENAMENTO.md)."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config as BotoConfig

        endpoint = config.R2_ENDPOINT_URL or f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            region_name=config.R2_REGION,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 2}),
        )
    return _client


def _user_hash(user_id) -> str:
    """Nunca usa o `user_id` real no caminho do objeto -- só um hash
    truncado, suficiente pra separar usuários entre si e verificar posse
    na restauração, sem nunca escrever a identidade real em nenhum lugar
    do armazenamento."""
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:24]


def _session_prefix(user_id, session_id: str) -> str:
    return f"{_OBJECT_KEY_PREFIX}/{_user_hash(user_id)}/{session_id}/"


def _user_prefix(user_id) -> str:
    """Prefixo de TODAS as sessões de um usuário (não só a atual) -- usado
    só pra somar quanto essa conta já tem guardado no R2 agora, antes de
    aceitar mais um upload (ver `_prefix_total_bytes`/cota por usuário
    abaixo)."""
    return f"{_OBJECT_KEY_PREFIX}/{_user_hash(user_id)}/"


def _prefix_total_bytes(client, prefix: str) -> int:
    """Soma o tamanho (`Size`, já devolvido pela própria listagem -- sem
    precisar de uma chamada extra por objeto) de tudo sob um prefixo.
    Simplificação conhecida e aceitável na escala real desta ferramenta:
    não pagina (`list_objects_v2` devolve até 1000 chaves por chamada) --
    o número real de objetos aqui é sempre pequeno (sessões expiram em 1h
    e são limpas, ver api/main.py), nunca chegando perto disso."""
    response = client.list_objects_v2(Bucket=config.R2_BUCKET_NAME, Prefix=prefix)
    return sum(item.get("Size", 0) for item in response.get("Contents", []))


def upload_raw_bytes(
    *, user_id, session_id: str, collection_name: str, filename: str, raw_bytes: bytes
) -> str | None:
    """Envia o arquivo original pro R2, best-effort. Devolve a chave do
    objeto em caso de sucesso, `None` em qualquer outro caso (R2 não
    configurado, cota excedida, ou a chamada falhou) -- nunca levanta
    exceção, e o chamador (api/routers/documents.py) nunca deve tratar
    `None` como erro do upload em si, só como "esta cópia de segurança
    não foi criada agora".

    2026-09-02, 5ª rodada ("nunca mandar 10GB pro R2"): antes de gravar,
    confirma 2 cotas de segurança (config.R2_MAX_BYTES_PER_USER/
    R2_MAX_TOTAL_BUCKET_BYTES) -- cota por usuário primeiro (mais barato
    de checar, e a causa mais provável em uso normal), cota global do
    bucket depois (rede de segurança final). As duas nunca bloqueiam o
    upload do documento em si -- só pulam esta cópia de segurança
    específica, com um log claro do motivo."""
    if not is_configured():
        return None
    try:
        client = _get_client()

        user_total = _prefix_total_bytes(client, _user_prefix(user_id))
        if user_total + len(raw_bytes) > config.R2_MAX_BYTES_PER_USER:
            logger.warning(
                "Backup R2 pulado: cota por usuário excedida (já usa %dB, arquivo tem %dB, limite %dB)",
                user_total, len(raw_bytes), config.R2_MAX_BYTES_PER_USER,
            )
            return None

        bucket_total = _prefix_total_bytes(client, f"{_OBJECT_KEY_PREFIX}/")
        if bucket_total + len(raw_bytes) > config.R2_MAX_TOTAL_BUCKET_BYTES:
            logger.warning(
                "Backup R2 pulado: cota global do bucket excedida (já usa %dB, arquivo tem %dB, limite %dB)",
                bucket_total, len(raw_bytes), config.R2_MAX_TOTAL_BUCKET_BYTES,
            )
            return None

        object_key = _session_prefix(user_id, session_id) + uuid.uuid4().hex
        client.put_object(
            Bucket=config.R2_BUCKET_NAME,
            Key=object_key,
            Body=raw_bytes,
            Metadata={
                "collection_name": quote(collection_name),
                "filename": quote(filename),
            },
        )
        logger.info(
            "Documento salvo no R2: sessão=%s coleção=%s tamanho=%dB",
            session_id, collection_name, len(raw_bytes),
        )
        return object_key
    except Exception:  # noqa: BLE001 -- R2 é durabilidade extra, nunca pode derrubar o upload
        logger.exception("Falha ao salvar documento no R2 (upload principal não é afetado)")
        return None


def list_session_objects(*, user_id, session_id: str) -> list[dict]:
    """Lista os objetos reais de uma sessão no R2, já com metadado
    decodificado (`collection_name`/`filename`). Usado na restauração:
    como o prefixo inclui o hash do `user_id` de quem está pedindo agora
    (não o de quando o objeto foi criado), um `session_id` reaproveitado
    por outra pessoa nunca encontra nada aqui -- devolve lista vazia, não
    erro, então o chamador trata igual a "sem nada pra restaurar"."""
    if not is_configured():
        return []
    try:
        client = _get_client()
        prefix = _session_prefix(user_id, session_id)
        response = client.list_objects_v2(Bucket=config.R2_BUCKET_NAME, Prefix=prefix)
        objects = []
        for item in response.get("Contents", []):
            key = item["Key"]
            head = client.head_object(Bucket=config.R2_BUCKET_NAME, Key=key)
            metadata = head.get("Metadata", {})
            objects.append(
                {
                    "key": key,
                    "collection_name": unquote(metadata.get("collection_name", "")),
                    "filename": unquote(metadata.get("filename", "documento")),
                }
            )
        return objects
    except Exception:  # noqa: BLE001 -- restauração é best-effort, nunca deveria quebrar a criação de sessão
        logger.exception("Falha ao listar objetos da sessão no R2 (segue sem restaurar)")
        return []


def download_raw_bytes(object_key: str) -> bytes | None:
    """Baixa o conteúdo original de um objeto. `None` em qualquer falha
    (R2 não configurado, objeto não existe mais, rede fora) -- o chamador
    (restauração de sessão) simplesmente pula esse documento em vez de
    quebrar a sessão inteira por causa de 1 objeto problemático."""
    if not is_configured():
        return None
    try:
        client = _get_client()
        obj = client.get_object(Bucket=config.R2_BUCKET_NAME, Key=object_key)
        return obj["Body"].read()
    except Exception:  # noqa: BLE001 -- ver docstring da função
        logger.exception("Falha ao baixar documento do R2 (chave=%s)", object_key)
        return None


def delete_session_objects(*, user_id, session_id: str) -> int:
    """Apaga todos os objetos de uma sessão -- chamado só pela faxina
    periódica de sessões vencidas (api/main.py), nunca no caminho síncrono
    de create_session/get_session (ver api/sessions.py). Devolve quantos
    objetos foram de fato apagados; `0` tanto pra "R2 não configurado"
    quanto pra "não havia nada" quanto pra "a chamada falhou" -- o
    chamador só usa esse número pra log, nunca pra decidir outra coisa."""
    if not is_configured():
        return 0
    try:
        client = _get_client()
        prefix = _session_prefix(user_id, session_id)
        response = client.list_objects_v2(Bucket=config.R2_BUCKET_NAME, Prefix=prefix)
        keys = [{"Key": item["Key"]} for item in response.get("Contents", [])]
        if not keys:
            return 0
        client.delete_objects(Bucket=config.R2_BUCKET_NAME, Delete={"Objects": keys})
        logger.info("Faxina R2: %d objeto(s) apagado(s) da sessão expirada %s", len(keys), session_id)
        return len(keys)
    except Exception:  # noqa: BLE001 -- a faxina de sessão em si nunca pode falhar por causa do R2
        logger.exception("Falha ao apagar objetos da sessão no R2 (sessão=%s)", session_id)
        return 0
