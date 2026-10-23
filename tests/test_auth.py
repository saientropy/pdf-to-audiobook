import json

import pytest

from audiobook import auth


@pytest.fixture
def config(tmp_path, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    return tmp_path


def add_profile(base, name):
    (base / "configs").mkdir(exist_ok=True)
    (base / "credentials").mkdir(exist_ok=True)
    (base / "configs" / f"{name}.json").write_text(json.dumps({"auth": {"type": "user_oauth"}}))
    (base / "credentials" / f"{name}.json").write_text(json.dumps({"access_token": "x"}))


def test_no_credentials(config):
    assert auth.current_credential().kind == "none"
    with pytest.raises(RuntimeError, match="audiobook login"):
        auth.make_client()


def test_api_key_is_the_fallback(config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert auth.current_credential().kind == "api-key"


def test_oauth_profile_wins_over_api_key(config, monkeypatch):
    add_profile(config, "default")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    cred = auth.current_credential()
    assert (cred.kind, cred.detail) == ("oauth-profile", "default")
    assert "OAuth profile is used" in auth.status_text()


def test_active_profile_pointer_and_env_override(config, monkeypatch):
    add_profile(config, "work")
    (config / "active_config").write_text("work\n")
    assert auth.oauth_profile() == "work"
    monkeypatch.setenv("ANTHROPIC_PROFILE", "missing")
    assert auth.oauth_profile() is None


def test_login_without_cli_explains_install(config, monkeypatch, capsys):
    monkeypatch.setattr(auth.shutil, "which", lambda _: None)
    assert auth.login() == 1
    assert "brew install anthropics/tap/ant" in capsys.readouterr().out
