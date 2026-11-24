"""Assemble les connecteurs réels (production) ou simulés (--dry-run)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .email import FileSender, ImapInbox, ResendSender, SmtpSender
from .fakes import FakeInbox, FakeMeta, FakeShopify, FakeTikTok
from .supplier import DSersMonitor


class MissingCredentials(Exception):
    pass


class Hosting:
    """Rend un fichier local accessible par URL publique (requis par Instagram, Facebook, Sume).
    Utilise Shopify Files (CDN Shopify) et garde l'URL en cache dans la base."""

    def __init__(self, ctx):
        self.ctx = ctx

    def public_url(self, path: Path) -> str:
        key = f"hosted:{Path(path).resolve()}"
        cached = self.ctx.db.kv_get(key)
        if cached:
            return cached
        url = self.ctx.tools.shopify.upload_file(Path(path))
        self.ctx.db.kv_set(key, url)
        return url


@dataclass
class Toolbox:
    shopify: Any
    meta: Any
    tiktok: Any
    inbox: Any
    report_sender: Any
    support_sender: Any
    supplier: Any
    hosting: Hosting | None = None


class _Lazy:
    """Instancie le client réel au premier usage, avec un message clair si une clé manque."""

    def __init__(self, label: str, factory):
        self._label, self._factory, self._obj = label, factory, None

    def __getattr__(self, item: str):
        if self._obj is None:
            self._obj = self._factory()
        return getattr(self._obj, item)


def _need(cfg, *names: str) -> list[str]:
    values = [cfg.secret(n) for n in names]
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise MissingCredentials("variables manquantes dans .env : " + ", ".join(missing))
    return values  # type: ignore[return-value]


def build_toolbox(ctx) -> Toolbox:
    cfg = ctx.cfg
    supplier = DSersMonitor(int(cfg.get("orders.alert_unfulfilled_hours", 24)),
                            int(cfg.get("orders.alert_no_tracking_days", 5)),
                            int(cfg.get("orders.alert_stuck_days", 10)))
    if ctx.dry_run:
        sender = FileSender(cfg.output_dir / "reports" / ctx.day)
        if ctx.send_test_email:
            sender = _real_report_sender(cfg)
        box = Toolbox(shopify=FakeShopify(ctx.day), meta=FakeMeta(ctx.day), tiktok=FakeTikTok(ctx.day),
                      inbox=FakeInbox(ctx.day), report_sender=sender,
                      support_sender=FileSender(cfg.output_dir / "reports" / ctx.day / "sav"), supplier=supplier)
        box.hosting = Hosting(ctx)
        return box

    def shopify():
        from .shopify import ShopifyClient
        shop, token = _need(cfg, "SHOPIFY_SHOP", "SHOPIFY_ADMIN_TOKEN")
        return ShopifyClient(shop, token)

    def meta():
        from .meta import MetaClient
        page_id, token, ig = _need(cfg, "META_PAGE_ID", "META_PAGE_TOKEN", "META_IG_USER_ID")
        return MetaClient(page_id, token, ig, cfg.secret("META_AD_LIBRARY_TOKEN"))

    def tiktok():
        from .tiktok import TikTokClient
        key, secret, refresh = _need(cfg, "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
        refresh = ctx.db.kv_get("tiktok_refresh_token", refresh)
        return TikTokClient(key, secret, refresh, lambda t: ctx.db.kv_set("tiktok_refresh_token", t))

    def inbox():
        user, pwd = _need(cfg, "SUPPORT_EMAIL", "SUPPORT_EMAIL_PASSWORD")
        return ImapInbox(cfg.get("support.imap_host"), int(cfg.get("support.imap_port", 993)), user, pwd)

    def support_sender():
        user, pwd = _need(cfg, "SUPPORT_EMAIL", "SUPPORT_EMAIL_PASSWORD")
        return SmtpSender(cfg.get("support.smtp_host"), int(cfg.get("support.smtp_port", 465)), user, pwd,
                          f"PrecisVis <{user}>")

    box = Toolbox(shopify=_Lazy("shopify", shopify), meta=_Lazy("meta", meta), tiktok=_Lazy("tiktok", tiktok),
                  inbox=_Lazy("inbox", inbox), report_sender=_Lazy("report", lambda: _real_report_sender(cfg)),
                  support_sender=_Lazy("support", support_sender), supplier=supplier)
    box.hosting = Hosting(ctx)
    return box


def _real_report_sender(cfg):
    if cfg.get("reporting.provider", "resend") == "resend":
        (key,) = _need(cfg, "RESEND_API_KEY")
        return ResendSender(key, cfg.get("reporting.from"))
    user, pwd = _need(cfg, "REPORT_SMTP_USER", "REPORT_SMTP_PASSWORD")
    return SmtpSender("smtp.gmail.com", 465, user, pwd, f"PrecisVis Agents <{user}>")
