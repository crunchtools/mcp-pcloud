"""Browser-authorization tools and the /callback route."""

import httpx
import pytest
from pydantic import SecretStr

from mcp_pcloud_crunchtools.auth import (
    PENDING_LOGIN_TTL_SECONDS,
    PendingLogin,
    TokenStore,
    complete_login,
    get_pending_login,
)
from mcp_pcloud_crunchtools.errors import AuthenticationError


class TestPendingLogin:
    """CSRF state must survive between the tool call and the redirect."""

    def test_issue_then_verify_succeeds(self):
        p = PendingLogin()
        assert p.verify(p.issue()) is None

    def test_state_is_single_use(self):
        p = PendingLogin()
        st = p.issue()
        p.verify(st)
        with pytest.raises(AuthenticationError, match="No authorization is in progress"):
            p.verify(st)

    def test_wrong_state_rejected(self):
        p = PendingLogin()
        p.issue()
        with pytest.raises(AuthenticationError, match="CSRF"):
            p.verify("not-it")

    def test_verify_without_issue_rejected(self):
        with pytest.raises(AuthenticationError, match="No authorization is in progress"):
            PendingLogin().verify("anything")

    def test_reissue_supersedes_the_previous_state(self):
        """Two outstanding valid states would be two ways in."""
        p = PendingLogin()
        first = p.issue()
        p.issue()
        with pytest.raises(AuthenticationError, match="CSRF"):
            p.verify(first)

    def test_expired_state_rejected(self, monkeypatch):
        p = PendingLogin()
        st = p.issue()
        import mcp_pcloud_crunchtools.auth as auth_mod

        base = auth_mod.time.monotonic()
        monkeypatch.setattr(
            auth_mod.time, "monotonic", lambda: base + PENDING_LOGIN_TTL_SECONDS + 1
        )
        with pytest.raises(AuthenticationError, match="expired"):
            p.verify(st)


class TestCompleteLogin:
    """What the /callback route does with pCloud's redirect."""

    @staticmethod
    def _complete(tmp_path, *, state, hostname="api.pcloud.com", payload=None):
        store = TokenStore(path=tmp_path / "tokens.json")
        captured = {}

        def fake_post(_self, url, data=None, **_kw):
            captured["url"] = url
            captured["data"] = data
            return httpx.Response(
                200,
                json=payload or {"result": 0, "access_token": "tok", "uid": 7},
                request=httpx.Request("POST", url),
            )

        from unittest.mock import patch

        with patch.object(httpx.Client, "post", fake_post):
            data = complete_login(
                "cid",
                SecretStr("csec"),
                store,
                code="the-code",
                state=state,
                hostname=hostname,
                redirect_uri="https://x.example.com/callback",
            )
        return data, store, captured

    def test_stores_token_on_valid_state(self, tmp_path):
        st = get_pending_login().issue()
        data, store, captured = self._complete(tmp_path, state=st)
        assert data.uid == 7
        assert store.load() is not None
        assert captured["data"]["code"] == "the-code"

    def test_secret_never_in_url(self, tmp_path):
        st = get_pending_login().issue()
        _, _, captured = self._complete(tmp_path, state=st)
        assert "csec" not in captured["url"]

    def test_bad_state_is_refused_before_exchange(self, tmp_path):
        get_pending_login().issue()
        with pytest.raises(AuthenticationError, match="CSRF"):
            self._complete(tmp_path, state="forged")
        assert TokenStore(path=tmp_path / "tokens.json").load() is None

    def test_untrusted_hostname_ignored(self, tmp_path):
        st = get_pending_login().issue()
        data, _, captured = self._complete(tmp_path, state=st, hostname="evil.example.com")
        assert data.api_host == "api.pcloud.com"
        assert "evil.example.com" not in captured["url"]

    def test_eu_region_honoured(self, tmp_path):
        st = get_pending_login().issue()
        data, _, _ = self._complete(tmp_path, state=st, hostname="eapi.pcloud.com")
        assert data.api_host == "eapi.pcloud.com"

    def test_rejected_code_surfaces(self, tmp_path):
        st = get_pending_login().issue()
        with pytest.raises(AuthenticationError, match="2093"):
            self._complete(tmp_path, state=st, payload={"result": 2093, "error": "bad code"})


class TestAuthStatusTool:
    """The tool an agent polls before doing any work."""

    @pytest.mark.anyio
    async def test_reports_not_authorized_without_a_token(self, monkeypatch, tmp_path):
        from mcp_pcloud_crunchtools import config as config_mod
        from mcp_pcloud_crunchtools.tools.auth import auth_status

        monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "none.json"))
        config_mod._config = None

        out = await auth_status()
        assert "NOT AUTHORIZED" in out
        assert "pcloud_auth_start" in out

    @pytest.mark.anyio
    async def test_static_token_mode_says_browser_flow_not_applicable(self):
        from mcp_pcloud_crunchtools.tools.auth import auth_status

        out = await auth_status()
        assert "static_token" in out
        assert "does not apply" in out


class TestAuthStartTool:
    @pytest.mark.anyio
    async def test_refuses_without_oauth_mode(self):
        from mcp_pcloud_crunchtools.errors import ConfigurationError
        from mcp_pcloud_crunchtools.tools.auth import auth_start

        with pytest.raises(ConfigurationError, match="OAuth application mode"):
            await auth_start()

    @pytest.mark.anyio
    async def test_refuses_without_redirect_uri(self, monkeypatch, tmp_path):
        from mcp_pcloud_crunchtools import config as config_mod
        from mcp_pcloud_crunchtools.errors import ConfigurationError
        from mcp_pcloud_crunchtools.tools.auth import auth_start

        monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        config_mod._config = None

        with pytest.raises(ConfigurationError, match="PCLOUD_OAUTH_REDIRECT_URI"):
            await auth_start()

    @pytest.mark.anyio
    async def test_returns_url_and_never_the_secret(self, monkeypatch, tmp_path):
        from mcp_pcloud_crunchtools import config as config_mod
        from mcp_pcloud_crunchtools.tools.auth import auth_start

        monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "super-secret-value")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        monkeypatch.setenv("PCLOUD_OAUTH_REDIRECT_URI", "https://x.example.com/callback")
        config_mod._config = None

        out = await auth_start()
        assert "my.pcloud.com/oauth2/authorize" in out
        assert "super-secret-value" not in out
