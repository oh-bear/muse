import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


def test_settings_loads_from_env():
    """Settings should load from environment variables."""
    env = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/muse",
        "MINIFLUX_URL": "http://localhost:8080",
        "MINIFLUX_API_KEY": "test-key",
        "AI_PROVIDER": "claude",
        "ANTHROPIC_API_KEY": "sk-test",
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_CHAT_ID": "-100123",
        "TIMEZONE": "UTC",
        "SCHEDULE_HOUR": "9",
        "SCHEDULE_MINUTE": "30",
    }
    with patch.dict(os.environ, env, clear=True):
        from importlib import reload
        import muse.config as cfg_mod
        reload(cfg_mod)
        s = cfg_mod.Settings()
        assert s.database_url == env["DATABASE_URL"]
        assert s.miniflux_url == env["MINIFLUX_URL"]
        assert s.ai_provider == "claude"
        assert s.timezone == "UTC"
        assert s.schedule_hour == 9
        assert s.schedule_minute == 30


def test_focus_config_loads_yaml(tmp_path):
    """FocusConfig should load from a YAML file."""
    data = {
        "focus_areas": ["ai-tools", "saas"],
        "exclude": ["crypto"],
        "score_threshold": 3,
        "languages": ["en", "zh"],
        "source_mapping": {"PH Feed": "producthunt"},
        "indie_criteria": {"max_team_size": 5},
    }
    f = tmp_path / "focus.yaml"
    f.write_text(yaml.dump(data))

    from muse.config import FocusConfig
    cfg = FocusConfig.from_yaml(f)
    assert cfg.focus_areas == ["ai-tools", "saas"]
    assert cfg.exclude == ["crypto"]
    assert cfg.score_threshold == 3
    assert cfg.languages == ["en", "zh"]
    assert cfg.source_mapping == {"PH Feed": "producthunt"}


def test_focus_config_defaults(tmp_path):
    """FocusConfig should use sensible defaults for missing fields."""
    f = tmp_path / "focus.yaml"
    f.write_text(yaml.dump({"focus_areas": ["ai-tools"]}))

    from muse.config import FocusConfig
    cfg = FocusConfig.from_yaml(f)
    assert cfg.score_threshold == 3
    assert cfg.exclude == []
    assert cfg.languages == ["en"]
    assert cfg.source_mapping == {}
