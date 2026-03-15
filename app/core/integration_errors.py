"""Shared integration errors for optional cloud dependencies."""

from __future__ import annotations


class AzureIntegrationUnavailableError(RuntimeError):
    """Raised when an Azure-backed capability is unavailable in the current environment."""

    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"{service} unavailable: {detail}")
