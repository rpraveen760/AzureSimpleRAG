"""Azure AI Foundry helpers with lazy imports and explicit readiness checks."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.core.integration_errors import AzureIntegrationUnavailableError

logger = logging.getLogger(__name__)


def _is_direct_openai_configured() -> bool:
    """Return True when a direct Azure OpenAI endpoint + key are set."""
    return bool(settings.azure_openai_endpoint.strip() and settings.azure_openai_key.strip())


def is_foundry_configured() -> bool:
    """Return True when the project endpoint is available."""
    return bool(settings.azure_ai_project_endpoint.strip())


def foundry_status() -> str:
    """Expose a human-readable Foundry state for health checks and UI labels."""
    if _is_direct_openai_configured():
        return "configured (direct)"
    if not is_foundry_configured():
        return "not-configured"
    try:
        import azure.ai.projects  # noqa: F401
        import azure.identity  # noqa: F401
    except ModuleNotFoundError:
        return "missing-sdk"
    return "configured"


def ensure_foundry_ready() -> None:
    """Raise a user-facing error if neither direct OpenAI nor Foundry can be used."""
    if _is_direct_openai_configured():
        return  # Direct mode — no SDK check needed

    if not is_foundry_configured():
        raise AzureIntegrationUnavailableError(
            "Azure AI Foundry",
            "set AZURE_AI_PROJECT_ENDPOINT (or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY) before using AI features",
        )
    try:
        import azure.ai.projects  # noqa: F401
        import azure.identity  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AzureIntegrationUnavailableError(
            "Azure AI Foundry",
            "install azure-ai-projects and azure-identity to enable Foundry-backed chat and embeddings",
        ) from exc


@lru_cache(maxsize=1)
def get_project_client():
    """Return an Azure AI Foundry project client once Azure packages are installed."""
    ensure_foundry_ready()

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(
        endpoint=settings.azure_ai_project_endpoint,
        credential=DefaultAzureCredential(),
    )


@lru_cache(maxsize=1)
def get_openai_client():
    """Return a cached OpenAI client — direct Azure OpenAI if configured, otherwise via Foundry."""
    # Prefer direct Azure OpenAI endpoint (simpler, avoids Foundry routing issues)
    if _is_direct_openai_configured():
        from openai import AzureOpenAI

        logger.info("Using direct Azure OpenAI endpoint: %s", settings.azure_openai_endpoint)
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_key,
            api_version=settings.azure_openai_api_version,
        )

    # Fallback to Foundry-backed client
    logger.info("Using Foundry-backed OpenAI client")
    return get_project_client().get_openai_client()
