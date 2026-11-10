"""Logs : console + fichier tournant dans data/logs/autopilot.log."""
import logging
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR

_configured = False


def get(name: str = "autopilot") -> logging.Logger:
    global _configured
    if not _configured:
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
        root = logging.getLogger("autopilot")
        root.setLevel(logging.INFO)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        fh = RotatingFileHandler(DATA_DIR / "logs" / "autopilot.log", maxBytes=5_000_000,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(sh)
        root.addHandler(fh)
        _configured = True
    return logging.getLogger(name if name.startswith("autopilot") else f"autopilot.{name}")
