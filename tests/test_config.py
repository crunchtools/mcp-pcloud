"""Configuration and credential-handling tests."""

import pytest

from mcp_pcloud_crunchtools.config import Config, get_config
from mcp_pcloud_crunchtools.errors import ConfigurationError


def test_token_from_env():
    assert get_config().access_token == "test-token-value"


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConfigurationError, match="PCLOUD_ACCESS_TOKEN"):
        Config()


def test_oauth_is_default_mode():
    assert get_config().uses_oauth is True


def test_session_token_alone_is_accepted(monkeypatch):
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
    config = Config()
    assert config.uses_oauth is False
    assert config.auth_token == "session-value"


def test_oauth_wins_when_both_present(monkeypatch):
    monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
    config = Config()
    assert config.uses_oauth is True
    assert config.access_token == "test-token-value"


def test_session_token_file_supported(monkeypatch, tmp_path):
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    secret = tmp_path / "session"
    secret.write_text("from-session-file\n")
    monkeypatch.setenv("PCLOUD_AUTH_TOKEN_FILE", str(secret))
    assert Config().auth_token == "from-session-file"


def test_access_token_unavailable_in_session_mode(monkeypatch):
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
    config = Config()
    with pytest.raises(ConfigurationError, match="not configured"):
        _ = config.access_token


def test_repr_names_auth_mode(monkeypatch):
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
    assert "session" in repr(Config())
    assert "session-value" not in repr(Config())


def test_token_file_takes_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "token"
    secret.write_text("from-file\n")
    secret.chmod(0o600)
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN", "from-env")
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN_FILE", str(secret))
    assert Config().access_token == "from-file"


def test_token_file_is_stripped(monkeypatch, tmp_path):
    secret = tmp_path / "token"
    secret.write_text("  padded-token  \n\n")
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN_FILE", str(secret))
    assert Config().access_token == "padded-token"


def test_empty_token_file_raises(monkeypatch, tmp_path):
    secret = tmp_path / "token"
    secret.write_text("   \n")
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN_FILE", str(secret))
    with pytest.raises(ConfigurationError, match="empty file"):
        Config()


def test_unreadable_token_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN_FILE", str(tmp_path / "nope"))
    with pytest.raises(ConfigurationError, match="Could not read"):
        Config()


def test_permissive_token_file_warns(monkeypatch, tmp_path, caplog):
    secret = tmp_path / "token"
    secret.write_text("loose-token")
    secret.chmod(0o644)
    monkeypatch.setenv("PCLOUD_ACCESS_TOKEN_FILE", str(secret))
    Config()
    assert "group/world accessible" in caplog.text


def test_eu_host_accepted(monkeypatch):
    monkeypatch.setenv("PCLOUD_API_HOST", "eapi.pcloud.com")
    assert Config().api_base_url == "https://eapi.pcloud.com"


def test_invalid_host_rejected(monkeypatch):
    monkeypatch.setenv("PCLOUD_API_HOST", "evil.example.com")
    with pytest.raises(ConfigurationError, match="Invalid PCLOUD_API_HOST"):
        Config()


def test_repr_and_str_never_expose_token():
    config = get_config()
    assert "test-token-value" not in repr(config)
    assert "test-token-value" not in str(config)
    assert "***" in repr(config)
