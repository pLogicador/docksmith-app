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

# Bypass só para desenvolvimento local (QA do frontend sem token real do
# Hub). Nunca deve ser "true" em produção — não existe na Vercel/Railway.
DEV_BYPASS_AUTH = os.getenv("DOCKSMITH_API_DEV_BYPASS_AUTH", "false").lower() == "true"
if IS_PRODUCTION and DEV_BYPASS_AUTH:
    raise RuntimeError(
        "DOCKSMITH_API_DEV_BYPASS_AUTH não pode ser 'true' quando ENVIRONMENT=production."
    )

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
