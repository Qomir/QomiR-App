"""Chargement de config.yaml et des variables d'environnement (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # dépendance optionnelle
        return
    load_dotenv(ROOT / ".env", override=False)


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path = ROOT
    env: dict[str, str] = field(default_factory=dict)

    # Accès pratique : cfg["budgets"]["api_daily_eur"] ou cfg.get("budgets.api_daily_eur")
    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def secret(self, name: str) -> str | None:
        value = self.env.get(name) or os.environ.get(name)
        return value or None

    @property
    def kill_switch(self) -> bool:
        return bool(self.raw.get("kill_switch", False))

    @property
    def db_path(self) -> Path:
        return Path(self.env.get("PRECISVIS_DB") or os.environ.get("PRECISVIS_DB") or self.root / "data" / "precisvis.db")

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def brand_dir(self) -> Path:
        return self.root / "brand"


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    _load_dotenv()
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if overrides:
        _deep_update(raw, overrides)
    return Config(raw=raw, env={k: v for k, v in os.environ.items()})


def _deep_update(base: dict, upd: dict) -> None:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def load_brand(cfg: Config) -> dict[str, Any]:
    with open(cfg.brand_dir / "brand.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
