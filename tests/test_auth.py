"""OAuth application mode: token store, code exchange, and login flow."""

import json
import stat
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from mcp_pcloud_crunchtools.auth import (
    EU_API_HOST,
    US_API_HOST,
    TokenData,
    TokenStore,
    run_login_flow,
)
from mcp_pcloud_crunchtools.config import AuthMode, Config
from mcp_pcloud_crunchtools.errors import (
    AuthenticationError,
    TokenUnavailableError,
)


def _store(tmp_path):
    return TokenStore(path=tmp_path / "tokens.json")


class TestTokenStore:
    """Persistence of the bearer token."""

    def test_missing_store_loads_as_none(self, tmp_path):
        assert _store(tmp_path).load() is None

    def test_round_trip(self, tmp_path):
        store = _store(tmp_path)
        store.save(TokenData(access_token=SecretStr("tok"), api_host=EU_API_HOST, uid=7))

        fresh = TokenStore(path=store.path)
        loaded = fresh.load()
        assert loaded is not None
        assert loaded.access_token.get_secret_value() == "tok"
        assert loaded.api_host == EU_API_HOST
        assert loaded.uid == 7

    def test_saved_file_is_owner_only(self, tmp_path):
        store = _store(tmp_path)
        store.save(TokenData(access_token=SecretStr("tok")))
        mode = stat.S_IMODE(store.path.stat().st_mode)
        assert mode == 0o600

    def test_corrupt_store_loads_as_none(self, tmp_path):
        store = _store(tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json", encoding="utf-8")
        assert store.load() is None

    def test_unknown_host_falls_back_to_us(self, tmp_path):
        store = _store(tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(
            json.dumps({"access_token": "tok", "api_host": "evil.example.com"}),
            encoding="utf-8",
        )
        loaded = store.load()
        assert loaded is not None
        assert loaded.api_host == US_API_HOST

    def test_get_token_without_login_is_actionable(self, tmp_path):
        with pytest.raises(TokenUnavailableError, match="login"):
            _store(tmp_path).get_token()

    def test_env_var_overrides_path(self, tmp_path, monkeypatch):
        target = tmp_path / "elsewhere.json"
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(target))
        assert TokenStore(path=tmp_path / "ignored.json").path == target

    def test_token_is_not_exposed_by_repr(self, tmp_path):
        data = TokenData(access_token=SecretStr("super-secret"))
        assert "super-secret" not in repr(data)


class TestConfigOAuthMode:
    """Mode selection and precedence."""

    def test_client_credentials_select_oauth_app(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        config = Config()
        assert config.mode is AuthMode.OAUTH_APP
        assert config.uses_oauth is True
        assert config.client_id == "cid"
        assert config.client_secret.get_secret_value() == "csec"

    def test_oauth_app_outranks_static_and_session(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        assert Config().mode is AuthMode.OAUTH_APP

    def test_half_configured_app_does_not_select_oauth(self, monkeypatch):
        """A client id with no secret must not shadow a working token."""
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        assert Config().mode is AuthMode.STATIC_TOKEN

    def test_client_secret_file_supported(self, monkeypatch, tmp_path):
        secret = tmp_path / "csec"
        secret.write_text("from-file\n", encoding="utf-8")
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET_FILE", str(secret))
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        assert Config().client_secret.get_secret_value() == "from-file"

    def test_access_token_reads_from_store(self, monkeypatch, tmp_path):
        store_path = tmp_path / "t.json"
        TokenStore(path=store_path).save(TokenData(access_token=SecretStr("stored-token")))
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(store_path))
        assert Config().access_token == "stored-token"

    def test_access_token_without_login_is_actionable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "none.json"))
        with pytest.raises(TokenUnavailableError, match="login"):
            _ = Config().access_token

    def test_region_comes_from_the_store(self, monkeypatch, tmp_path):
        store_path = tmp_path / "t.json"
        TokenStore(path=store_path).save(
            TokenData(access_token=SecretStr("tok"), api_host=EU_API_HOST)
        )
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(store_path))
        assert Config().api_host == EU_API_HOST

    def test_explicit_host_overrides_the_store(self, monkeypatch, tmp_path):
        store_path = tmp_path / "t.json"
        TokenStore(path=store_path).save(
            TokenData(access_token=SecretStr("tok"), api_host=EU_API_HOST)
        )
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(store_path))
        monkeypatch.setenv("PCLOUD_API_HOST", US_API_HOST)
        assert Config().api_host == US_API_HOST

    def test_repr_never_exposes_the_secret(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
        monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "super-secret")
        monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(tmp_path / "t.json"))
        config = Config()
        assert "super-secret" not in repr(config)
        assert "super-secret" not in str(config)


def _fake_callback(code="the-code", state=None, error=None, hostname=None):
    """Build a _CallbackServer stand-in that replays a finished redirect."""
    server = MagicMock()
    server.callback_code = code
    server.callback_state = state
    server.callback_error = error
    server.callback_hostname = hostname
    return server


