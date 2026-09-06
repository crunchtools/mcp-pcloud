"""Shared fixtures. Resets module singletons so state never leaks between tests."""

import os

import pytest

from mcp_pcloud_crunchtools import client as client_module
from mcp_pcloud_crunchtools import config as config_module


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """Reset config and client singletons around every test."""
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN", "test-token-value")
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN_FILE", raising=False)
    monkeypatch.delenv("PCLOUD_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("PCLOUD_AUTH_TOKEN_FILE", raising=False)
    monkeypatch.delenv("PCLOUD_API_HOST", raising=False)
    config_module._config = None
    client_module._client = None
    yield
    config_module._config = None
    client_module._client = None
    os.environ.pop("PCLOUD_ACCESS_TOKEN", None)
    os.environ.pop("PCLOUD_AUTH_TOKEN", None)
