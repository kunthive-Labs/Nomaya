"""Hand-rolled .env parsing and lazy settings."""

import os

from nomaya.config import _load_dotenv, settings


def test_load_dotenv_parses_and_strips(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "NOMAYA_T_PLAIN=value\n"
        'NOMAYA_T_DQUOTE="quoted value"\n'
        "NOMAYA_T_SQUOTE='single'\n"
        "NOMAYA_T_SPACES =  padded  \n"
        "not a key value line\n"
    )
    for key in ("NOMAYA_T_PLAIN", "NOMAYA_T_DQUOTE", "NOMAYA_T_SQUOTE", "NOMAYA_T_SPACES"):
        monkeypatch.delenv(key, raising=False)
    try:
        _load_dotenv(env)
        assert os.environ["NOMAYA_T_PLAIN"] == "value"
        assert os.environ["NOMAYA_T_DQUOTE"] == "quoted value"
        assert os.environ["NOMAYA_T_SQUOTE"] == "single"
        assert os.environ["NOMAYA_T_SPACES"] == "padded"
    finally:
        for key in ("NOMAYA_T_PLAIN", "NOMAYA_T_DQUOTE", "NOMAYA_T_SQUOTE", "NOMAYA_T_SPACES"):
            os.environ.pop(key, None)


def test_load_dotenv_does_not_clobber_existing_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAYA_T_PRESET", "from-process")
    env = tmp_path / ".env"
    env.write_text("NOMAYA_T_PRESET=from-file\n")
    _load_dotenv(env)
    assert os.environ["NOMAYA_T_PRESET"] == "from-process"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    _load_dotenv(tmp_path / "does-not-exist.env")  # must not raise


def test_settings_defaults(monkeypatch):
    for key in ("NOMAYA_API_TOKEN", "NOMAYA_ALLOWED_MODELS", "NOMAYA_CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    assert settings.api_token == ""
    assert settings.allowed_models == ["mock/compliant-agent", "mock/naive-agent", "mock/judge"]
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_settings_parse_comma_lists(monkeypatch):
    monkeypatch.setenv("NOMAYA_ALLOWED_MODELS", " mock/judge , openai/gpt-4o-mini ,")
    assert settings.allowed_models == ["mock/judge", "openai/gpt-4o-mini"]