class TestLoginFlow:
    """The authorization code flow, with the browser and socket stubbed out."""

    @staticmethod
    def _run(tmp_path, server, post_payload=None, post_side_effect=None):
        store = _store(tmp_path)
        captured = {}

        def fake_server(_addr, _handler):
            # The real state is generated inside run_login_flow; echo it back
            # so the CSRF check passes unless a test says otherwise.
            return server

        def fake_post(_self, url, data=None, **_kwargs):
            captured["url"] = url
            captured["data"] = data
            if post_side_effect is not None:
                raise post_side_effect
            return httpx.Response(
                200,
                json=post_payload or {"result": 0, "access_token": "tok", "uid": 1},
                request=httpx.Request("POST", url),
            )

        with (
            patch("mcp_pcloud_crunchtools.auth._CallbackServer", fake_server),
            patch("mcp_pcloud_crunchtools.auth.webbrowser.open"),
            patch.object(httpx.Client, "post", fake_post),
        ):
            result = run_login_flow(
                client_id="cid",
                client_secret=SecretStr("csec"),
                token_store=store,
                open_browser=False,
            )
        return result, store, captured

    def test_successful_login_persists_the_token(self, tmp_path):
        server = _fake_callback()
        # Mirror whatever state the flow generated back into the callback.
        original_serve = server.serve_forever

        def echo_state():
            original_serve()

        server.serve_forever = echo_state
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            data, store, captured = self._run(tmp_path, server)

        assert data.access_token.get_secret_value() == "tok"
        assert store.load() is not None
        assert captured["url"].endswith("/oauth2_token")

    def test_secret_travels_in_the_post_body_never_the_url(self, tmp_path):
        server = _fake_callback()
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            _, _, captured = self._run(tmp_path, server)

        assert "csec" not in captured["url"]
        assert captured["data"]["client_secret"] == "csec"
        assert captured["data"]["client_id"] == "cid"

    def test_state_mismatch_aborts(self, tmp_path):
        server = _fake_callback(state="attacker-supplied")
        with (
            patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=False),
            pytest.raises(AuthenticationError, match="CSRF"),
        ):
            self._run(tmp_path, server)

    def test_denied_authorization_raises(self, tmp_path):
        server = _fake_callback(code=None, error="access_denied")
        with pytest.raises(AuthenticationError, match="denied"):
            self._run(tmp_path, server)

    def test_missing_code_raises(self, tmp_path):
        server = _fake_callback(code=None)
        with pytest.raises(AuthenticationError, match="No authorization code"):
            self._run(tmp_path, server)

    def test_callback_hostname_selects_the_region(self, tmp_path):
        server = _fake_callback(hostname=EU_API_HOST)
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            data, _, captured = self._run(tmp_path, server)

        assert data.api_host == EU_API_HOST
        assert EU_API_HOST in captured["url"]

    def test_untrusted_callback_hostname_is_ignored(self, tmp_path):
        """A redirect must not be able to point the client at any host."""
        server = _fake_callback(hostname="evil.example.com")
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            data, _, captured = self._run(tmp_path, server)

        assert data.api_host == US_API_HOST
        assert "evil.example.com" not in captured["url"]

    def test_rejected_code_raises(self, tmp_path):
        server = _fake_callback()
        with (
            patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True),
            pytest.raises(AuthenticationError, match="2093"),
        ):
            self._run(
                tmp_path,
                server,
                post_payload={"result": 2093, "error": "Invalid 'client_secret'"},
            )

    def test_transport_failure_raises(self, tmp_path):
        server = _fake_callback()
        with (
            patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True),
            pytest.raises(AuthenticationError, match="Token exchange failed"),
        ):
            self._run(tmp_path, server, post_side_effect=httpx.ConnectError("no route"))


class TestStoredTokenIsScrubbed:
    """A token from the store is not in the environment, so scrubbing it
    needs explicit registration. Without that it would leak into errors."""

    def test_stored_token_is_scrubbed_from_errors(self, tmp_path):
        from mcp_pcloud_crunchtools.errors import PCloudApiError

        secret = "store-only-token-abcdef123456"
        store = _store(tmp_path)
        store.save(TokenData(access_token=SecretStr(secret)))

        err = PCloudApiError(5000, f"upstream echoed {secret} back")
        assert secret not in str(err)
        assert "***" in str(err)

    def test_loading_a_token_also_registers_it(self, tmp_path):
        from mcp_pcloud_crunchtools.errors import PCloudApiError

        secret = "loaded-token-zyxwvu987654"
        path = tmp_path / "tokens.json"
        TokenStore(path=path).save(TokenData(access_token=SecretStr(secret)))

        # A brand new process would only ever load, never save.
        TokenStore(path=path).load()
        assert secret not in str(PCloudApiError(5000, f"leak {secret}"))


