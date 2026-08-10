"""Catálogo de provedores/modelos de IA suportados e teste de conexão.

Groq continua sendo o provedor padrão (usa a chave do servidor quando o
usuário não informa a própria), exatamente como o Docksmith funciona hoje.
Os demais provedores só funcionam quando o usuário informa sua própria
chave — nunca é persistida, vive apenas na sessão em memória do processo.
"""

from starlette.concurrency import run_in_threadpool

from . import config
from .bootstrap import DEFAULT_MODELS, build_chat_llm
from .logging_config import get_logger

logger = get_logger(__name__)

PROVIDER_CATALOG = [
    {
        "id": "groq",
        "label": "Groq",
        "requiresApiKey": False,
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
        "defaultModel": DEFAULT_MODELS["groq"],
        "speedHint": "Rápida",
        "description": "Usa a chave padrão do Docksmith — nenhuma configuração necessária.",
        "apiKeyHelp": None,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "requiresApiKey": True,
        "models": ["gpt-4o-mini", "gpt-4o"],
        "defaultModel": DEFAULT_MODELS["openai"],
        "speedHint": "Equilibrada",
        "description": "Requer sua própria chave de API da OpenAI.",
        "apiKeyHelp": {
            "steps": [
                "Acesse platform.openai.com e crie uma conta (ou faça login).",
                "Vá em API keys e clique em \"Create new secret key\".",
                "Copie a chave (começa com sk-...) — ela só é exibida uma vez.",
            ],
            "url": "https://platform.openai.com/api-keys",
        },
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "requiresApiKey": True,
        "models": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
        "defaultModel": DEFAULT_MODELS["anthropic"],
        "speedHint": "Profunda",
        "description": "Requer sua própria chave de API da Anthropic.",
        "apiKeyHelp": {
            "steps": [
                "Acesse console.anthropic.com e crie uma conta (ou faça login).",
                "Vá em Settings → API Keys e clique em \"Create Key\".",
                "Copie a chave (começa com sk-ant-...) — ela só é exibida uma vez.",
            ],
            "url": "https://console.anthropic.com/settings/keys",
        },
    },
    {
        "id": "google",
        "label": "Google Gemini",
        "requiresApiKey": True,
        "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
        "defaultModel": DEFAULT_MODELS["google"],
        "speedHint": "Rápida",
        "description": "Requer sua própria chave de API do Google AI Studio.",
        "apiKeyHelp": {
            "steps": [
                "Acesse aistudio.google.com/app/apikey e faça login com uma conta Google.",
                "Clique em \"Create API key\" e escolha um projeto (ou crie um novo).",
                "Copie a chave gerada.",
            ],
            "url": "https://aistudio.google.com/app/apikey",
        },
    },
]

# Recomendações prontas por objetivo — sempre apontando para provedores/modelos
# que já existem em PROVIDER_CATALOG (nunca inventa capacidade, preço ou modelo
# que o sistema não suporte de fato). "recommendedDepth" usa as mesmas chaves
# de RAGService.DEPTH_K (docksmith/service/rag.py) — rapida/equilibrada/profunda.
RECOMMENDATIONS = [
    {
        "id": "custo-beneficio",
        "label": "Custo-benefício",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "recommendedDepth": "equilibrada",
        "requiresApiKey": False,
        "bestFor": "Uso do dia a dia sem custo extra e sem configurar nada.",
        "whenToUse": "Quando você quer boas respostas rápido, sem se preocupar com chave de API.",
        "limitations": "Menos profundo que os modelos Anthropic em análises muito longas ou ambíguas.",
        "tips": "É o padrão do Docksmith — bom ponto de partida para qualquer coleção.",
    },
    {
        "id": "rapida",
        "label": "Rápida",
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "recommendedDepth": "rapida",
        "requiresApiKey": False,
        "bestFor": "Perguntas diretas e objetivas, iteração rápida.",
        "whenToUse": "Quando você está explorando e quer respostas quase instantâneas.",
        "limitations": "Menos indicado para perguntas que exigem cruzar muitos trechos de contexto.",
        "tips": "Combine com a profundidade \"Rápida\" para o menor tempo de resposta possível.",
    },
    {
        "id": "precisa",
        "label": "Precisa",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "recommendedDepth": "equilibrada",
        "requiresApiKey": True,
        "bestFor": "Respostas técnicas com alta fidelidade ao contexto fornecido.",
        "whenToUse": "Quando a precisão da resposta importa mais que a velocidade.",
        "limitations": "Requer sua própria chave de API da Anthropic (uso pago).",
        "tips": "Boa escolha padrão para documentação técnica densa.",
    },
    {
        "id": "profunda",
        "label": "Profunda",
        "provider": "anthropic",
        "model": "claude-opus-5",
        "recommendedDepth": "profunda",
        "requiresApiKey": True,
        "bestFor": "Análises extensas, comparações e raciocínio sobre muitos trechos de uma vez.",
        "whenToUse": "Quando você precisa da resposta mais completa e detalhada possível.",
        "limitations": "Mais lento e mais caro por pergunta; requer chave de API da Anthropic.",
        "tips": "Combine com a profundidade \"Profunda\" (mais trechos de contexto) para tirar o máximo proveito.",
    },
]


def resolve_api_key(provider: str, api_key: str | None) -> str | None:
    if api_key:
        return api_key
    if provider == "groq":
        return config.GROQ_API_KEY
    return None


async def test_connection(provider: str, model: str | None, api_key: str | None) -> tuple[bool, str | None]:
    resolved_key = resolve_api_key(provider, api_key)
    if not resolved_key:
        return False, "Informe uma chave de API para este provedor."

    def _run() -> None:
        llm = build_chat_llm(provider, model, resolved_key)
        llm.invoke("ping")

    try:
        await run_in_threadpool(_run)
        logger.info("Teste de conexão OK: provider=%s", provider)
        return True, None
    except Exception as e:  # provedor externo pode falhar de várias formas
        logger.warning("Teste de conexão falhou: provider=%s", provider)
        return False, str(e)[:300]
