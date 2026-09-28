import pytest

from pulse import config


def test_teste_por_omissao_e_base_de_teste():
    s = config.load({})
    assert s.env == "development" and s.db_path.name == "teste-pulse.db" and not s.production
    assert s.web_base_path == "/pulse/" and s.dados_url == "http://127.0.0.1:8898"


def test_fora_de_producao_recusa_base_que_nao_e_de_teste():
    with pytest.raises(config.ConfigError):
        config.load({"PULSE_ENV": "development", "PULSE_DB_PATH": "/var/lib/pulse/pulse.db"})
    with pytest.raises(config.ConfigError):
        config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": "/tmp/qualquer.db"})


def test_em_producao_recusa_base_de_teste_e_aceita_pulse_db():
    with pytest.raises(config.ConfigError):
        config.load({"PULSE_ENV": "production", "PULSE_DB_PATH": "/var/lib/pulse-test/teste-pulse.db"})
    s = config.load({"PULSE_ENV": "production", "PULSE_DB_PATH": "/var/lib/pulse/pulse.db"})
    assert s.production


def test_ambiente_invalido():
    with pytest.raises(config.ConfigError):
        config.load({"PULSE_ENV": "staging"})


def test_base_path_normalizado():
    assert config.load({"PULSE_WEB_BASE_PATH": "pulse"}).web_base_path == "/pulse/"


def test_base_path_raiz_e_sessao_dias():
    assert config.load({"PULSE_WEB_BASE_PATH": "/"}).web_base_path == "/"
    assert config.load({}).session_days == 30 and config.load({"PULSE_SESSION_DAYS": "7"}).session_days == 7
    for mau in ("0", "abc", "999"):
        with pytest.raises(config.ConfigError):
            config.load({"PULSE_SESSION_DAYS": mau})