class TestTokenResponseHandling:
    """pCloud reports failure in the body, not the HTTP status, so a 200
    response still has to be inspected. Exercised through the real flow."""

    def test_uid_is_recorded(self, tmp_path):
        server = _fake_callback()
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            data, _, _ = TestLoginFlow._run(
                tmp_path,
                server,
                post_payload={"result": 0, "access_token": "abc", "uid": 42},
            )
        assert data.uid == 42

    def test_missing_access_token_raises(self, tmp_path):
        server = _fake_callback()
        with (
            patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True),
            pytest.raises(AuthenticationError, match="no access_token"),
        ):
            TestLoginFlow._run(tmp_path, server, post_payload={"result": 0})

    def test_no_expiry_is_recorded(self, tmp_path):
        """pCloud tokens do not expire; inventing an expiry would be a lie."""
        server = _fake_callback()
        with patch("mcp_pcloud_crunchtools.auth.secrets.compare_digest", return_value=True):
            data, _, _ = TestLoginFlow._run(tmp_path, server)
        assert not hasattr(data, "expires_at")


class TestAuthorizeUrl:
    """pCloud makes redirect_uri optional for the code flow."""

    def test_redirect_uri_included_when_given(self):
        from mcp_pcloud_crunchtools.auth import build_authorize_url

        url = build_authorize_url("cid", "st", "https://example.com/callback")
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcallback" in url
        assert "response_type=code" in url

    def test_redirect_uri_omitted_entirely_when_none(self):
        """Omitting it is what makes pCloud display the code instead."""
        from mcp_pcloud_crunchtools.auth import build_authorize_url

        url = build_authorize_url("cid", "st", None)
        assert "redirect_uri" not in url
        assert "client_id=cid" in url


class TestManualLogin:
    """Paste-the-code flow for headless hosts."""

    @staticmethod
    def _run(tmp_path, typed, payload=None):
        from mcp_pcloud_crunchtools.auth import run_manual_login

        store = _store(tmp_path)
        captured = {}

        def fake_post(_self, url, data=None, **_kw):
            captured["url"] = url
            captured["data"] = data
            return httpx.Response(
                200,
                json=payload or {"result": 0, "access_token": "tok", "uid": 99},
                request=httpx.Request("POST", url),
            )

        with (
            patch("builtins.input", return_value=typed),
            patch.object(httpx.Client, "post", fake_post),
        ):
            data = run_manual_login(
                client_id="cid",
                client_secret=SecretStr("csec"),
                token_store=store,
            )
        return data, store, captured

    def test_pasted_code_is_exchanged_and_stored(self, tmp_path):
        data, store, captured = self._run(tmp_path, "the-code")
        assert data.access_token.get_secret_value() == "tok"
        assert data.uid == 99
        assert store.load() is not None
        assert captured["data"]["code"] == "the-code"

    def test_no_redirect_uri_is_sent_on_exchange(self, tmp_path):
        _, _, captured = self._run(tmp_path, "the-code")
        assert "redirect_uri" not in captured["data"]

    def test_secret_stays_out_of_the_url(self, tmp_path):
        _, _, captured = self._run(tmp_path, "the-code")
        assert "csec" not in captured["url"]
        assert captured["data"]["client_secret"] == "csec"

    def test_empty_code_is_rejected(self, tmp_path):
        with pytest.raises(AuthenticationError, match="No authorization code"):
            self._run(tmp_path, "   ")

    def test_rejected_code_surfaces_the_result(self, tmp_path):
        with pytest.raises(AuthenticationError, match="2093"):
            self._run(tmp_path, "bad", payload={"result": 2093, "error": "Invalid code"})

    def test_non_interactive_stdin_is_actionable(self, tmp_path):
        from mcp_pcloud_crunchtools.auth import run_manual_login

        with (
            patch("builtins.input", side_effect=EOFError),
            pytest.raises(AuthenticationError, match="interactive terminal"),
        ):
            run_manual_login("cid", SecretStr("csec"), _store(tmp_path))


class TestRedirectUriOverride:
    """Behind a proxy, localhost is not reachable from the browser."""

    def test_env_var_overrides_localhost_default(self, tmp_path, monkeypatch):
        from mcp_pcloud_crunchtools import auth as auth_mod

        monkeypatch.setenv("PCLOUD_OAUTH_REDIRECT_URI", "https://mcp-pcloud.example.com/callback")
        server = _fake_callback(hostname=US_API_HOST)
        captured = {}

        def fake_post(_self, url, data=None, **_kw):
            captured["data"] = data
            return httpx.Response(
                200,
                json={"result": 0, "access_token": "t"},
                request=httpx.Request("POST", url),
            )

        with (
            patch.object(auth_mod, "_CallbackServer", lambda *_a: server),
            patch.object(auth_mod.secrets, "compare_digest", return_value=True),
            patch.object(httpx.Client, "post", fake_post),
        ):
            auth_mod.run_login_flow("cid", SecretStr("csec"), _store(tmp_path), open_browser=False)

        assert captured["data"]["redirect_uri"] == "https://mcp-pcloud.example.com/callback"
