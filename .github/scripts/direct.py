"""Trouver le direct d'une compétition, au lieu de l'écrire à la main.

Deux adresses en dur suffisent à casser un lecteur : une chaîne Twitch renommée (« esl_csgo » renvoie vers « eslcs », et le
lecteur affiche « hors ligne »), une chaîne YouTube qui n'est pas celle qui diffuse. Ce module va donc **demander** :

- `twitch_login` : le vrai nom de la chaîne Twitch, celui que le lecteur accepte, lu dans l'adresse canonique de sa page ;
- `youtube_live` : le direct en cours d'une chaîne YouTube (son identifiant de vidéo), lu sur sa page « /live ».

Une question par chaîne et par exécution (mémoire `_SEEN`), 12 secondes d'attente au plus, et aucune erreur n'est propagée :
sans réponse, le site retombe sur ce que dit le tableau de `diffusions.py`.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "en"}
CANONICAL = re.compile(r'<meta property="og:url" content="https://www\.twitch\.tv/([A-Za-z0-9_]+)"')
LINK = re.compile(r'<link rel="canonical" href="https://www\.twitch\.tv/([A-Za-z0-9_]+)"')
VIDEO = re.compile(r'"videoId":"([\w-]{11})"')
_SEEN: dict[str, str | None] = {}


def _get(url: str) -> str | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=12) as answer:
            return answer.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def twitch_login(name: str) -> str:
    """Le nom de chaîne que le lecteur Twitch accepte. Une chaîne renommée garde son ancienne adresse, mais le lecteur, lui, ne
    suit pas la redirection : il affiche « hors ligne » alors que la chaîne diffuse. Le nom d'origine est rendu tel quel quand
    la question échoue."""
    key = f"twitch:{name}"
    if key not in _SEEN:
        page = _get(f"https://www.twitch.tv/{name}")
        found = (CANONICAL.search(page) or LINK.search(page)) if page else None
        _SEEN[key] = found.group(1) if found else None
    return _SEEN[key] or name


def youtube_live(channel: str) -> str | None:
    """L'identifiant de la vidéo que la chaîne diffuse en ce moment, None si elle ne diffuse pas. La page « /live » d'une chaîne
    mène à son direct ; sans direct, elle n'en porte pas la marque et rien n'est rendu — on ne montre pas une rediffusion à la
    place d'un match."""
    key = f"youtube:{channel}"
    if key not in _SEEN:
        page = _get(f"https://www.youtube.com/channel/{channel}/live")
        found = VIDEO.search(page) if page and '"isLive":true' in page else None
        _SEEN[key] = found.group(1) if found else None
    return _SEEN[key]


def forget() -> None:
    """Vide la mémoire des questions déjà posées (les tests s'en servent)."""
    _SEEN.clear()
