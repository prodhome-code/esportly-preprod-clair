"""Top plays du Blog : pour chaque jeu, au plus 3 vidéos récentes des chaînes YouTube officielles, choisies chaque matin.

Lit blog-src/channels.json (les chaînes validées de chaque jeu) puis le flux de chacune, garde les vidéos récentes les plus vues
dont l'intégration est autorisée, et réécrit blog-src/topplays.json que blog.py affiche. Lancé chaque matin par le job « Matchs du
jour » (étape « Top plays du moment »), avant « Mise à jour du blog ». Le script ne décide rien : il applique la liste de chaînes,
et, pour une chaîne qui a un champ `include` (expression régulière), seulement ses vidéos dont le titre la contient (temps forts).
Spécification : docs/superpowers/specs/2026-10-27-blog-design.md (§7 et §14)

    py -3.13 .github/scripts/topplays.py             # choisit et écrit
    py -3.13 .github/scripts/topplays.py --essai     # dit ce qui changerait, sans rien écrire
    py -3.13 .github/scripts/topplays.py --verifier  # valide seulement blog-src/channels.json (sans base des fuseaux)

Le choix (select_videos) et la lecture du flux (read_feed) ne touchent pas au réseau par eux-mêmes : le flux et la page oEmbed
arrivent par les fonctions `fetch` et `status`, que les tests remplacent. La sélection de la veille d'un jeu dont une chaîne ne
répond pas, ou dont la page oEmbed est en panne (OutageError), est gardée telle quelle.
"""
from __future__ import annotations

import http.client
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

import actualites as an
import blog

ROOT = Path(__file__).resolve().parents[2]
TOPPLAYS = "blog-src/topplays.json"

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id="  # flux Atom d'une chaîne, suivi de son identifiant
OEMBED = "https://www.youtube.com/oembed?format=json&url="  # répond 200 seulement pour une vidéo dont l'intégration est autorisée
WATCH = "https://www.youtube.com/watch?v="
NAMESPACES = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
ATOM_FEED = "{" + NAMESPACES["atom"] + "}feed"  # nom de l'élément racine d'un flux Atom, espace de noms compris

SHORT_WINDOW = 7  # jours : fenêtre habituelle
LONG_WINDOW = 21  # jours : fenêtre quand la courte compte moins de MAX_VIDEOS vidéos
MAX_VIDEOS = 3
TITLE_LENGTH = 100
CHANNEL_LENGTH = 60

LIVE = re.compile(r"\b(?:live|livestream|replay|full vod|full match|shorts|vertical)\b", re.I)  # mots entiers : « Alive », « Delivery », « Shortstop » restent ; « #shorts » part
CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x84\x86-\x9f]")  # caractères de contrôle ; tabulation, retours à la ligne et \x85 sont des espaces


# --- Réseau -----------------------------------------------------------------------------------------------------

def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": blog.USER_AGENT})


def http_get(url: str) -> str:
    """Le texte d'une adresse (UTF-8, 2 000 000 d'octets au plus) ; toute panne est levée telle quelle : read_feed retente."""
    with urllib.request.urlopen(_request(url), timeout=blog.FETCH_TIMEOUT) as response:
        return response.read(blog.FETCH_MAX_BYTES).decode("utf-8")


def http_status(url: str) -> int:
    """Le code HTTP d'une adresse. Un code d'erreur HTTP est rendu tel quel ; une panne réseau est retentée une fois, puis rend 0."""
    for _ in range(2):
        try:
            with urllib.request.urlopen(_request(url), timeout=blog.FETCH_TIMEOUT) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code
        except (OSError, http.client.HTTPException, ValueError):  # dont délai dépassé, connexion refusée ou coupée
            pass
    return 0


# --- Flux ---------------------------------------------------------------------------------------------------------

def _paris_day(text: str, paris) -> date | None:
    """Le jour de Paris d'un horodatage ISO 8601 (sans fuseau : UTC) ; None s'il est illisible."""
    try:
        moment = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(paris).date()


def _views(statistics) -> int:
    """Le nombre de vues de media:statistics ; 0 s'il manque ou s'il n'est pas un entier."""
    try:
        return max(0, int(statistics.get("views", "0")))
    except (AttributeError, ValueError):
        return 0


def _parse_feed(text: str, paris) -> list[dict]:
    if "<!DOCTYPE" in text or "<!ENTITY" in text:  # un flux YouTube n'a ni DTD ni entités : un tel texte vient d'ailleurs (donnée de tiers)
        raise ValueError("flux avec DTD ou entités, refusé")
    root = ET.fromstring(text)
    if root.tag != ATOM_FEED:  # une page d'erreur ou un autre document bien formé n'est pas « une chaîne sans vidéo » : c'est une panne
        raise ValueError("pas un flux Atom")
    entries = []
    for node in root.findall("atom:entry", NAMESPACES):
        video_id = node.findtext("yt:videoId", "", NAMESPACES).strip()
        published = _paris_day(node.findtext("atom:published", "", NAMESPACES), paris)
        if not video_id or published is None:
            continue
        statistics = node.find("media:group/media:community/media:statistics", NAMESPACES)
        entries.append({"id": video_id, "title": node.findtext("atom:title", "", NAMESPACES),
                        "channel": node.findtext("atom:author/atom:name", "", NAMESPACES),
                        "published": published, "views": _views(statistics)})
    return entries


