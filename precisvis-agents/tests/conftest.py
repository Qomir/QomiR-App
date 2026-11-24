import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.context import build_context  # noqa: E402
from core.db import DB  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c.root = ROOT
    return c


@pytest.fixture
def make_ctx(cfg, tmp_path, monkeypatch):
    """Contexte de simulation isolé : base en mémoire et sorties dans un dossier temporaire."""
    from core import config as config_mod

    def _make(day="2026-11-24", overrides=None, phase="morning"):
        if overrides:
            config_mod._deep_update(cfg.raw, overrides)
        out = tmp_path / "output"
        monkeypatch.setattr(type(cfg), "output_dir", property(lambda self: out))
        return build_context(cfg, dry_run=True, day=day, db=DB(":memory:"), phase=phase)

    return _make
