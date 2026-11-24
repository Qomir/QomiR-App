"""Doubles « simulés » de chaque service externe pour le mode --dry-run.

Données réalistes, déterministes pour une date donnée, aucun appel réseau.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .email import IncomingEmail

PRICE = 49.90


def _rnd(day: str, salt: str = "") -> random.Random:
    return random.Random(f"{day}:{salt}")


class FakeShopify:
    def __init__(self, day: str):
        self.day = day
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self._products = [
            {"id": "gid://shopify/Product/1001", "title": "Tournevis électrique de précision PrecisVis",
             "handle": "tournevis-electrique-precision", "status": "ACTIVE",
             "description_html": "<p>Tournevis électrique de précision avec embouts.</p>",
             "tags": ["outil", "précision"], "category": "Outils", "inventory": 140, "seo": {},
             "updated_at": "2026-11-01T10:00:00Z", "images": ["https://cdn.example/p1.jpg", "https://cdn.example/p2.jpg"],
             "variants": [{"id": "gid://shopify/ProductVariant/1", "title": "Standard", "price": PRICE, "inventory": 140}]},
            {"id": "gid://shopify/Product/1002", "title": "Tapis magnétique de réparation", "handle": "tapis-magnetique",
             "status": "DRAFT", "description_html": "", "tags": [], "category": "Accessoires", "inventory": 0, "seo": {},
             "updated_at": "2026-11-10T10:00:00Z", "images": [], "variants": [{"id": "v2", "title": "Standard", "price": 24.9, "inventory": 0}]},
        ]

    def _day_orders(self, day: str, n: int, rnd: random.Random) -> list[dict[str, Any]]:
        base = datetime.fromisoformat(day + "T08:00:00+01:00")
        out = []
        for i in range(n):
            qty = 2 if rnd.random() < 0.12 else 1
            src = rnd.choice(["tiktok", "instagram", "facebook", "tiktok", None, "google"])
            created = base + timedelta(minutes=rnd.randint(0, 720))
            out.append({
                "id": f"gid://shopify/Order/{day.replace('-', '')}{i}", "name": f"#{1000 + int(day[-2:]) * 10 + i}",
                "created_at": created.isoformat(), "cancelled": False, "email": f"client{i}@exemple.fr",
                "financial_status": "PAID", "fulfillment_status": "UNFULFILLED", "total": round(PRICE * qty, 2),
                "shipping_paid": 0.0, "refunded": 0.0,
                "lines": [{"title": "Tournevis électrique de précision PrecisVis", "qty": qty, "unit_cost": None}],
                "fulfillments": [], "utm_source": src, "utm_content": None,
            })
        return out

    def orders_since(self, since: datetime) -> list[dict[str, Any]]:
        out = []
        d = since.date()
        end = datetime.fromisoformat(self.day).date()
        while d <= end:
            rnd = _rnd(d.isoformat(), "orders")
            out += self._day_orders(d.isoformat(), rnd.randint(2, 7), rnd)
            d += timedelta(days=1)
        return [o for o in out if datetime.fromisoformat(o["created_at"]) >= since]

    def open_orders(self) -> list[dict[str, Any]]:
        now = datetime.fromisoformat(self.day + "T07:00:00+01:00").astimezone(timezone.utc)
        def order(name, hours_ago, fulfil_days_ago=None, tracking=True, delivered=False):
            created = (now - timedelta(hours=hours_ago)).isoformat()
            f = []
            if fulfil_days_ago is not None:
                f = [{"created_at": (now - timedelta(days=fulfil_days_ago)).isoformat(), "status": "SUCCESS",
                      "display_status": "IN_TRANSIT", "delivered_at": None, "in_transit_at": None,
                      "tracking": ["LP00" + name[1:] + "CN"] if tracking else []}]
            return {"id": name, "name": name, "created_at": created, "cancelled": False, "email": "client@exemple.fr",
                    "financial_status": "PAID", "fulfillment_status": "FULFILLED" if f else "UNFULFILLED",
                    "total": PRICE, "lines": [], "fulfillments": f}
        return [order("#1180", 6), order("#1172", 30), order("#1150", 200, 7), order("#1121", 400, 14),
                order("#1139", 160, 6, tracking=False), order("#1101", 500, 18)]

    def find_orders(self, email: str = "", name: str = "") -> list[dict[str, Any]]:
        for o in self.open_orders():
            if name and o["name"] == name:
                return [o]
        return [self.open_orders()[2]] if email else []

    def disputes(self) -> list[dict[str, Any]]:
        if _rnd(self.day, "dispute").random() < 0.35:
            return [{"id": "gid://shopify/ShopifyPaymentsDispute/77", "status": "NEEDS_RESPONSE", "amount": PRICE,
                     "reason": "PRODUCT_NOT_RECEIVED", "order": "#1101", "initiated_at": self.day + "T05:12:00Z"}]
        return []

    def products(self, query: str | None = None) -> list[dict[str, Any]]:
        return [dict(p) for p in self._products]

    def create_draft_product(self, p: dict[str, Any]) -> str:
        pid = f"gid://shopify/Product/sim-{len(self.created) + 1}"
        self.created.append({**p, "id": pid})
        return pid

    def update_product(self, product_id: str, **kwargs: Any) -> None:
        self.updated.append({"id": product_id, **kwargs})

    def upload_file(self, path: Path) -> str:
        return f"https://cdn.shopify.example/files/{path.name}"


class FakeMeta:
    def __init__(self, day: str):
        self.day = day
        self.published: list[dict[str, Any]] = []

    def _pub(self, kind: str, url: str, text: str) -> dict[str, str]:
        pid = f"sim_{kind}_{len(self.published) + 1}"
        self.published.append({"kind": kind, "url": url, "text": text, "id": pid})
        return {"id": pid, "permalink": f"https://simulation.local/{pid}"}

    def publish_facebook_photo(self, image_url: str, message: str): return self._pub("fb_photo", image_url, message)
    def publish_facebook_video(self, video_url: str, description: str): return self._pub("fb_video", video_url, description)
    def publish_instagram_image(self, image_url: str, caption: str): return self._pub("ig_image", image_url, caption)
    def publish_instagram_reel(self, video_url: str, caption: str): return self._pub("ig_reel", video_url, caption)

    def _metrics(self, pid: str, scale: int) -> dict[str, int]:
        r = random.Random(pid + self.day)
        views = r.randint(scale // 4, scale)
        return {"views": views, "likes": int(views * r.uniform(0.02, 0.07)), "comments": int(views * r.uniform(0.001, 0.006)),
                "shares": int(views * r.uniform(0.001, 0.01)), "saves": int(views * r.uniform(0.002, 0.012)),
                "clicks": int(views * r.uniform(0.004, 0.02))}

    def facebook_post_metrics(self, post_id: str): return self._metrics(post_id, 1800)
    def instagram_media_metrics(self, media_id: str): return self._metrics(media_id, 3500)

    def ad_library_search(self, terms: str, country: str = "FR", limit: int = 40) -> list[dict[str, Any]]:
        return [
            {"page_name": "OutilPro FR", "ad_creative_bodies": ["Fini les vis qui foirent. Le tournevis électrique qui fait le travail à ta place 🔧"],
             "ad_creative_link_titles": ["Kit 50 embouts inclus"], "ad_delivery_start_time": "2026-09-02", "publisher_platforms": ["facebook", "instagram"]},
            {"page_name": "RepairLab", "ad_creative_bodies": ["Réparer sa manette soi-même ? En 3 minutes avec le bon outil."],
             "ad_creative_link_titles": ["Le tournevis des réparateurs"], "ad_delivery_start_time": "2026-10-15", "publisher_platforms": ["instagram"]},
            {"page_name": "MakerShop", "ad_creative_bodies": ["Maquettistes : couple réglable, aucune vis abîmée."],
             "ad_creative_link_titles": ["Précision au 1/10e"], "ad_delivery_start_time": "2026-08-20", "publisher_platforms": ["facebook"]},
        ]


class FakeTikTok:
    def __init__(self, day: str):
        self.day = day
        self.published: list[dict[str, Any]] = []

    def publish_video(self, path: Path, caption: str, privacy_level: str) -> dict[str, str]:
        pid = f"sim_tt_{len(self.published) + 1}"
        self.published.append({"path": str(path), "caption": caption, "privacy": privacy_level, "id": pid})
        return {"id": pid, "permalink": f"https://simulation.local/{pid}"}

    def video_metrics(self, video_ids: list[str]) -> dict[str, dict[str, int]]:
        out = {}
        for vid in video_ids:
            r = random.Random(vid + self.day)
            views = r.randint(800, 12000)
            out[vid] = {"views": views, "likes": int(views * r.uniform(0.03, 0.09)),
                        "comments": int(views * r.uniform(0.001, 0.005)), "shares": int(views * r.uniform(0.002, 0.012))}
        return out


class FakeInbox:
    def __init__(self, day: str):
        self.day = day
        self.handled: list[tuple[str, str | None]] = []

    def unread(self, limit: int = 30) -> list[IncomingEmail]:
        msgs = [
            ("m1", "julien.r@exemple.fr", "Où en est ma commande #1150 ?",
             "Bonjour, j'ai commandé il y a une semaine, pouvez-vous me donner le suivi ? Merci, Julien"),
            ("m2", "claire.m@exemple.fr", "Embout pour montre",
             "Bonjour, est-ce que le tournevis convient pour changer la pile d'une montre ? Quels embouts utiliser ?"),
            ("m3", "marc.d@exemple.fr", "Remboursement",
             "Bonjour, le produit ne me convient pas, je souhaite être remboursé. Commande #1121."),
            ("m4", "colere@exemple.fr", "INADMISSIBLE",
             "Toujours pas reçu ma commande #1101 après 18 jours, c'est une arnaque, j'ai ouvert un litige PayPal et je contacte un avocat."),
        ]
        return [IncomingEmail(uid=u, message_id=f"<{u}@sim>", sender=s, subject=sub, body=b) for u, s, sub, b in msgs][:limit]

    def mark_handled(self, uid: str, label: str | None = None) -> None:
        self.handled.append((uid, label))