def read_feed(channel_id: str, fetch: Callable[[str], str] = http_get) -> list[dict] | None:
    """Les vidéos d'une chaîne (id, title, channel, published en jour de Paris, views) ; None si le flux n'est pas lisible après un second essai."""
    paris = an.paris()  # hors du try : une base des fuseaux absente ne doit pas passer pour une panne de la chaîne
    for _ in range(2):
        try:
            return _parse_feed(fetch(FEED + channel_id), paris)
        except Exception as error:  # une chaîne indisponible ne bloque pas les autres
            print(f"{channel_id} : {error}")
    return None


class OutageError(Exception):
    """La page oEmbed ne répond pas (aucune réponse, 429 ou 5xx) : on ne sait pas si la vidéo est intégrable.

    Ce n'est pas un refus : select_videos la laisse passer et refresh garde la sélection de la veille du jeu, comme pour une chaîne en panne.
    """


def oembed_ok(video_id: str, status: Callable[[str], int] = http_status) -> bool:
    """Vrai si YouTube autorise l'intégration de la vidéo : sa page oEmbed répond 200.

    Faux pour un refus (400, 401, 403, 404 et tout autre code, comme 204 ou 410) : la vidéo est écartée. Lève OutageError pour une panne :
    code 0 (aucune réponse après le second essai), 429 (trop de requêtes) ou 5xx.
    """
    code = status(OEMBED + quote(WATCH + video_id, safe=""))
    if code == 200:
        return True
    if code == 0 or code == 429 or code >= 500:
        raise OutageError(f"oEmbed de {video_id} : {'pas de réponse' if code == 0 else f'code {code}'}")
    return False


# --- Sélection ----------------------------------------------------------------------------------------------------

def _tidy(text: str) -> str:
    """Le texte sans caractères de contrôle, les espaces repliées en une seule, sans espace au début ni à la fin."""
    return " ".join(CONTROL.sub("", text).split())


def _cut(text: str, longest: int) -> str:
    """Au plus `longest` caractères : un texte plus long est coupé aux `longest - 1` premiers, sans espace de fin, puis « … »."""
    return text if len(text) <= longest else text[:longest - 1].rstrip() + "…"


def clean_title(title: str, longest: int = TITLE_LENGTH) -> str:
    """Un titre (ou un nom de chaîne, avec `longest`) de tiers prêt à être écrit dans topplays.json : l'échappement est fait à l'affichage."""
    return _cut(_tidy(title), longest)


def select_videos(videos: list[dict], now: datetime, is_embeddable: Callable[[str], bool], includes: dict[str, str] | None = None) -> list[dict]:
    """Les (3 au plus) vidéos à montrer pour un jeu, parmi toutes celles de toutes ses chaînes.

    `includes` associe l'identifiant d'une chaîne (UC…) à son expression `include` de channels.json : une vidéo dont la clé `channel_id`
    est dans `includes` n'est candidate que si son titre la contient (insensible à la casse). On indexe par identifiant, et non par nom :
    le nom du flux (media:author) peut différer du nom de channels.json ; refresh ajoute `channel_id` à chaque vidéo qu'il lit.
    Une vidéo sans `channel_id`, ou d'une chaîne sans expression, n'est pas filtrée. Ce filtre passe avant le classement et avant le
    calcul de la fenêtre : le seuil de 3 vidéos compte les vidéos qualifiées. S'il y en a moins de 3 sur 21 jours on en montre moins,
    et aucune donne une liste vide.

    Garde celles publiées les 7 derniers jours (jour de Paris), ou les 21 derniers s'il y en a moins de 3 ; écarte les directs,
    rediffusions, shorts et vidéos verticales (mots entiers du titre), les identifiants invalides, les titres ou chaînes vides et les dates futures ; classe par vues décroissantes (égalité :
    la plus récente, puis l'identifiant) et garde les premières dont is_embeddable est vrai, sans interroger les suivantes.
    Une panne (OutageError levée par is_embeddable) n'est pas rattrapée : c'est à l'appelant de décider quoi garder.
    """
    today = now.astimezone(an.paris()).date()
    patterns = {channel_id: re.compile(pattern, re.I) for channel_id, pattern in (includes or {}).items()}  # même compilation que blog.load_channels
    candidates, seen = [], set()
    for video in videos:
        title, channel = _tidy(video["title"]), clean_title(video["channel"], CHANNEL_LENGTH)
        age = (today - video["published"]).days
        pattern = patterns.get(video.get("channel_id"))
        if (not blog.VIDEO_ID.fullmatch(video["id"]) or not title or not channel or LIVE.search(title)  # le mot compte même au-delà de la coupe
                or not 0 <= age <= LONG_WINDOW or (pattern and not pattern.search(title))  # de même pour l'expression `include`
                or video["id"] in seen):  # écartée avant `seen` : la même vidéo reste candidate par une chaîne sans filtre
            continue
        seen.add(video["id"])
        candidates.append({"id": video["id"], "title": _cut(title, TITLE_LENGTH), "channel": channel, "published": video["published"],
                           "views": video["views"], "age": age})
    recent = [video for video in candidates if video["age"] <= SHORT_WINDOW]
    pool = recent if len(recent) >= MAX_VIDEOS else candidates
    pool.sort(key=lambda video: (-video["views"], -video["published"].toordinal(), video["id"]))
    chosen = []
    for video in pool:
        if is_embeddable(video["id"]):
            chosen.append({"id": video["id"], "title": video["title"], "channel": video["channel"], "published": video["published"].isoformat()})
            if len(chosen) == MAX_VIDEOS:
                break
    return chosen


