"""Logging estruturado mínimo para a api/.

Reaproveita o mesmo `logging` stdlib que docksmith/service/*.py já usa (mesmo
formato, mesmo nível) — não introduz nenhuma biblioteca nova. Vários módulos
de docksmith/service chamam `logging.basicConfig` na importação; `setup()`
aqui é idempotente (só configura se ainda não houver handler no root logger),
então funciona independente da ordem de import entre api/ e docksmith/.

Regra de conteúdo: só metadados vão pro log (contagens, nomes de
provedor/modelo, IDs de sessão, URLs raspadas, status HTTP). Nunca: API keys,
tokens (mesmo parciais), senhas, ou o texto de perguntas/respostas do
usuário.
"""

import logging


def setup() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
