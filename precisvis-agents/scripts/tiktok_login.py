"""Obtenir le premier TIKTOK_REFRESH_TOKEN (à faire une seule fois).

1. Dans votre application TikTok for Developers, ajoutez l'URL de redirection : https://precisvis.fr/
   (ou l'adresse de votre boutique, la même que ci-dessous).
2. Lancez :  python scripts/tiktok_login.py
3. Ouvrez le lien affiché, connectez le compte TikTok de PrecisVis, acceptez.
4. Vous arrivez sur votre boutique avec une adresse du type https://precisvis.fr/?code=XXXX&state=...
   Copiez toute cette adresse et collez-la dans le terminal.
5. Le script affiche le refresh token à enregistrer dans le secret GitHub TIKTOK_REFRESH_TOKEN.
"""
from __future__ import annotations

import os
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

REDIRECT = os.environ.get("TIKTOK_REDIRECT_URI", "https://precisvis.fr/")


def main() -> None:
    key = os.environ.get("TIKTOK_CLIENT_KEY") or input("TIKTOK_CLIENT_KEY : ").strip()
    secret = os.environ.get("TIKTOK_CLIENT_SECRET") or input("TIKTOK_CLIENT_SECRET : ").strip()
    state = secrets.token_urlsafe(8)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key": key, "scope": "user.info.basic,video.publish,video.upload,video.list",
        "response_type": "code", "redirect_uri": REDIRECT, "state": state})
    print("\nOuvrez ce lien dans votre navigateur :\n\n" + url + "\n")
    back = input("Collez ici l'adresse complète de la page sur laquelle vous êtes arrivé : ").strip()
    code = parse_qs(urlparse(back).query).get("code", [""])[0]
    if not code:
        sys.exit("Aucun code trouvé dans l'adresse collée.")
    res = httpx.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30).json()
    if "refresh_token" not in res:
        sys.exit(f"Échec : {res}")
    print("\nTIKTOK_REFRESH_TOKEN =", res["refresh_token"])
    print("(valable environ 1 an ; le système le renouvelle ensuite tout seul)")


if __name__ == "__main__":
    main()
