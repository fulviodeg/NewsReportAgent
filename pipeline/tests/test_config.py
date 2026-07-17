from pathlib import Path

from src.config import load_config, load_secrets

CONFIG_PATH = str(Path(__file__).parents[1] / "config.toml")


def test_load_config_types_and_values():
    cfg = load_config(CONFIG_PATH)
    assert cfg.cadence.collection_interval_minutes > 0
    assert cfg.cadence.processing_interval_minutes > 0
    assert cfg.llm.model_classify and cfg.llm.model_synthesize
    assert cfg.llm.endpoint.startswith("http")
    assert 0.0 <= cfg.clustering.similarity_threshold <= 1.0
    assert cfg.clustering.window_hours > 0
    assert cfg.cost.daily_usd_cap > 0
    assert "Other" in cfg.classify.themes
    assert cfg.embeddings.provider and cfg.embeddings.model and cfg.embeddings.endpoint
    assert len(cfg.sources) >= 1
    assert cfg.sources[0].from_address


def test_load_secrets_reads_env_not_toml():
    env = {
        "OPENROUTER_API_KEY": "sk-or-test",
        "IMAP_HOST": "imap.example.com",
        "IMAP_PORT": "993",
        "IMAP_USERNAME": "u",
        "IMAP_PASSWORD": "p",
        "EMBEDDINGS_API_KEY": "sk-emb",
    }
    secrets = load_secrets(env)
    assert secrets.openrouter_api_key == "sk-or-test"
    assert secrets.imap_port == 993
    assert secrets.embeddings_api_key == "sk-emb"


def test_load_secrets_optional_embeddings_key():
    secrets = load_secrets({"IMAP_PORT": "993"})
    assert secrets.embeddings_api_key is None
