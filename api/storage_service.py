"""Fachada neutra de armazenamento (Fase I da evolução "livros grandes",
2026-09-10).

Achado da auditoria desta fase: a SUBSTÂNCIA da abstração de storage já
estava pronta antes desta fachada existir -- `api/r2_storage.py` já tem
uma interface pública genérica nos nomes (`is_configured`/
`upload_raw_bytes`/`list_session_objects`/`download_raw_bytes`/
`delete_session_objects`, nenhum verbo específico de R2) e já funciona
com Cloudflare R2 OU Backblaze B2 (via `R2_ENDPOINT_URL`/`R2_REGION`,
ver api/config.py) -- confirmado ao vivo, testado, em uso real em
produção. O que faltava era só cosmético: o próprio ARQUIVO ainda se
chama `r2_storage.py` e as env vars ainda começam com `R2_`.

Decisão registrada (não renomear nada existente -- tocaria toda a
superfície de testes/imports/`.env` já configurado em produção, por um
ganho puramente de nome, contrariando o princípio "aditivo/reversível"
da evolução): este módulo é a opção de menor risco pra quem quiser
programar contra um nome de fachada neutro (`StorageService`) em vez do
nome histórico `r2_storage` -- só repassa cada chamada, zero lógica
própria, zero duplicação. `r2_storage.py` continua sendo a única
implementação real; isto é 100% aditivo, nada some se este arquivo for
removido no futuro.
"""

from __future__ import annotations

from . import r2_storage


class StorageService:
    """Fachada estática sobre `api/r2_storage.py` -- cada método é um
    repasse direto (mesma assinatura, mesmo comportamento, mesmas
    garantias já documentadas nas funções reais), nada reimplementado
    aqui. Usar `StorageService.X(...)` ou `r2_storage.X(...)` é
    equivalente em tudo; a única diferença é o nome que o código
    chamador prefere ler."""

    @staticmethod
    def is_configured() -> bool:
        return r2_storage.is_configured()

    @staticmethod
    def upload_raw_bytes(*, user_id, session_id: str, collection_name: str, filename: str, raw_bytes: bytes) -> str | None:
        return r2_storage.upload_raw_bytes(
            user_id=user_id, session_id=session_id, collection_name=collection_name,
            filename=filename, raw_bytes=raw_bytes,
        )

    @staticmethod
    def list_session_objects(*, user_id, session_id: str) -> list[dict]:
        return r2_storage.list_session_objects(user_id=user_id, session_id=session_id)

    @staticmethod
    def download_raw_bytes(object_key: str) -> bytes | None:
        return r2_storage.download_raw_bytes(object_key)

    @staticmethod
    def delete_session_objects(*, user_id, session_id: str) -> int:
        return r2_storage.delete_session_objects(user_id=user_id, session_id=session_id)
