"""LLM gratuits : palier gratuit de l'API Gemini et/ou Ollama en local, avec repli automatique.

L'ordre est défini par `llm.providers` dans config.yaml. Chaque appel demande du JSON strict.
"""
from __future__ import annotations

import json
import re
import time

import requests

from . import log
from .config import env, load

L = log.get("llm")


class LLMError(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError("Réponse LLM non JSON")
        return json.loads(m.group(0))


def _gemini(system: str, prompt: str, temperature: float) -> dict:
    key = env("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY absent")
    model = env("GEMINI_MODEL") or load()["llm"]["gemini_model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    for attempt in range(3):
        r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=120)
        if r.status_code in (429, 500, 503):  # quota/minute du palier gratuit : on patiente
            time.sleep(20 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
        try:
            return _parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"Réponse Gemini inattendue : {r.text[:300]}") from e
    raise LLMError("Gemini : quota gratuit épuisé ou service indisponible")


def _ollama(system: str, prompt: str, temperature: float) -> dict:
    host = env("OLLAMA_HOST") or "http://localhost:11434"
    model = env("OLLAMA_MODEL") or load()["llm"]["ollama_model"]
    r = requests.post(f"{host}/api/chat", timeout=1800, json={
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": temperature, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}]})
    if r.status_code != 200:
        raise LLMError(f"Ollama HTTP {r.status_code}: {r.text[:300]}")
    return _parse_json(r.json()["message"]["content"])


PROVIDERS = {"gemini": _gemini, "ollama": _ollama}


def generate_json(system: str, prompt: str, temperature: float = 0.8) -> dict:
    errors = []
    for name in load()["llm"]["providers"]:
        try:
            return PROVIDERS[name](system, prompt, temperature)
        except Exception as e:
            L.warning("LLM %s en échec : %s", name, e)
            errors.append(f"{name}: {e}")
    raise LLMError("Aucun LLM disponible — " + " ; ".join(errors))
