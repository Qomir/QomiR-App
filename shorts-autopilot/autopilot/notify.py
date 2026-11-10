"""Notifications Telegram (Bot API officielle, gratuite). Sans token : simple log."""
from __future__ import annotations

from pathlib import Path

import requests

from . import log
from .config import env

L = log.get("notify")
API = "https://api.telegram.org/bot{token}/{method}"


def _enabled() -> bool:
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def _call(method: str, data: dict | None = None, files: dict | None = None, timeout: int = 60):
    url = API.format(token=env("TELEGRAM_BOT_TOKEN"), method=method)
    r = requests.post(url, data=data, files=files, timeout=timeout)
    r.raise_for_status()
    return r.json().get("result")


def send(text: str) -> None:
    L.info("[telegram] %s", text.replace("\n", " | "))
    if not _enabled():
        return
    try:
        _call("sendMessage", {"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[:4000],
                              "disable_web_page_preview": "true"})
    except Exception as e:  # une notif ratée ne doit jamais casser le pipeline
        L.warning("Telegram indisponible : %s", e)


def error(context: str, exc: Exception | str) -> None:
    send(f"❌ ERREUR — {context}\n{exc}")


def send_video(path: Path, caption: str, video_id: str | None = None,
               with_buttons: bool = False) -> None:
    """Envoie la vidéo (limite Bot API : 50 Mo) avec boutons Valider/Rejeter optionnels."""
    if not _enabled():
        return
    data = {"chat_id": env("TELEGRAM_CHAT_ID"), "caption": caption[:1000],
            "supports_streaming": "true"}
    if with_buttons and video_id:
        import json
        data["reply_markup"] = json.dumps({"inline_keyboard": [[
            {"text": "✅ Publier", "callback_data": f"ok:{video_id}"},
            {"text": "⛔ Rejeter", "callback_data": f"no:{video_id}"}]]})
    try:
        if path.stat().st_size > 49 * 1024 * 1024:
            data["text"] = caption + f"\n(vidéo trop lourde pour Telegram : {path})"
            data.pop("caption")
            data.pop("supports_streaming")
            _call("sendMessage", data)
        else:
            with open(path, "rb") as f:
                _call("sendVideo", data, files={"video": f}, timeout=300)
    except Exception as e:
        L.warning("Envoi vidéo Telegram impossible : %s", e)


def poll_decisions() -> list[tuple[str, str]]:
    """Lit les clics sur les boutons. Renvoie [(video_id, 'approved'|'rejected')]."""
    if not _enabled():
        return []
    from . import db
    offset = db.kv_get("tg_offset", 0)
    out = []
    try:
        updates = _call("getUpdates", {"offset": offset, "timeout": 0,
                                       "allowed_updates": '["callback_query"]'}) or []
    except Exception as e:
        L.warning("getUpdates : %s", e)
        return []
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq:
            continue
        # Seul le propriétaire (TELEGRAM_CHAT_ID) peut décider
        if str(cq.get("from", {}).get("id")) != env("TELEGRAM_CHAT_ID") and \
           str(cq.get("message", {}).get("chat", {}).get("id")) != env("TELEGRAM_CHAT_ID"):
            continue
        action, _, vid = (cq.get("data") or "").partition(":")
        if action in ("ok", "no") and vid:
            decision = "approved" if action == "ok" else "rejected"
            out.append((vid, decision))
            try:
                _call("answerCallbackQuery", {"callback_query_id": cq["id"],
                                              "text": "Validée ✅" if action == "ok" else "Rejetée ⛔"})
            except Exception:
                pass
    db.kv_set("tg_offset", offset)
    return out
