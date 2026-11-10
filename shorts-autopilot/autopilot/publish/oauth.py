"""Jetons OAuth : stockage local (data/tokens.json, droits 600) et rafraîchissement automatique.

Aucun mot de passe n'est stocké : uniquement les jetons délivrés par les plateformes
après VOTRE consentement dans le navigateur (commande `python -m autopilot auth <plateforme>`).
"""
from __future__ import annotations

import json
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .. import log
from ..config import DATA_DIR, env, load

L = log.get("oauth")
STORE = DATA_DIR / "tokens.json"

YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
             "https://www.googleapis.com/auth/youtube.readonly",
             "https://www.googleapis.com/auth/yt-analytics.readonly"]
TT_SCOPES = "user.info.basic,video.publish,video.upload,video.list"


def _load() -> dict:
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def _save(platform: str, data: dict) -> None:
    allt = _load()
    allt[platform] = {**allt.get(platform, {}), **data}
    STORE.write_text(json.dumps(allt, indent=2))
    os.chmod(STORE, 0o600)


def get(platform: str) -> dict:
    return _load().get(platform, {})


def _ask_redirect(auth_url: str) -> dict:
    print("\n1) Ouvrez cette adresse dans votre navigateur et autorisez l'accès :\n")
    print(auth_url)
    print("\n2) Vous êtes redirigé vers une page (qui peut afficher une erreur : c'est normal).")
    pasted = input("3) Copiez l'adresse COMPLÈTE de cette page et collez-la ici :\n> ").strip()
    params = {k: v[0] for k, v in parse_qs(urlparse(pasted).query).items()}
    if "code" not in params:
        raise SystemExit(f"Pas de code d'autorisation dans l'adresse collée ({params.get('error', '?')}).")
    return params


# ── YouTube (Google OAuth, client de type « Application de bureau ») ─────────────
def youtube_login() -> None:
    redirect = env("YOUTUBE_REDIRECT_URI") or "http://localhost:8765"
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": env("YOUTUBE_CLIENT_ID"), "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(YT_SCOPES), "access_type": "offline", "prompt": "consent", "state": state})
    params = _ask_redirect(url)
    if params.get("state") != state:
        raise SystemExit("Paramètre state inattendu : recommencez.")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": params["code"], "client_id": env("YOUTUBE_CLIENT_ID"),
        "client_secret": env("YOUTUBE_CLIENT_SECRET"), "redirect_uri": redirect,
        "grant_type": "authorization_code"})
    r.raise_for_status()
    tok = r.json()
    _save("youtube", {"refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
                      "expires_at": time.time() + tok["expires_in"] - 60})
    print("✅ YouTube connecté.")


def youtube_token() -> str:
    t = get("youtube")
    if not t.get("refresh_token"):
        raise RuntimeError("YouTube non connecté : lancez `python -m autopilot auth youtube`")
    if t.get("expires_at", 0) > time.time():
        return t["access_token"]
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": env("YOUTUBE_CLIENT_ID"), "client_secret": env("YOUTUBE_CLIENT_SECRET"),
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        # invalid_grant = jeton révoqué, ou écran de consentement resté en mode « Test » (7 jours)
        raise RuntimeError(f"Rafraîchissement YouTube refusé ({r.text[:200]}). "
                           "Relancez `auth youtube` (et passez l'app Google « En production »).")
    tok = r.json()
    _save("youtube", {"access_token": tok["access_token"],
                      "expires_at": time.time() + tok["expires_in"] - 60})
    return tok["access_token"]


# ── TikTok (Login Kit, flux web) ─────────────────────────────────────────────────
def tiktok_login() -> None:
    redirect = env("TIKTOK_REDIRECT_URI")
    state = secrets.token_urlsafe(16)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key": env("TIKTOK_CLIENT_KEY"), "scope": TT_SCOPES, "response_type": "code",
        "redirect_uri": redirect, "state": state})
    params = _ask_redirect(url)
    if params.get("state") != state:
        raise SystemExit("Paramètre state inattendu : recommencez.")
    _tiktok_exchange({"code": params["code"], "grant_type": "authorization_code",
                      "redirect_uri": redirect})
    print("✅ TikTok connecté.")


def _tiktok_exchange(extra: dict) -> dict:
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": env("TIKTOK_CLIENT_KEY"),
                            "client_secret": env("TIKTOK_CLIENT_SECRET"), **extra})
    tok = r.json()
    if "access_token" not in tok:
        raise RuntimeError(f"TikTok OAuth refusé : {tok}")
    _save("tiktok", {"access_token": tok["access_token"], "refresh_token": tok["refresh_token"],
                     "open_id": tok.get("open_id"),
                     "expires_at": time.time() + tok["expires_in"] - 300})
    return tok


def tiktok_token() -> str:
    t = get("tiktok")
    if not t.get("refresh_token"):
        raise RuntimeError("TikTok non connecté : lancez `python -m autopilot auth tiktok`")
    if t.get("expires_at", 0) > time.time():
        return t["access_token"]
    return _tiktok_exchange({"grant_type": "refresh_token",
                             "refresh_token": t["refresh_token"]})["access_token"]


# ── Instagram (API Instagram avec connexion Instagram, jeton longue durée 60 j) ──
def _ig_base() -> str:
    return f"https://graph.instagram.com/{load()['platforms']['instagram']['api_version']}"


def instagram_login() -> None:
    token = env("INSTAGRAM_ACCESS_TOKEN") or input(
        "Collez le jeton longue durée généré dans le tableau de bord Meta :\n> ").strip()
    r = requests.get(f"{_ig_base()}/me", params={"fields": "user_id,username",
                                                 "access_token": token}, timeout=30)
    r.raise_for_status()
    me = r.json()
    _save("instagram", {"access_token": token, "user_id": str(me["user_id"]),
                        "username": me.get("username"), "refreshed_at": time.time()})
    print(f"✅ Instagram connecté : @{me.get('username')}")


def instagram_token() -> tuple[str, str]:
    t = get("instagram")
    if not t.get("access_token"):
        raise RuntimeError("Instagram non connecté : lancez `python -m autopilot auth instagram`")
    return t["access_token"], t["user_id"]


def instagram_refresh() -> None:
    """Prolonge le jeton de 60 jours (à appeler régulièrement : fait par le planificateur)."""
    t = get("instagram")
    if not t.get("access_token") or time.time() - t.get("refreshed_at", 0) < 7 * 86400:
        return
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=30,
                     params={"grant_type": "ig_refresh_token", "access_token": t["access_token"]})
    if r.status_code == 200:
        _save("instagram", {"access_token": r.json()["access_token"], "refreshed_at": time.time()})
        L.info("Jeton Instagram prolongé")
    else:
        raise RuntimeError(f"Prolongation du jeton Instagram refusée : {r.text[:200]}")