# --- Rafraîchissement ---------------------------------------------------------------------------------------------

def _read(path: Path) -> str | None:
    """Le texte du fichier avec ses fins de ligne, None s'il n'existe pas (Path.read_text n'a `newline` que depuis Python 3.13 ; le job est en 3.12)."""
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", newline="") as file:
        return file.read()


def _fresh_entry(game: str, game_channels: list[dict], now: datetime, fetch: Callable[[str], str], status: Callable[[str], int]) -> dict | None:
    """L'entrée du jour d'un jeu ; None si une de ses chaînes ne répond pas ou si la page oEmbed est en panne (il garde alors la veille)."""
    feeds = [read_feed(channel["id"], fetch) for channel in game_channels]
    if any(feed is None for feed in feeds):
        return None
    entries = [{**entry, "channel_id": channel["id"]} for channel, feed in zip(game_channels, feeds) for entry in feed]  # d'où vient chaque vidéo
    includes = {channel["id"]: channel["include"] for channel in game_channels if "include" in channel}  # déjà validées par load_channels
    try:
        videos = select_videos(entries, now, lambda video_id: oembed_ok(video_id, status), includes)
    except OutageError as error:  # ni refus ni accord : une liste vide effacerait la bonne sélection de la veille
        print(f"{game} : {error}")
        return None
    return {"fetched": now.astimezone(an.paris()).date().isoformat(), "videos": videos}


def refresh(root: Path, now: datetime, fetch: Callable[[str], str] = http_get, status: Callable[[str], int] = http_status) -> dict[str, str]:
    """Calcule en mémoire le nouveau blog-src/topplays.json ; rend {"blog-src/topplays.json": texte} seulement si son contenu change.

    Un jeu n'est mis à jour que si toutes ses chaînes répondent et que la page oEmbed ne tombe pas en panne : sinon sa sélection de la
    veille reste telle quelle (`fetched` compris), et un jeu jamais relevé reste absent ; les autres jeux sont mis à jour. Les jeux absents
    de channels.json, ou sans chaîne, n'ont pas d'entrée. Le fichier garde ses fins de ligne (CRLF en local) ; un fichier neuf est en LF.
    """
    channels, previous = blog.load_channels(root), blog.load_topplays(root)
    result = {}
    for game, game_channels in channels.items():
        if not game_channels:
            continue
        entry = _fresh_entry(game, game_channels, now, fetch, status)
        if entry is not None:
            result[game] = entry
        elif game in previous:
            result[game] = previous[game]
    old = _read(root / TOPPLAYS)
    if old is None and not result:  # un fichier absent vaut {} : rien à créer
        return {}
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if old is not None:
        text = an.same_eol(text, old)
    return {} if text == old else {TOPPLAYS: text}


# --- Ligne de commande ------------------------------------------------------------------------------------------

def main(argv: list[str], root: Path = ROOT, now: datetime | None = None, fetch: Callable[[str], str] = http_get,
         status: Callable[[str], int] = http_status) -> int:
    """Ligne de commande (voir le haut du fichier). `fetch` et `status` remplacent le réseau dans les tests."""
    trial = "--essai" in argv
    try:
        if "--verifier" in argv:
            blog.load_channels(root)
            print("blog-src/channels.json : valide")
            return 0
        changes = refresh(root, now or datetime.now(timezone.utc), fetch, status)
    except blog.BlogError as error:
        print(f"Refus : {len(error.problems)} problème(s)", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if not trial:
        for name, content in changes.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="")
    print(f"{len(changes)} fichier(s) {'à changer' if trial else 'changé(s)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
