"""Partie « Blog » du site : une fiche par jeu, des guides et des notes de version, sources citées, top plays.

Lit blog-src/ (pages/<id>.json, channels.json, topplays.json), les valide, puis écrit les pages et les accueils du Blog,
le lien de guide des pages de jeux et le bloc du Blog dans le sitemap. Lancé chaque matin par le job « Matchs du jour »
et à la main pour publier une page.
Spécification : docs/superpowers/specs/2026-10-27-blog-design.md

    py -3.13 .github/scripts/blog.py             # génère
    py -3.13 .github/scripts/blog.py --essai     # dit ce qui changerait, sans rien écrire
    py -3.13 .github/scripts/blog.py --verifier  # valide seulement blog-src/ (sans modèles ni base des fuseaux)
    py -3.13 .github/scripts/blog.py --sources   # contrôle les sources citées (réseau, à la demande, jamais dans le job) ; n'écrit rien

La génération, et --sources dès qu'une page existe, demandent la base des fuseaux (PYTHONTZPATH ou tzdata sous Windows).
"""
from __future__ import annotations

import base64
import hashlib
import html
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
import warnings
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import actualites as an
import bascule_appstore
import site_chrome
from site_chrome import (CSP_META, FILTER_STYLE, FOOTER_STYLE, GAME_DIRS, GAMES, HUBS, LIVE_PAGES, MENU, MENU_HASH, MENU_ICONS, MENU_JS, MENU_STYLE,
                         MENU_STYLE_OWN, SCRIPT_SRC, THEME_ICONS, VISIT)  # HUBS : les accueils du Blog, aussi ceux que le menu des pages News vise

ROOT = Path(__file__).resolve().parents[2]
_eol = site_chrome.eol

BLOG_DIRS = site_chrome.BLOG_DIRS  # une page par article : <dossier>/<id>.html (partagé avec les News, dont les cartes y mènent)

KINDS = ("game", "guide", "release", "news")  # news : l'article d'une carte des News (news/news.json, link {"blog": <id>})
PAGE_KEYS = {"kind", "game", "date", "updated", "image", "sources", "sections", *an.LANGS}
IMAGE_KEYS = {"kind", "credit", "url", "file"}  # file : réutiliser la couverture d'une autre page (couvertures/<file>.webp), par exemple celle du jeu
IMAGE_KINDS = ("ia", "officielle")  # couverture : illustration générée par IA, ou image d'un éditeur créditée avec sa source
SOURCE_KEYS = {"id", "title", "url"}
SECTION_KEYS = {"cite", *an.LANGS}
BODY_KEYS = {"heading", "text"}
HEADER_KEYS = {"title", "description"}
CHANNEL_KEYS = {"id", "name", "proof", "include"}
TOPPLAYS_KEYS = {"fetched", "videos"}
VIDEO_KEYS = {"id", "title", "channel", "published"}

DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SOURCE_ID = re.compile(r"s[0-9]+")
CHANNEL_ID = re.compile(r"UC[0-9A-Za-z_-]{22}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
INCLUDE_LENGTH = 200  # caractères au plus pour l'expression `include` d'une chaîne
TOPPLAYS_MAX_AGE = timedelta(days=14)  # au-delà, la sélection du matin est jugée périmée et n'est pas affichée

_UNREADABLE = object()  # rendu par _read_json quand le fichier est illisible (le problème est déjà noté)


class BlogError(an.NewsError):
    """Données du Blog invalides : `problems` liste tout ce qui ne va pas, et rien n'est écrit."""


# --- Aides communes ---------------------------------------------------------------------------------------------

class _Report:
    """Problèmes d'un fichier : chacun commence par le nom du fichier puis le chemin JSON de la valeur en cause."""

    def __init__(self, file: str, problems: list[str]):
        self.file, self.problems = file, problems

    def add(self, path: str, message: str) -> None:
        self.problems.append(f"{self.file} : {path} : {message}" if path else f"{self.file} : {message}")


def _at(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _parse_date(value) -> date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _read_json(path: Path, problems: list[str]):
    """Contenu JSON d'un fichier ; _UNREADABLE (et un problème noté) s'il n'est pas lisible."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        problems.append(f"{path.name} : illisible : {error}")
        return _UNREADABLE


def _missing_game_pages(root: Path, game: str) -> list[str]:
    """Pages d'un jeu qui manquent : games/<jeu>.html et ses 4 équivalents. Vide quand le jeu existe."""
    return [f"{folder}/{game}.html" for folder in GAME_DIRS.values() if not (root / folder / f"{game}.html").is_file()]


def _check_game_name(r: _Report, path: str, game, root: Path) -> None:
    """Le nom d'un jeu (clé de channels.json) : un identifiant, et un jeu dont les 5 pages existent."""
    if not isinstance(game, str) or not an.ID.fullmatch(game):
        r.add(path, "identifiant de jeu invalide")
    elif missing := _missing_game_pages(root, game):
        r.add(path, f"jeu introuvable (pages manquantes : {', '.join(missing)})")


def _check_unknown(r: _Report, path: str, entry: dict, allowed) -> None:
    for key in entry:
        if key not in allowed:
            r.add(path, f"champ inconnu « {key} »")


def _check_length(r: _Report, path: str, value, longest: int | None = None) -> None:
    """Un texte de 1 caractère au moins (`longest` au plus, s'il est donné), compté en caractères Unicode."""
    if not isinstance(value, str):
        r.add(path, "manquant" if value is None else "doit être un texte")
    elif not value:
        r.add(path, "vide" if longest is None else f"0 caractères (1 à {longest} attendus)")
    elif longest is not None and len(value) > longest:
        r.add(path, f"{len(value)} caractères (1 à {longest} attendus)")


def _check_plain(r: _Report, path: str, value, longest: int) -> None:
    """Texte simple des pages : longueur, puis ni « < » ni retour à la ligne (les problèmes de longueur s'ajoutent aux autres)."""
    _check_length(r, path, value, longest)
    if isinstance(value, str):
        if "<" in value:
            r.add(path, "contient « < »")
        if "\n" in value or "\r" in value:
            r.add(path, "contient un retour à la ligne")


def _check_url(r: _Report, path: str, value, longest: int | None = None) -> None:
    """Une adresse en https://, sans espace, de `longest` caractères au plus s'il est donné."""
    if not isinstance(value, str):
        r.add(path, "manquant" if value is None else "doit être un texte")
        return
    if not value.startswith("https://"):
        r.add(path, "doit commencer par https://")
    if re.search(r"\s", value):
        r.add(path, "ne doit pas contenir d'espace")
    if longest is not None and len(value) > longest:
        r.add(path, f"{len(value)} caractères ({longest} au plus)")


# --- Pages : blog-src/pages/<id>.json ---------------------------------------------------------------------------

def _check_identity(r: _Report, stem: str, data: dict, root: Path, fiches: set[str]) -> None:
    """kind, game, et l'espace de noms partagé avec les adresses du Blog (un identifiant égal à un jeu est réservé à sa fiche)."""
    kind = data.get("kind")
    if "kind" not in data:
        r.add("kind", "manquant")
    elif kind not in KINDS:
        r.add("kind", f"« {kind} » invalide ({', '.join(KINDS)} attendu)")
    valid_id = an.ID.fullmatch(stem) is not None
    if kind != "game" and valid_id and (stem in GAMES or not _missing_game_pages(root, stem)):
        r.add("", f"identifiant « {stem} » réservé à la fiche du jeu (kind game)")
    if kind == "game":
        if "game" not in data:
            r.add("game", "manquant (obligatoire pour une fiche de jeu)")
        elif data["game"] != stem:
            r.add("game", f"« {data['game']} » doit être égal à l'identifiant « {stem} »")
        if valid_id and (missing := _missing_game_pages(root, stem)):
            r.add("game", f"pages introuvables : {', '.join(missing)}")
    elif kind in KINDS and "game" in data:
        game = data["game"]
        if not isinstance(game, str) or not an.ID.fullmatch(game):
            r.add("game", f"« {game} » invalide")
        elif game not in fiches:
            r.add("game", f"« {game} » n'a pas de fiche de jeu (kind game)")


def _check_image(r: _Report, stem: str, data: dict, root: Path) -> None:
    """La couverture facultative : {"kind": "ia"} (illustration générée) ou {"kind": "officielle", "credit": …, "url": …} (image d'un
    éditeur, créditée et reliée à sa source) ; le fichier couvertures/<id>.webp doit exister à la racine du site."""
    if "image" not in data:
        return
    image = data["image"]
    if not isinstance(image, dict) or image.get("kind") not in IMAGE_KINDS:
        r.add("image", 'doit être {"kind": "ia"} ou {"kind": "officielle", "credit": …, "url": …}')
        return
    _check_unknown(r, "image", image, IMAGE_KEYS)
    if image["kind"] == "ia":
        for key in ("credit", "url"):
            if key in image:
                r.add(_at("image", key), "inutile pour une illustration générée par IA")
    else:
        _check_plain(r, _at("image", "credit"), image.get("credit"), 80)
        _check_url(r, _at("image", "url"), image.get("url"), 300)
    name = image.get("file", stem)
    if "file" in image and (not isinstance(name, str) or not an.ID.fullmatch(name)):
        r.add(_at("image", "file"), f"« {name} » invalide (identifiant d'une page, comme league-of-legends)")
    elif an.ID.fullmatch(name) and not (root / "couvertures" / f"{name}.webp").is_file():
        r.add("image", f"couvertures/{name}.webp introuvable")


def _check_dates(r: _Report, data: dict) -> None:
    days: dict[str, date] = {}
    for field in ("date", "updated"):
        if field not in data:
            r.add(field, "manquant")
            continue
        day = _parse_date(data[field])
        if day is None:
            r.add(field, f"« {data[field]} » n'est pas une date AAAA-MM-JJ")
        else:
            days[field] = day
    if len(days) == 2 and days["updated"] < days["date"]:
        r.add("updated", f"{data['updated']} est avant date {data['date']}")


def _check_sources(r: _Report, data: dict) -> set[str]:
    """Les sources de la page ; rend les identifiants déclarés (ceux que les sections peuvent citer)."""
    declared: set[str] = set()
    sources = data.get("sources")
    if "sources" not in data:
        r.add("sources", "manquant")
        return declared
    if not isinstance(sources, list):
        r.add("sources", "doit être une liste")
        return declared
    if not 1 <= len(sources) <= 8:
        r.add("sources", f"{len(sources)} source(s) (1 à 8 attendues)")
    urls: set[str] = set()
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        if not isinstance(source, dict):
            r.add(path, "doit être un objet avec « id », « title » et « url »")
            continue
        _check_unknown(r, path, source, SOURCE_KEYS)
        source_id = source.get("id")
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            r.add(_at(path, "id"), "manquant" if source_id is None else f"« {source_id} » invalide (s suivi de chiffres, comme s1)")
        elif source_id in declared:
            r.add(_at(path, "id"), f"« {source_id} » en double")
        else:
            declared.add(source_id)
        _check_plain(r, _at(path, "title"), source.get("title"), 120)
        url = source.get("url")
        _check_url(r, _at(path, "url"), url, 300)
        if isinstance(url, str):
            if url in urls:
                r.add(_at(path, "url"), f"« {url} » en double")
            urls.add(url)
    return declared


def _check_cite(r: _Report, path: str, cite, declared: set[str]) -> None:
    if not isinstance(cite, list):
        r.add(path, "manquant" if cite is None else "doit être une liste d'identifiants de sources")
        return
    if not 1 <= len(cite) <= 4:
        r.add(path, f"{len(cite)} source(s) citée(s) (1 à 4 attendues)")
    seen: set[str] = set()
    for index, ref in enumerate(cite):
        if not isinstance(ref, str) or ref not in declared:
            r.add(f"{path}[{index}]", f"« {ref} » n'est pas une source déclarée")
        elif ref in seen:
            r.add(f"{path}[{index}]", f"« {ref} » en double")
        else:
            seen.add(ref)


def _check_body(r: _Report, path: str, body) -> None:
    """Le texte d'une section dans une langue : un titre et de 1 à 4 paragraphes."""
    if not isinstance(body, dict):
        r.add(path, "doit être un objet avec « heading » et « text »")
        return
    _check_unknown(r, path, body, BODY_KEYS)
    _check_plain(r, _at(path, "heading"), body.get("heading"), 80)
    paragraphs, where = body.get("text"), _at(path, "text")
    if not isinstance(paragraphs, list):
        r.add(where, "manquant" if paragraphs is None else "doit être une liste de paragraphes")
        return
    if not 1 <= len(paragraphs) <= 4:
        r.add(where, f"{len(paragraphs)} paragraphe(s) (1 à 4 attendus)")
    for index, paragraph in enumerate(paragraphs):
        _check_plain(r, f"{where}[{index}]", paragraph, 600)


def _check_sections(r: _Report, data: dict, declared: set[str]) -> None:
    sections = data.get("sections")
    if "sections" not in data:
        r.add("sections", "manquant")
        return
    if not isinstance(sections, list):
        r.add("sections", "doit être une liste")
        return
    is_game = data.get("kind") == "game"
    lowest, highest = (3, 8) if is_game else (1, 12)
    if not lowest <= len(sections) <= highest:
        r.add("sections", f"{len(sections)} section(s) ({lowest} à {highest} attendues{' pour une fiche de jeu' if is_game else ''})")
    for index, section in enumerate(sections):
        path = f"sections[{index}]"
        if not isinstance(section, dict):
            r.add(path, "doit être un objet avec « cite » et les 5 langues")
            continue
        _check_unknown(r, path, section, SECTION_KEYS)
        _check_cite(r, _at(path, "cite"), section.get("cite"), declared)
        for lang in an.LANGS:
            if lang not in section:
                r.add(path, f"langue « {lang} » manquante")
            else:
                _check_body(r, _at(path, lang), section[lang])


def _check_header(r: _Report, path: str, header) -> None:
    """Titre et description de la page dans une langue."""
    if not isinstance(header, dict):
        r.add(path, "doit être un objet avec « title » et « description »")
        return
    _check_unknown(r, path, header, HEADER_KEYS)
    _check_plain(r, _at(path, "title"), header.get("title"), 70)
    _check_plain(r, _at(path, "description"), header.get("description"), 160)


def _check_page(r: _Report, stem: str, data, root: Path, fiches: set[str]) -> None:
    if not isinstance(data, dict):
        r.add("", "doit être un objet")
        return
    _check_unknown(r, "", data, PAGE_KEYS)
    _check_identity(r, stem, data, root, fiches)
    _check_image(r, stem, data, root)
    _check_dates(r, data)
    declared = _check_sources(r, data)
    _check_sections(r, data, declared)
    for lang in an.LANGS:
        if lang not in data:
            r.add("", f"langue « {lang} » manquante")
        else:
            _check_header(r, lang, data[lang])


def load_pages(root: Path) -> dict[str, dict]:
    """Lit et valide blog-src/pages/*.json (§5 de la spec) ; rend {identifiant: page}, l'identifiant (nom du fichier) ajouté à chaque page.

    Lève BlogError avec tous les problèmes à la fois ; un dossier absent donne {}.
    """
    folder = root / "blog-src" / "pages"
    if not folder.is_dir():
        return {}
    problems: list[str] = []
    loaded = []
    for path in sorted(folder.glob("*.json")):
        if path.is_file() and (data := _read_json(path, problems)) is not _UNREADABLE:
            loaded.append((path, data))
    fiches = {path.stem for path, data in loaded if isinstance(data, dict) and data.get("kind") == "game"}
    for path, data in loaded:
        report = _Report(path.name, problems)
        if not an.ID.fullmatch(path.stem):
            report.add("", "identifiant invalide (minuscules, chiffres et tirets, sans espace)")
        _check_page(report, path.stem, data, root, fiches)
    if problems:
        raise BlogError(problems)
    return {path.stem: {**data, "id": path.stem} for path, data in loaded}


def visible_pages(pages: dict[str, dict], today: date) -> list[dict]:
    """Pages à publier aujourd'hui (date ≤ aujourd'hui) : les fiches de jeu dans l'ordre de GAMES (les autres jeux ensuite,
    par identifiant), puis les guides et notes de version, du plus récent au plus ancien, à date égale par identifiant."""
    def order(page: dict):
        if page["kind"] == "game":
            return 0, GAMES.index(page["id"]) if page["id"] in GAMES else len(GAMES), page["id"]
        return 1, -date.fromisoformat(page["date"]).toordinal(), page["id"]

    return sorted((p for p in pages.values() if date.fromisoformat(p["date"]) <= today), key=order)


# --- Chaînes YouTube : blog-src/channels.json -------------------------------------------------------------------

def _include_problem(value) -> str | None:
    """Ce qui ne va pas dans le champ facultatif `include` d'une chaîne (expression régulière, insensible à la casse) ; None s'il est valide."""
    if not isinstance(value, str):
        return "doit être un texte"
    if not 1 <= len(value) <= INCLUDE_LENGTH:
        return f"{len(value)} caractères (1 à {INCLUDE_LENGTH} attendus)"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # un avertissement de `re` (ex. « Possible nested set ») : le sens de l'expression est douteux, on la refuse
            re.compile(value, re.I)  # topplays.select_videos la compile de la même façon
    except (re.error, OverflowError, Warning) as error:  # OverflowError : « a{99999999999} »
        return f"expression invalide : {error}"
    return None


def _check_channels(r: _Report, root: Path, data) -> None:
    if not isinstance(data, dict):
        r.add("", "doit être un objet {jeu: [chaînes]}")
        return
    for game, channels in data.items():
        _check_game_name(r, game, game, root)
        if not isinstance(channels, list):
            r.add(game, "doit être une liste de chaînes")
            continue
        seen: set[str] = set()
        for index, channel in enumerate(channels):
            path = f"{game}[{index}]"
            if not isinstance(channel, dict):
                r.add(path, "doit être un objet avec « id », « name » et « proof »")
                continue
            _check_unknown(r, path, channel, CHANNEL_KEYS)
            channel_id = channel.get("id")
            if not isinstance(channel_id, str) or not CHANNEL_ID.fullmatch(channel_id):
                r.add(_at(path, "id"), "manquant" if channel_id is None else f"« {channel_id} » invalide (UC suivi de 22 caractères)")
            elif channel_id in seen:
                r.add(_at(path, "id"), f"« {channel_id} » en double")
            else:
                seen.add(channel_id)
            _check_length(r, _at(path, "name"), channel.get("name"), 60)
            _check_url(r, _at(path, "proof"), channel.get("proof"))
            if "include" in channel and (problem := _include_problem(channel["include"])):
                r.add(_at(path, "include"), f"{problem} (chaîne « {channel.get('name') or channel_id or index} »)")  # le jeu est nommé par le chemin


def load_channels(root: Path) -> dict[str, list[dict]]:
    """Lit et valide blog-src/channels.json ; un fichier absent donne {}. Lève BlogError avec tous les problèmes à la fois."""
    path = root / "blog-src" / "channels.json"
    if not path.is_file():
        return {}
    problems: list[str] = []
    data = _read_json(path, problems)
    if data is not _UNREADABLE:
        _check_channels(_Report(path.name, problems), root, data)
    if problems:
        raise BlogError(problems)
    return data


# --- Sélection du matin : blog-src/topplays.json ----------------------------------------------------------------

def _check_topplays(r: _Report, data) -> None:
    if not isinstance(data, dict):
        r.add("", "doit être un objet {jeu: {fetched, videos}}")
        return
    for game, entry in data.items():
        if not an.ID.fullmatch(game):
            r.add(game, "identifiant de jeu invalide")
        if not isinstance(entry, dict):
            r.add(game, "doit être un objet avec « fetched » et « videos »")
            continue
        _check_unknown(r, game, entry, TOPPLAYS_KEYS)
        if "fetched" not in entry:
            r.add(_at(game, "fetched"), "manquant")
        elif _parse_date(entry["fetched"]) is None:
            r.add(_at(game, "fetched"), f"« {entry['fetched']} » n'est pas une date AAAA-MM-JJ")
        videos, where = entry.get("videos"), _at(game, "videos")
        if not isinstance(videos, list):
            r.add(where, "manquant" if videos is None else "doit être une liste")
            continue
        for index, video in enumerate(videos):
            path = f"{where}[{index}]"
            if not isinstance(video, dict):
                r.add(path, "doit être un objet avec « id », « title », « channel » et « published »")
                continue
            _check_unknown(r, path, video, VIDEO_KEYS)
            video_id = video.get("id")
            if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
                r.add(_at(path, "id"), "manquant" if video_id is None else f"« {video_id} » invalide (11 caractères : lettres, chiffres, _ et -)")
            _check_length(r, _at(path, "title"), video.get("title"))
            _check_length(r, _at(path, "channel"), video.get("channel"))
            if "published" not in video:
                r.add(_at(path, "published"), "manquant")
            elif _parse_date(video["published"]) is None:
                r.add(_at(path, "published"), f"« {video['published']} » n'est pas une date AAAA-MM-JJ")


def load_topplays(root: Path) -> dict[str, dict]:
    """Lit et valide blog-src/topplays.json ; un fichier absent donne {}. Lève BlogError avec tous les problèmes à la fois."""
    path = root / "blog-src" / "topplays.json"
    if not path.is_file():
        return {}
    problems: list[str] = []
    data = _read_json(path, problems)
    if data is not _UNREADABLE:
        _check_topplays(_Report(path.name, problems), data)
    if problems:
        raise BlogError(problems)
    return data


def visible_topplays(topplays: dict[str, dict], today: date) -> dict[str, list[dict]]:
    """Vidéos à afficher : celles des jeux dont la sélection date d'au plus 14 jours et compte au moins une vidéo."""
    return {game: entry["videos"] for game, entry in topplays.items()
            if entry["videos"] and today - date.fromisoformat(entry["fetched"]) <= TOPPLAYS_MAX_AGE}


# --- Libellés ---------------------------------------------------------------------------------------------------

# Textes fixes des pages (tableaux « Les textes fixes de la page » §6 et libellés du lien de guide §8 de la spec).
# Les noms de jeux ne se traduisent pas : {game} est remplacé par le nom lu dans la page du jeu, {date} par une date en toutes lettres.
# Ces textes sont insérés tels quels dans le HTML : aucun ne contient « < », « > », « & » ni « " ».
LABELS = {
    "en": dict(kicker="Blog", title="The games behind the matches", head="Esports guides: every game and its pro scene",
               lead="What each game is, how its pro scene works and how to follow it, with the sources we used.",
               grid="Games", latest="Latest articles", about="Articles about {game}", sources="Sources", checked="Checked on {date}",
               ai="Written with AI assistance and checked against the sources cited.",
               follow="Follow {game} with eSportly", see_game="See what eSportly does for {game}", others="Other games",
               topplays="Top plays right now",
               topnote="Videos from the game's official YouTube channels, ranked by views this week. A video loads from YouTube only when you click it.",
               play="Play: {title}",
               guide="Guide: {game}, the game and its pro scene →",
               toc="Contents", ai_image="Illustration generated by AI", credit="Image: {credit}", source_link="source"),
    "fr": dict(kicker="Blog", title="Les jeux derrière les matchs", head="Guides esport : chaque jeu et sa scène pro",
               lead="Ce qu'est chaque jeu, comment fonctionne sa scène pro et comment la suivre, avec les sources utilisées.",
               grid="Jeux", latest="Derniers articles", about="Articles sur {game}", sources="Sources", checked="Vérifié le {date}",
               ai="Rédigé avec l'aide de l'IA et vérifié par rapport aux sources citées.",
               follow="Suivre {game} avec eSportly", see_game="Voir ce que fait eSportly pour {game}", others="Autres jeux",
               topplays="Top plays du moment",
               topnote="Vidéos des chaînes YouTube officielles du jeu, classées par vues cette semaine. Une vidéo ne se charge depuis YouTube que lorsque tu cliques dessus.",
               play="Lire : {title}",
               guide="Guide : {game}, le jeu et sa scène pro →",
               toc="Sommaire", ai_image="Illustration générée par IA", credit="Image : {credit}", source_link="source"),
    "es": dict(kicker="Blog", title="Los juegos detrás de los partidos", head="Guías de esports: cada juego y su escena profesional",
               lead="Qué es cada juego, cómo funciona su escena profesional y cómo seguirla, con las fuentes que hemos usado.",
               grid="Juegos", latest="Últimos artículos", about="Artículos sobre {game}", sources="Fuentes", checked="Comprobado el {date}",
               ai="Redactado con ayuda de IA y comprobado con las fuentes citadas.",
               follow="Sigue {game} con eSportly", see_game="Descubre qué hace eSportly por {game}", others="Otros juegos",
               topplays="Top plays del momento",
               topnote="Vídeos de los canales oficiales de YouTube del juego, por vistas esta semana. Un vídeo solo se carga desde YouTube cuando haces clic en él.",
               play="Reproducir: {title}",
               guide="Guía: {game}, el juego y su escena profesional →",
               toc="Índice", ai_image="Ilustración generada por IA", credit="Imagen: {credit}", source_link="fuente"),
    "de": dict(kicker="Blog", title="Die Spiele hinter den Matches", head="E-Sport-Guides: jedes Spiel und seine Profiszene",
               lead="Was jedes Spiel ist, wie die Profiszene funktioniert und wie du sie verfolgst – mit den verwendeten Quellen.",
               grid="Spiele", latest="Neueste Artikel", about="Artikel zu {game}", sources="Quellen", checked="Geprüft am {date}",
               ai="Mit KI-Unterstützung verfasst und anhand der genannten Quellen geprüft.",
               follow="{game} mit eSportly verfolgen", see_game="Das kann eSportly für {game}", others="Weitere Spiele",
               topplays="Top Plays im Moment",
               topnote="Videos der offiziellen YouTube-Kanäle des Spiels, nach Aufrufen dieser Woche sortiert. Ein Video wird erst nach einem Klick von YouTube geladen.",
               play="Abspielen: {title}",
               guide="Ratgeber: {game} und seine Profiszene →",
               toc="Inhalt", ai_image="Mit KI erzeugte Illustration", credit="Bild: {credit}", source_link="Quelle"),
    "pt-BR": dict(kicker="Blog", title="Os jogos por trás das partidas", head="Guias de esports: cada jogo e sua cena profissional",
                  lead="O que é cada jogo, como funciona a cena profissional e como acompanhá-la, com as fontes que usamos.",
                  grid="Jogos", latest="Últimos artigos", about="Artigos sobre {game}", sources="Fontes", checked="Verificado em {date}",
                  ai="Escrito com ajuda de IA e conferido com as fontes citadas.",
                  follow="Acompanhe {game} com o eSportly", see_game="Veja o que o eSportly faz por {game}", others="Outros jogos",
                  topplays="Top plays do momento",
                  topnote="Vídeos dos canais oficiais do jogo no YouTube, ordenados por visualizações nesta semana. Um vídeo só é carregado do YouTube quando você clica nele.",
                  play="Reproduzir: {title}",
                  guide="Guia: {game}, o jogo e sua cena profissional →",
                  toc="Sumário", ai_image="Ilustração gerada por IA", credit="Imagem: {credit}", source_link="fonte"),
}
COLON = {"fr": " :"}  # « Sources : [1] » : la typographie française met une espace avant les deux-points

# Jeux dont le logo est une image blanche : les pages de jeux la dessinent avec un masque de la couleur du texte (« glogo mono »),
# alors que le Blog l'affiche en <img>, invisible sur le thème clair sans la règle d'inversion ci-dessous.
MONO_LOGOS = ("call-of-duty", "counter-strike-2", "ea-sports-fc", "honor-of-kings", "overwatch-2", "rocket-league", "starcraft-brood-war")


def _mono_logos(prefix: str) -> str:
    return ",".join(f'{prefix} img[src$="/{game}.png"]' for game in MONO_LOGOS)


# Style des pages du Blog, avec les variables de thème du site (une règle par ligne). Les classes crumbs, hero, big, kicker,
# lead, glogo, others et cta ne sont pas ici : les pages modèles les définissent déjà. Aucune ressource externe.
BLOG_STYLE = "\n".join([
    ".hero .lead:last-child{margin-bottom:0}",
    ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}",
    ".card{display:grid;gap:8px;align-content:start;padding:18px;border-radius:20px;border:1px solid var(--border);background:var(--surface);color:var(--text);text-decoration:none}",
    ".card:hover{border-color:var(--g,var(--or))}",
    ".card img{display:block;height:48px;width:auto;max-width:100%}",
    ".card b{font:700 24px/1.2 var(--display)}",
    ".card small{font-size:15px;color:var(--soft)}",
    ".posts{list-style:none;margin:0;padding:0;display:grid;gap:10px}",
    ".posts a{display:grid;gap:3px;padding:14px 18px;border-radius:18px;border:1px solid var(--border);background:var(--surface);color:var(--text);text-decoration:none}",
    ".posts time{font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--soft)}",
    ".posts b{font:700 21px/1.2 var(--display)}",
    ".posts small{font-size:15px;color:var(--soft)}",
    ".feed{grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:18px}",
    ".feed a{padding:0;gap:0;overflow:hidden;height:100%;box-sizing:border-box;align-content:start;border-radius:22px}",
    ".feed a:hover{border-color:var(--or)}",
    ".feed img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:cover}",
    ".feed .txt{display:grid;gap:8px;padding:16px 20px 20px}",
    ".feed b{font:700 26px/1.15 var(--display)}",
    ".feed small{font-size:16px}",
    "@media (min-width:800px){.feed li:first-child{grid-column:1/-1}.feed li:first-child a:has(img){grid-template-columns:3fr 2fr}.feed li:first-child img{height:100%;min-height:300px;aspect-ratio:auto}.feed li:first-child .txt{align-content:center;padding:28px}.feed li:first-child b{font-size:38px}}",
    ".cards.mini{grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}",
    ".cards.mini .card{grid-template-columns:34px 1fr;align-items:center;gap:11px;padding:9px 12px;border-radius:16px}",
    ".cards.mini .card img{width:34px;height:34px;object-fit:contain}",
    ".cards.mini .card b{font-size:17px}",
    ".sec p{margin:0 0 12px;color:var(--soft)}",
    ".sec .cite{margin:0 0 4px;font-size:14px}",
    ".cite a{font-weight:700;text-decoration:none}",
    ".topplays{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:16px}",
    ".play{display:grid;gap:10px;align-content:start}",
    ".video{position:relative;display:grid;place-items:center;aspect-ratio:16/9;border-radius:14px;overflow:hidden;background:var(--surface);border:1px solid var(--border);text-decoration:none}",
    ".video .btn{display:grid;place-items:center;width:64px;height:64px;border-radius:50%;background:var(--or);color:var(--on-or);font-size:24px;line-height:1;padding-left:4px;box-sizing:border-box}",
    ".video:hover .btn{transform:scale(1.08)}",
    ".video:focus-visible{outline:2px solid var(--or);outline-offset:3px}",
    ".video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}",
    ".legend{display:grid;gap:2px;margin:0}",
    ".legend b{font-size:17px;line-height:1.3;color:var(--text)}",
    ".legend small{font-size:14px;color:var(--soft)}",
    ".topnote{margin:10px 0 0;font-size:14px;color:var(--muted)}",
    ".sources{margin:0;padding-left:24px;display:grid;gap:8px;color:var(--soft)}",
    ".sources small{margin-left:8px;font-size:13px}",
    ".sources li:target{outline:2px solid var(--or);outline-offset:4px;border-radius:6px}",
    ".checked{margin:24px 0 4px;font-size:14px;font-weight:600;color:var(--soft)}",
    ".ai{margin:0;font-size:14px;color:var(--soft)}",
    ".follow{margin:32px 0 0;padding:22px;border-radius:24px;border:1px solid var(--border);border-left:5px solid var(--g,var(--or));background:var(--surface)}",
    ".follow h2{margin:0 0 10px;font-size:28px}",
    ".follow p{margin:0 0 16px;color:var(--soft)}",
    ".guide{margin:18px 0}",
    ".guide a{font-weight:700}",
    ".cover{margin:0 0 8px}",
    ".cover img{display:block;width:100%;height:auto;border-radius:22px;border:1px solid var(--border)}",
    ".cover figcaption{margin:8px 4px 0;font-size:13px;color:var(--muted)}",
    ".art{display:grid;gap:24px;align-items:start}",
    ".toc{order:-1;padding:14px 18px;border-radius:18px;border:1px solid var(--border);background:var(--surface)}",
    ".toc p{margin:0 0 8px;font:700 15px var(--display);letter-spacing:.06em;text-transform:uppercase;color:var(--soft)}",
    ".toc ol{margin:0;padding:0 0 0 20px;display:grid;gap:6px;font-size:15px}",
    ".toc a{color:var(--soft);text-decoration:none}",
    ".toc a:hover{color:var(--text);text-decoration:underline}",
    "h2[id]{scroll-margin-top:88px}",
    "@media (min-width:1100px){main.wrap:has(.art){max-width:1240px}.art{grid-template-columns:minmax(0,1fr) 260px;gap:40px}.toc{order:0;position:sticky;top:88px}.cover img{aspect-ratio:21/9;object-fit:cover}}",
    _mono_logos(':root[data-theme="light"]') + "{filter:invert(1)}",
    "@media (prefers-color-scheme:light){" + _mono_logos(":root:not([data-theme])") + "{filter:invert(1)}}",
    *MENU_STYLE,
    *FOOTER_STYLE,
    *FILTER_STYLE,
])


# --- Fragments HTML ---------------------------------------------------------------------------------------------
# Chaque fragment tient sur une seule ligne, et tout texte venu des données est échappé (texte comme attribut).

def _esc(value) -> str:
    """Une donnée prête à entrer dans le HTML : échappée, et sur une ligne (les sauts de ligne deviennent des espaces)."""
    return html.escape(" ".join(str(value).splitlines()))


DATE_FORMS = {"es": "{d} de {m} de {y}", "de": "{d}. {m} {y}", "pt-BR": "{d} de {m} de {y}"}  # sinon « 28 octobre 2026 »


def _day(day: str, lang: str) -> str:
    """« 28 octobre 2026 », « 28 October 2026 », « 28 de octubre de 2026 », « 28. Oktober 2026 », « 28 de outubro de 2026 »."""
    value = date.fromisoformat(day)
    return DATE_FORMS.get(lang, "{d} {m} {y}").format(d=value.day, m=an.MONTHS[lang][value.month - 1], y=value.year)


def _domain(url: str) -> str:
    """Le domaine affiché sous une source (sans « www. », sans port ni chemin) ; vide si l'adresse n'en a pas de lisible."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:  # par exemple « https://[::1 »
        return ""
    return host.removeprefix("www.")


def render_sections(page: dict, lang: str) -> str:
    """Les sections de la page dans la langue : intertitre, paragraphes, puis « Sources : [1] [2] » (liens vers #src1…).

    Le numéro d'une source est sa position dans `sources`, qui est aussi l'ordre de la liste affichée par render_sources.
    """
    numbers = {source["id"]: number for number, source in enumerate(page["sources"], start=1)}
    label = LABELS[lang]["sources"] + COLON.get(lang, ":")
    parts = []
    for number, section in enumerate(page["sections"], start=1):
        body = section[lang]
        paragraphs = "".join(f"<p>{_esc(text)}</p>" for text in body["text"])
        cited = " ".join(f'<a href="#src{numbers[ref]}">[{numbers[ref]}]</a>' for ref in section["cite"])
        parts.append(f'<section class="sec"><h2 id="s{number}">{_esc(body["heading"])}</h2>{paragraphs}<p class="cite">{label} {cited}</p></section>')
    return "".join(parts)


def render_toc(page: dict, lang: str, videos: bool) -> str:
    """Le sommaire de la page (nav.toc) : un lien par section (#s1, #s2… : les intertitres de render_sections, dans l'ordre),
    puis « Top plays » (#plays) quand `videos`, et « Sources » (#sources)."""
    labels = LABELS[lang]
    items = [(f"#s{number}", section[lang]["heading"]) for number, section in enumerate(page["sections"], start=1)]
    if videos:
        items.append(("#plays", labels["topplays"]))
    items.append(("#sources", labels["sources"]))
    links = "".join(f'<li><a href="{href}">{_esc(text)}</a></li>' for href, text in items)
    return f'<nav class="toc" aria-label="{_esc(labels["toc"])}"><p>{_esc(labels["toc"])}</p><ol>{links}</ol></nav>'


def render_cover(page: dict, lang: str, prefix: str | None = None) -> str:
    """La couverture d'une page qui a une `image` : <figure class="cover"> avec couvertures/<id>.webp (1600×900, alt = le titre) et sa
    légende, « Illustration générée par IA » ou « Image : <crédit> · source » (lien vers la page de l'éditeur) ; vide sans image."""
    image = page.get("image")
    if not image:
        return ""
    if prefix is None:  # vu d'une page du Blog de la langue (BLOG_DIRS[lang]/<id>.html)
        prefix = _page_prefix(lang)
    labels = LABELS[lang]
    if image["kind"] == "ia":
        caption = _esc(labels["ai_image"])
    else:
        caption = (f'{_esc(labels["credit"].format(credit=image["credit"]))} · '
                   f'<a href="{_esc(image["url"])}" rel="noopener">{_esc(labels["source_link"])}</a>')
    return (f'<figure class="cover"><img src="{prefix}couvertures/{_esc(cover_file(page))}.webp" alt="{_esc(page[lang]["title"])}" '
            f'width="1600" height="900" decoding="async"><figcaption>{caption}</figcaption></figure>')


def render_sources(page: dict, lang: str) -> str:
    """La liste numérotée des sources : titre (lien `rel="noopener"`) et domaine ; chaque ligne porte l'ancre src1, src2…"""
    items = []
    for number, source in enumerate(page["sources"], start=1):
        domain = _domain(source["url"])
        shown = f"<small>{_esc(domain)}</small>" if domain else ""
        items.append(f'<li id="src{number}"><a href="{_esc(source["url"])}" rel="noopener">{_esc(source["title"])}</a>{shown}</li>')
    return f'<h2 id="sources">{LABELS[lang]["sources"]}</h2><ol class="sources">{"".join(items)}</ol>'


def render_videos(videos: list[dict], lang: str) -> str:
    """Le bloc des top plays : une carte de lecture au clic par vidéo (spec §14), dans un cadre 16/9, avec sa légende (titre, chaîne,
    date en texte), puis la note ; vide sans vidéo.

    La carte n'a aucune ressource de tiers (ni vignette, ni lecteur) : c'est un lien vers la vidéo sur YouTube (le secours sans
    JavaScript), avec son identifiant (data-id), un libellé accessible (« Lire : <titre> ») et un bouton dessiné en CSS. Au clic,
    PLAYER_JS la remplace par le lecteur youtube-nocookie.com ; render_guide_page ajoute ce script et élargit la CSP de la page.
    """
    if not videos:
        return ""
    labels = LABELS[lang]
    items = "".join(
        f'<li class="play"><a class="video" href="{WATCH_URL}{_esc(quote(video["id"], safe=""))}" data-id="{_esc(video["id"])}" '
        f'aria-label="{_esc(labels["play"].format(title=video["title"]))}"><span class="btn" aria-hidden="true">▶</span></a>'
        f'<p class="legend"><b>{_esc(video["title"])}</b><small>{_esc(video["channel"])} · '
        f'<time datetime="{_esc(video["published"])}">{_day(video["published"], lang)}</time></small></p></li>' for video in videos)
    return f'<h2 id="plays">{labels["topplays"]}</h2><ul class="topplays">{items}</ul><p class="topnote">{labels["topnote"]}</p>'


def _jsonld(data: dict) -> str:
    """Une balise de données structurées ; « </ » et « <!-- » y sont neutralisés (le JSON reste valide, une fois extrait)."""
    text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return f'<script type="application/ld+json">{text}</script>'


def cover_file(page: dict) -> str:
    """Le nom (sans .webp) de la couverture d'une page qui a une `image` : `image.file` quand elle réutilise celle d'une autre page, sinon son identifiant."""
    return page["image"].get("file") or page["id"]


def cover_url(page: dict) -> str:
    """L'image de partage de la page : sa couverture quand elle en a une, sinon l'og:image du modèle (la page de son jeu)."""
    if page.get("image"):
        return f"{SITE}couvertures/{cover_file(page)}.webp"
    return f"{SITE}partage/jeux/{page.get('game') or TEMPLATE_GAME}.jpg"


def render_jsonld(page: dict, lang: str, url: str, crumbs: list[tuple[str, str]]) -> str:
    """Données structurées de la page : `Article` (avec les adresses des sources en `citation`) et `BreadcrumbList` des `crumbs` (nom, adresse)."""
    article = {
        "@context": "https://schema.org", "@type": "Article", "headline": page[lang]["title"], "description": page[lang]["description"],
        "datePublished": page["date"], "dateModified": page["updated"], "inLanguage": lang, "mainEntityOfPage": url,
        "image": cover_url(page),
        "author": {"@type": "Organization", "name": "eSportly", "url": SITE},
        "publisher": {"@type": "Organization", "name": "ProtoJo Digital", "url": SITE, "logo": f"{SITE}icone-512.png"},
        "citation": [source["url"] for source in page["sources"]]}
    trail = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": position, "name": name, "item": link}
                            for position, (name, link) in enumerate(crumbs, start=1)]}
    return _jsonld(article) + _jsonld(trail)


def _data_game(entry: dict) -> str:
    """L'attribut data-game d'une page liée à un jeu (le filtre de l'accueil du Blog), rien pour un guide général."""
    return f' data-game="{_esc(entry["game"])}"' if entry.get("game") else ""


def _page_prefix(lang: str) -> str:
    """Ce qui précède un chemin depuis la racine, vu d'une page du Blog de la langue (« ../ » en anglais, « ../../ » sinon)."""
    return site_chrome.prefix_for(f"{BLOG_DIRS[lang]}/x.html")


def _posts(pages: list[dict], lang: str, folder: str) -> str:
    """Liste de liens vers des pages du Blog (date, titre, description). `folder` précède <id>.html : « » depuis une page du Blog, « blog/ » depuis l'accueil."""
    items = "".join(
        f'<li{_data_game(entry)}><a href="{folder}{_esc(entry["id"])}.html"><time datetime="{_esc(entry["date"])}">{_day(entry["date"], lang)}</time>'
        f'<b>{_esc(entry[lang]["title"])}</b><small>{_esc(entry[lang]["description"])}</small></a></li>' for entry in pages)
    return f'<ul class="posts">{items}</ul>'


def _game_key(entry: dict) -> str:
    """Le jeu d'une page : `game` quand elle en a un, sinon son identifiant (une fiche de jeu a pour identifiant celui du jeu)."""
    return entry.get("game") or entry["id"]


def render_guide_main(page: dict, lang: str, names: dict[str, str], home: tuple[str, str], videos: list[dict],
                      articles: list[dict], others: list[dict]) -> str:
    """Le contenu de <main> d'une page du Blog (dans un sous-dossier : liens en « ../ »), dans l'ordre de la spec §6 :
    fil d'Ariane, logo et titre, description, sections, top plays, sources, « Vérifié le », ligne de transparence, encadré « Suivre »,
    articles du jeu, autres jeux.

    `names` : identifiant de jeu → nom (à défaut, l'identifiant) ; `home` : (adresse, libellé) du lien d'accueil du site, lu dans le modèle ;
    `videos` : top plays du jeu (peut être vide ; _guide_page n'en donne qu'à la fiche du jeu) ; `articles` : pages non-jeu visibles sur ce jeu ; `others` : les autres fiches visibles.
    Une fiche de jeu finit son fil d'Ariane sur le nom du jeu ; un guide ou une note de version, sur son propre titre. Sans `game`,
    la page n'a ni logo ni encadré « Suivre ».
    """
    labels, prefix = LABELS[lang], _page_prefix(lang)
    header = page[lang]
    game = page.get("game")
    name = _esc(names.get(game, game)) if game else ""
    last = name if page["kind"] == "game" else _esc(header["title"])
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{_esc(home[0])}">{_esc(home[1])}</a> › '
              f'<a href="{prefix}{HUBS[lang]}">{labels["kicker"]}</a> › <span>{last}</span></nav>')
    logo = f'<img class="glogo" src="{prefix}logos-jeux/{_esc(game)}.png" alt="" width="58" height="48">' if game else ""
    hero = (f'<section class="hero">{logo}<div class="kicker">{labels["kicker"]}</div><h1>{_esc(header["title"])}</h1>'
            f'<p class="lead">{_esc(header["description"])}</p></section>')
    footer = f'<p class="checked">{labels["checked"].format(date=_day(page["updated"], lang))}</p><p class="ai">{labels["ai"]}</p>'
    follow = about = ""
    if game:
        follow = (f'<section class="follow"><h2>{labels["follow"].format(game=name)}</h2>'
                  f'<p><a href="{prefix}{GAME_DIRS[lang]}/{_esc(game)}.html">{labels["see_game"].format(game=name)}</a></p>'
                  f'<a class="cta" href="{VISIT}?p=/{BLOG_DIRS[lang]}/{_esc(page["id"])}&amp;go=testflight">{an.LABELS[lang]["cta"]}</a></section>')
        if articles:
            about = f'<h2>{labels["about"].format(game=name)}</h2>{_posts(articles, lang, "")}'
    more = ""
    if others:
        links = "".join(f'<a href="{_esc(entry["id"])}.html">{_esc(names.get(_game_key(entry), _game_key(entry)))}</a>' for entry in others)
        more = f'<h2>{labels["others"]}</h2><nav class="others" aria-label="{labels["others"]}">{links}</nav>'
    body = render_sections(page, lang) + render_videos(videos, lang) + render_sources(page, lang) + footer
    article = f'<div class="art"><article>{body}</article>{render_toc(page, lang, bool(videos))}</div>'
    return crumbs + hero + render_cover(page, lang) + article + follow + about + more


def _story(entry: dict, lang: str, folder: str, prefix: str, first: bool) -> str:
    """Une carte de l'accueil du Blog : couverture (16/9), date, gros titre, description ; toute la carte est le lien de l'article.
    La première image se charge tout de suite, les autres quand on s'en approche ; une page sans `image` n'a que le texte."""
    image = ""
    if entry.get("image"):
        loading = ' fetchpriority="high"' if first else ' loading="lazy"'
        image = f'<img src="{prefix}couvertures/{_esc(cover_file(entry))}.webp" alt="" width="1600" height="900" decoding="async"{loading}>'
    return (f'<li{_data_game(entry)}><a href="{folder}/{_esc(entry["id"])}.html">{image}<span class="txt">'
            f'<time datetime="{_esc(entry["date"])}">{_day(entry["date"], lang)}</time><b>{_esc(entry[lang]["title"])}</b>'
            f'<small>{_esc(entry[lang]["description"])}</small></span></a></li>')


def render_hub_main(lang: str, pages: list[dict], names: dict[str, str]) -> str:
    """Le contenu de <main> de l'accueil du Blog (un fichier à la racine du site pour l'anglais, dans un dossier de langue sinon : liens relatifs à la racine par `prefix`) :
    l'accroche, « Derniers articles » (12 au plus, du plus récent au plus ancien, une carte avec couverture et gros titre par article ;
    la première est mise en avant), puis les fiches de jeux dans l'ordre donné (jamais retriées), réduites au logo et au nom."""
    labels, prefix = LABELS[lang], site_chrome.prefix_for(HUBS[lang])
    folder = prefix + BLOG_DIRS[lang]
    hero = (f'<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{labels["kicker"]}</div>'
            f'<h1>{labels["title"]}</h1><p class="lead">{labels["lead"]}</p></section>')
    newest = sorted((entry for entry in pages if entry["kind"] != "game"),
                    key=lambda entry: (-date.fromisoformat(entry["date"]).toordinal(), entry["id"]))[:12]
    stories = "".join(_story(entry, lang, folder, prefix, first=number == 0) for number, entry in enumerate(newest))
    latest = f'<h2>{labels["latest"]}</h2><ul class="posts feed">{stories}</ul>' if newest else ""
    cards = "".join(
        f'<a class="card" data-game="{_esc(_game_key(entry))}" href="{folder}/{_esc(entry["id"])}.html"><img src="{prefix}logos-jeux/{_esc(_game_key(entry))}.png" alt="">'
        f'<b>{_esc(names.get(_game_key(entry), _game_key(entry)))}</b></a>'
        for entry in pages if entry["kind"] == "game")
    games = f'<h2>{labels["grid"]}</h2><div class="cards mini">{cards}</div>' if cards else ""
    return hero + latest + games


def render_guide_link(page: dict | None, lang: str, name: str) -> str:
    """Le lien « Guide : <jeu>, … → » inséré dans une page de jeu existante (qui est dans un sous-dossier : « ../ ») ; vide sans fiche visible."""
    if page is None:
        return ""
    label = LABELS[lang]["guide"].format(game=_esc(name))
    prefix = site_chrome.prefix_for(f"{GAME_DIRS[lang]}/x.html")  # vu de la page de jeu
    return f'<p class="guide"><a href="{prefix}{BLOG_DIRS[lang]}/{_esc(page["id"])}.html">{label}</a></p>'


# --- Pages : assemblage dans les modèles du site ----------------------------------------------------------------

SITE = "https://esportly.eu/"
TEMPLATE_GAME = "league-of-legends"  # sa page sert de modèle aux pages sans jeu (guides et notes de version généraux)
GUIDE_MARKERS = ("<!-- blog-guide -->", "<!-- /blog-guide -->")  # lien de guide des pages de jeux existantes (§8 de la spec)
SITEMAP_MARKERS = ("<!-- blog -->", "<!-- /blog -->")  # entrées du Blog dans sitemap.xml (§6)
CRUMBS = re.compile(r'<nav class="crumbs"[^>]*>(.*?)</nav>', re.S)
VISIT_PATH = re.compile(r"(visite\?p=/)[A-Za-z0-9/_-]+")
JSON_LD_LINE = re.compile(r'<script type="application/ld\+json">.*?</script>(\r?\n)?', re.S)
MAIN = re.compile(r"<main\b[^>]*>.*?</main>", re.S)
EMBED_URL = "https://www.youtube-nocookie.com/embed/"  # domaine du lecteur chargé au clic (spec §7 et §14)
WATCH_URL = "https://www.youtube.com/watch?v="  # lien de secours d'une carte de lecture (sans JavaScript, il ouvre la vidéo sur YouTube)
EMBED_CSP = "frame-src https://www.youtube-nocookie.com"  # directive que la CSP d'une page à top plays doit contenir (spec §6)
# Lecture au clic (spec §14) : un seul écouteur, sur le document. Un clic simple sur une carte dont le data-id est un identifiant
# YouTube valide remplace la carte par un cadre « video » contenant le lecteur, qui reçoit le focus ; tout autre clic (Ctrl, Maj,
# bouton du milieu, data-id invalide) laisse le lien de secours suivre son cours. Rien n'est chargé avant le clic. Le texte est
# haché tel quel pour la CSP : toute modification change PLAYER_HASH, et la génération met les pages à jour.
PLAYER_JS = (
    'document.addEventListener("click",function(e){'
    'var a=e.target&&e.target.closest?e.target.closest("a.video"):null;'
    'if(!a||e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;'
    'var id=a.getAttribute("data-id");if(!/^[A-Za-z0-9_-]{11}$/.test(id||""))return;'
    'e.preventDefault();'
    'var d=document.createElement("div"),f=document.createElement("iframe"),t=a.parentNode.querySelector(".legend b");'
    'd.setAttribute("class","video");'
    f'f.setAttribute("src","{EMBED_URL}"+id+"?autoplay=1");'
    'f.setAttribute("title",t?t.textContent:"");'
    'f.setAttribute("allowfullscreen","");'
    'f.setAttribute("referrerpolicy","strict-origin-when-cross-origin");'
    'f.setAttribute("allow","autoplay; encrypted-media; picture-in-picture");'
    'd.appendChild(f);a.replaceWith(d);f.focus()})'
)
PLAYER_HASH = base64.b64encode(hashlib.sha256(PLAYER_JS.encode("utf-8")).digest()).decode()  # pour script-src
PLAYER_TAG = f"<script>{PLAYER_JS}</script>"
OBJECT_SRC = re.compile(r"(?<![\w-])object-src 'none'")


def read_home(template: str) -> tuple[str, str]:
    """Premier lien du fil d'Ariane d'une page de jeu : (adresse, libellé) du lien d'accueil du site.

    Le texte est décodé (« &amp; » devient « & ») : les fragments l'échappent de nouveau. Lève BlogError sans ce lien.
    """
    crumbs = CRUMBS.search(template)
    link = re.search(r'<a href="([^"]*)"[^>]*>(.*?)</a>', crumbs.group(1), re.S) if crumbs else None
    if link is None:
        raise BlogError(["fil d'Ariane (nav.crumbs) sans lien d'accueil"])
    return html.unescape(link.group(1)), html.unescape(link.group(2))


def read_names(root: Path) -> dict[str, dict[str, str]]:
    """{langue: {jeu: nom}} : le nom affiché de chaque jeu, lu (et décodé) dans le <span> du fil d'Ariane de sa page.

    Un jeu sans page dans une langue, ou dont la page n'a pas de fil d'Ariane, en est absent : les fragments affichent son identifiant.
    """
    return site_chrome.read_game_names(root)


def _retitle(page: str, title: str, description: str, visit: str, seo: dict[str, dict[str, str]] | None = None) -> str:
    """<title>, description, og:title, og:description et chemin du compteur de visites ; og:image et twitter: restent ceux du modèle.
    `seo` (site_chrome.seo_texts) donne le title et la description SEO de la page `visit` quand il la connaît ; sinon `title` et
    `description` servent tels quels (sans marque en suffixe)."""
    title, description = (html.escape(s) for s in site_chrome.seo(seo or {}, visit, title, description))
    page = re.sub(r"<title>.*?</title>", lambda _: f"<title>{title}</title>", page, count=1, flags=re.S)
    for field, value in (('name="description"', description), ('property="og:title"', title), ('property="og:description"', description)):
        page = re.sub(rf'(<meta {field} content=")[^"]*', lambda m, value=value: m.group(1) + value, page, count=1)
    return VISIT_PATH.sub(lambda m: m.group(1) + visit, page)


def _with_player(page: str) -> str:
    """Le lecteur au clic dans une page à top plays, chaque élément une seule fois (une page refabriquée ne change pas) :
    l'empreinte 'sha256-PLAYER_HASH' à la fin de script-src, EMBED_CSP et « ; » juste avant « object-src 'none' », et
    <script>PLAYER_JS</script> sur sa propre ligne, juste avant </body>. Tout le reste de la CSP reste identique octet pour octet.

    Lève BlogError sans balise de CSP, sans « object-src 'none' », sans script-src (l'ajouter changerait ce que default-src autorise)
    ou sans </body> : on ne devine pas où placer ces ajouts (generate ajoute le nom du modèle).
    """
    meta = CSP_META.search(page)
    if meta is None:
        raise BlogError(["balise Content-Security-Policy introuvable, impossible d'ajouter frame-src"])
    policy = meta.group(1)
    if EMBED_CSP not in (directive.strip() for directive in policy.split(";")):
        if OBJECT_SRC.search(policy) is None:
            raise BlogError(["CSP sans object-src 'none', impossible d'ajouter frame-src"])
        policy = OBJECT_SRC.sub(lambda found: f"{EMBED_CSP}; {found.group(0)}", policy, count=1)
    return _with_script(page[:meta.start(1)] + policy + page[meta.end(1):], PLAYER_JS, PLAYER_HASH, "du lecteur au clic")


def _with_script(page: str, script: str, digest: str, what: str) -> str:
    """site_chrome.with_script, avec les erreurs du Blog : un script inline, une seule fois, et son empreinte dans la CSP."""
    try:
        return site_chrome.with_script(page, script, digest, what)
    except site_chrome.ChromeError as error:
        raise BlogError(error.problems) from None


def _with_menu(page: str, lang: str, prefix: str, path: str, home_page: str) -> str:
    """Le menu et le pied de page du site (site_chrome.with_chrome) sur une page du Blog : l'en-tête du modèle devient celui des
    accueils (la marque et le menu de langue du modèle y sont gardés ; « Blog » est marqué aria-current), le script du menu s'ajoute
    avec son empreinte dans la CSP, le pied de page est celui de l'accueil de la langue (`home_page`) et BLOG_STYLE s'ajoute.
    Une page refabriquée ne change pas.

    Lève BlogError sans <header> contenant la marque (a.brand) et le menu de langue (details.lang.langs), sans <footer>, ou sans le
    <footer> de l'accueil."""
    try:
        return site_chrome.with_chrome(page, lang, home_page, an.HOMES[lang], prefix, path, home=site_chrome.home_link(lang, prefix),
                                       news=prefix + an.PAGES[lang], hub=prefix + HUBS[lang], label=LABELS[lang]["kicker"],
                                       current="hub", live=prefix + LIVE_PAGES[lang], css=BLOG_STYLE)
    except site_chrome.ChromeError as error:
        raise BlogError(error.problems) from None


def _with_main(page: str, main_html: str) -> str:
    return MAIN.sub(lambda _: f'<main class="wrap">{main_html}</main>', page, count=1)


def _with_jsonld(page: str, jsonld: str) -> str:
    """Les données structurées du modèle remplacées par `jsonld`, à la place du premier bloc. Les blocs suivants sont retirés,
    avec leur ligne quand ils l'occupent seuls (les deux blocs de `jsonld` se suivent sur une ligne : la refabrication ne change rien)."""
    seen: list[str] = []

    def swap(match: re.Match) -> str:
        seen.append(match.group(0))
        eol = match.group(1) or ""
        if len(seen) == 1:
            return jsonld + eol
        alone = match.start() == 0 or match.string[match.start() - 1] == "\n"
        return "" if alone else eol

    return JSON_LD_LINE.sub(swap, page)


def render_guide_page(lang: str, template: str, page: dict, main_html: str, jsonld: str, home_page: str,
                      seo: dict[str, dict[str, str]] | None = None) -> str:
    """Une page du Blog fabriquée dans `template` : la page de son jeu dans la langue, celle de league-of-legends pour une page
    sans jeu (§6 « Fabrication »). La CSP, le pied de page, la couleur du jeu (--g) et l'og:image restent ceux du modèle.

    Les adresses <dossier des jeux>/<jeu>.html (canonical, hreflang, menu de langue) deviennent <dossier du Blog>/<id>.html ;
    titre, description, og:title, og:description et compteur de visites deviennent ceux de la page, BLOG_STYLE s'ajoute ;
    l'en-tête devient le menu du site (_with_menu : son script, et son empreinte dans la CSP) ;
    quand `main_html` contient des cartes de lecture (class="video"), la page reçoit le script du lecteur au clic et sa CSP gagne
    l'empreinte du script et EMBED_CSP (_with_player) ; sinon ni script ni changement de CSP ;
    puis <main> reçoit `main_html` et les données structurées du modèle laissent la place à `jsonld`, en dernier pour
    qu'aucun remplacement ne touche à ces textes venus des données.
    """
    game, target = page.get("game") or TEMPLATE_GAME, page["id"]
    out = template
    for other in an.LANGS:
        out = an.rename_page(out, f"{GAME_DIRS[other]}/{game}.html", f"{BLOG_DIRS[other]}/{target}.html")
    out = an.public_urls(out)  # adresses déclarées sans .html (le Worker renvoie les .html), même si le modèle les a encore
    out = re.sub(r'(<meta property="og:type" content=")[^"]*', lambda m: m.group(1) + "article", out, count=1)
    if page.get("image"):  # la couverture devient l'image de partage ; sans couverture, celle du modèle reste
        out = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + cover_url(page), out, count=1)
    out = _retitle(out, page[lang]["title"], page[lang]["description"], f"{BLOG_DIRS[lang]}/{target}", seo)
    out = _with_menu(out, lang, _page_prefix(lang), f"{BLOG_DIRS[lang]}/{target}", home_page)
    if 'class="video"' in main_html:  # les données y sont échappées (« " » devient &quot;) : seule une carte du Blog produit ce texte
        out = _with_player(out)
    return _with_jsonld(_with_main(out, main_html), jsonld)


def render_hub_page(lang: str, template: str, main_html: str, home_page: str, seo: dict[str, dict[str, str]] | None = None) -> str:
    """L'accueil du Blog d'une langue, fabriqué comme les pages News (actualites.render_page) dans la page « What's new » :
    liens de langue, canonical et hreflang vers les 5 accueils du Blog, lien RSS retiré, titre, description, compteur, menu du site
    (_with_menu), <main>."""
    labels = LABELS[lang]
    page = template
    for other, name in an.TEMPLATES.items():
        page = an.rename_page(page, name, HUBS[other])
    page = an.public_urls(page)
    page = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\r?\n?', "", page)
    page = _retitle(page, labels["head"], labels["lead"], HUBS[lang].removesuffix(".html"), seo)  # <title> : seo ou head ; H1 : title
    return _with_main(_with_menu(page, lang, site_chrome.prefix_for(HUBS[lang]), HUBS[lang].removesuffix(".html"), home_page), main_html)


def _sitemap_line(path: str, lastmod: str, address) -> str:
    """Une entrée du sitemap sur une ligne, comme celles des pages News ; `address(langue)` donne l'adresse de la page dans chaque langue."""
    alternates = [(lang, address(lang)) for lang in an.LANGS] + [("x-default", address("en"))]
    links = "".join(f'<xhtml:link rel="alternate" hreflang="{lang}" href="{an.public_url(href)}"/>' for lang, href in alternates)
    return f"<url><loc>{an.public_url(path)}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq>{links}</url>"


def sitemap_block(pages: list[dict], eol: str) -> str:
    """Le contenu entre SITEMAP_MARKERS : une ligne par accueil du Blog et par page visible dans chaque langue, triées par adresse
    publiée (sans .html, comme toutes les adresses du sitemap : actualites.public_url).

    lastmod : `updated` pour une page, la plus récente des `updated` visibles pour un accueil. Les identifiants, validés, n'ont rien
    à échapper. Sans page visible, il n'y a ni page ni accueil : le bloc se réduit à une fin de ligne.
    """
    entries: dict[str, str] = {}
    if pages:
        newest = max(page["updated"] for page in pages)
        for lang in an.LANGS:
            entries[HUBS[lang]] = _sitemap_line(HUBS[lang], newest, lambda other: HUBS[other])
            for page in pages:
                path = f"{BLOG_DIRS[lang]}/{page['id']}.html"
                entries[path] = _sitemap_line(path, page["updated"], lambda other, page_id=page["id"]: f"{BLOG_DIRS[other]}/{page_id}.html")
    return eol + "".join(entries[path] + eol for path in sorted(entries, key=an.public_url))


# --- Génération -------------------------------------------------------------------------------------------------

def _read(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def _no_markers(name: str, markers: tuple[str, str]) -> str:
    return f"{name} : marqueurs {markers[0]} … {markers[1]} introuvables"


def _orphans(root: Path, produced: set[str]) -> list[str]:
    """Fichiers des dossiers du Blog et accueils du Blog qu'aucune page visible ne produit : signalés, jamais supprimés."""
    found = [name for name in HUBS.values() if (root / name).is_file()]
    for folder in BLOG_DIRS.values():
        found += [f"{folder}/{path.name}" for path in (root / folder).glob("*.html") if path.is_file()]
    return [f"{name} : page orpheline (aucune page visible de blog-src/pages ne la produit), à supprimer à la main"
            for name in sorted(found) if name not in produced]


def _guide_page(lang: str, page: dict, template: str, shown: list[dict], names: dict[str, str], videos: dict[str, list[dict]],
                home_page: str, seo: dict[str, dict[str, str]] | None = None) -> str:
    """Une page du Blog complète : contenu de <main>, données structurées (fil d'Ariane en adresses absolues), assemblage dans le modèle."""
    home = read_home(template)
    game, url = page.get("game"), an.public_url(f"{BLOG_DIRS[lang]}/{page['id']}.html")
    articles = [entry for entry in shown if game and entry["kind"] != "game" and entry.get("game") == game and entry["id"] != page["id"]]
    others = [entry for entry in shown if entry["kind"] == "game" and entry["id"] != page["id"]]
    top_plays = videos.get(game, []) if page["kind"] == "game" else []  # spec §7 : la fiche du jeu seulement, pas ses guides ni notes de version
    main_html = render_guide_main(page, lang, names, home, top_plays, articles, others)
    last = names.get(game, game) if page["kind"] == "game" else page[lang]["title"]
    crumbs = [(home[1], an.public_url(urljoin(url, home[0]))), (LABELS[lang]["kicker"], an.public_url(HUBS[lang])), (last, url)]
    return render_guide_page(lang, template, page, main_html, render_jsonld(page, lang, url, crumbs), home_page, seo)


def generate(root: Path, now: datetime) -> dict[str, str]:
    """Calcule en mémoire les pages et les accueils du Blog, le lien de guide des pages de jeux et le bloc du sitemap ;
    rend {chemin relatif: nouveau contenu} pour les seuls fichiers qui changent.

    Lève BlogError avec tous les problèmes à la fois (données invalides, modèle ou marqueurs introuvables, pages orphelines) :
    rien n'est alors écrit. Sans page visible, aucune page ni aucun accueil n'est produit, et les blocs existants sont vidés.
    """
    pages, topplays = load_pages(root), load_topplays(root)
    today = now.astimezone(an.paris()).date()
    shown, videos, names = visible_pages(pages, today), visible_topplays(topplays, today), read_names(root)
    try:
        seo = site_chrome.seo_texts(root)
    except site_chrome.ChromeError as error:
        raise BlogError(error.problems) from error
    files: dict[str, str | None] = {}

    def read(name: str) -> str | None:  # chaque fichier n'est lu qu'une fois (un modèle sert à plusieurs pages)
        if name not in files:
            files[name] = _read(root / name)
        return files[name]

    output: dict[str, str] = {}
    produced: set[str] = set()
    problems: list[str] = []
    for lang in (an.LANGS if shown else ()):  # sans page visible, ni page ni accueil
        hub, hub_template, home_page = HUBS[lang], read(an.TEMPLATES[lang]), read(an.HOMES[lang])
        produced.add(hub)
        if home_page is None:
            problems.append(f"{an.HOMES[lang]} introuvable (pied de page des pages du Blog)")
        if hub_template is None:
            problems.append(f"{an.TEMPLATES[lang]} introuvable (modèle de {hub})")
        elif home_page is not None:
            try:
                output[hub] = an.same_eol(render_hub_page(lang, hub_template, render_hub_main(lang, shown, names[lang]), home_page, seo), hub_template)
            except BlogError as error:
                problems += [f"{hub} : {problem}" for problem in error.problems]
        for page in shown:
            path, name = f"{BLOG_DIRS[lang]}/{page['id']}.html", f"{GAME_DIRS[lang]}/{page.get('game') or TEMPLATE_GAME}.html"
            produced.add(path)
            template = read(name)
            if template is None:
                problems.append(f"{name} introuvable (modèle de {path})")
                continue
            if home_page is None:  # déjà signalé : sans l'accueil, pas de pied de page
                continue
            try:
                output[path] = an.same_eol(_guide_page(lang, page, template, shown, names[lang], videos, home_page, seo), template)
            except BlogError as error:
                problems += [f"{name} : {problem}" for problem in error.problems]
    problems += _orphans(root, produced)
    fiches = {page["id"]: page for page in shown if page["kind"] == "game"}
    for lang, folder in GAME_DIRS.items():
        for game in sorted({path.stem for path in (root / folder).glob("*.html")} | set(fiches)):
            name, fiche = f"{folder}/{game}.html", fiches.get(game)
            old = read(name)
            if old is not None and an.extract_between(old, *GUIDE_MARKERS) is not None:
                output[name] = an.update_between(old, *GUIDE_MARKERS, render_guide_link(fiche, lang, names[lang].get(game, game)), name)
            elif fiche is not None:  # sans marqueurs, une page de jeu n'est en faute que si une fiche visible lui doit son lien
                problems.append(f"{name} introuvable (fiche {game} du Blog)" if old is None else _no_markers(name, GUIDE_MARKERS))
    sitemap = read("sitemap.xml")
    if sitemap is not None and an.extract_between(sitemap, *SITEMAP_MARKERS) is not None:
        output["sitemap.xml"] = an.update_between(sitemap, *SITEMAP_MARKERS, sitemap_block(shown, _eol(sitemap)), "sitemap.xml")
    elif shown:
        problems.append("sitemap.xml introuvable" if sitemap is None else _no_markers("sitemap.xml", SITEMAP_MARKERS))
    if problems:
        raise BlogError(problems)
    # Après la sortie sur l'App Store (`storeURL` dans version.json), les pages repartent de libellés qui parlent encore de la bêta :
    # on les repasse par la bascule, sinon chaque génération défait le travail de bascule_appstore.py.
    released = (root / "version.json").is_file() and json.loads((root / "version.json").read_text(encoding="utf-8")).get("storeURL")
    if released:
        output = {name: bascule_appstore.switch(content) if name.endswith(".html") else content for name, content in output.items()}
    return {name: content for name, content in output.items() if content != read(name)}


def _verify(root: Path) -> None:
    """Valide les trois fichiers de blog-src/, avec tous leurs problèmes à la fois ; ne lit ni modèle ni base des fuseaux."""
    problems: list[str] = []
    for load in (load_pages, load_channels, load_topplays):
        try:
            load(root)
        except BlogError as error:
            problems += error.problems
    if problems:
        raise BlogError(problems)


# --- Contrôle des sources : --sources ---------------------------------------------------------------------------
# Réseau, à la demande, jamais dans le job du matin (§10 de la spec, étapes 2 et 4). Chaque fiche a son tableau
# blog-src/claims/<id>.md, `| Affirmation | Source | Extrait |`, une ligne par fait ; rien n'est jamais écrit.

USER_AGENT = "esportly-site/1.0 (+https://esportly.eu)"
FETCH_TIMEOUT = 20  # secondes
FETCH_MAX_BYTES = 2_000_000
MAX_EXCERPT_WORDS = 12
MANUAL = re.compile(r"manuel\s*:\s*(\S.*)", re.I | re.S)  # « manuel : <raison> » : une page qu'un script ne sait pas lire
TABLE_SEPARATOR = re.compile(r":?-+:?")
TYPOGRAPHY = str.maketrans({"´": "'", "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
# Éléments qui séparent deux textes : une espace entre eux (les autres, comme <a> ou <b>, collent leur texte à celui d'à côté).
BLOCK_TAGS = frozenset(
    "address article aside blockquote br dd details div dl dt fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main "
    "nav ol p pre section summary table tbody td tfoot th thead title tr ul".split())


def _cells(line: str) -> list[str]:
    """Les cellules d'une ligne de tableau Markdown, sans espaces autour ; vide pour une ligne qui n'en est pas une."""
    line = line.strip()
    if not line.startswith("|"):
        return []
    parts = re.split(r"(?<!\\)\|", line)[1:]  # une barre précédée d'une contre-oblique fait partie du texte
    if parts and parts[-1] == "":  # la barre finale
        parts.pop()
    return [part.strip().replace("\\|", "|") for part in parts]


def parse_claims(text: str) -> list[dict]:
    """Les affirmations d'un tableau Markdown `| Affirmation | Source | Extrait |` : {claim, source, excerpt, manual, note}.

    Un extrait « manuel : <raison> » (avec ou sans espace avant les deux-points) donne manual=True, excerpt="" et la raison dans note.
    L'en-tête, le séparateur et les lignes de moins de 3 cellules sont ignorés.
    """
    claims = []
    for line in text.lstrip("﻿").splitlines():  # un éditeur peut poser une marque d'ordre des octets
        cells = _cells(line)[:3]
        if len(cells) < 3 or all(TABLE_SEPARATOR.fullmatch(cell) for cell in cells) or [cell.lower() for cell in cells] == ["affirmation", "source", "extrait"]:
            continue
        claim, source, excerpt = cells
        manual = MANUAL.fullmatch(excerpt)
        claims.append({"claim": claim, "source": source, "excerpt": "" if manual else excerpt, "manual": manual is not None,
                       "note": manual.group(1).strip() if manual else ""})
    return claims


def normalize(text: str) -> str:
    """Texte comparable : minuscules, suites d'espaces réduites à une, guillemets et tirets typographiques ramenés à leur forme simple."""
    return " ".join(text.translate(TYPOGRAPHY).lower().split())


class _TextExtractor(HTMLParser):
    """Collecte le texte d'une page : le contenu de <script> et de <style> est laissé de côté, les entités sont décodées."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0  # profondeur dans <script> et <style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(html_text: str) -> str:
    """Le texte d'une page HTML, sans <script> ni <style>, entités décodées (« &amp; » devient « & »), une espace entre deux blocs."""
    extractor = _TextExtractor()
    extractor.feed(html_text)
    extractor.close()
    return "".join(extractor.parts)


def fetch_page(url: str) -> tuple[int, str]:
    """Télécharge une page : (code HTTP après redirections, corps). Un code d'erreur HTTP est rendu tel quel, avec un corps vide ;
    une panne réseau est retentée une fois, puis rend (0, ""). Au plus 2 000 000 d'octets lus, décodés en UTF-8 (octets invalides remplacés)."""
    for _ in range(2):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                return response.status, response.read(FETCH_MAX_BYTES).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, ""
        except (OSError, http.client.HTTPException, ValueError):  # dont délai dépassé, connexion refusée ou coupée
            pass
    return 0, ""


def _claims_file(root: Path, page_id: str, problems: list[str]) -> list[dict] | None:
    """Les affirmations de blog-src/claims/<id>.md ; None, avec un problème noté, si le fichier manque ou est illisible."""
    name = f"blog-src/claims/{page_id}.md"
    try:
        return parse_claims((root / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{page_id} : tableau des affirmations introuvable ({name})")
    except (OSError, ValueError) as error:
        problems.append(f"{page_id} : {name} illisible : {error}")
    return None


def _sources_pages(root: Path, today: date | None) -> list[dict]:
    """Les pages visibles de blog-src/pages, à contrôler ; lève BlogError si elles sont invalides. Sans `today`, le jour à Paris
    (la base des fuseaux n'est demandée que s'il y a des pages)."""
    pages = load_pages(root)
    if not pages:
        return []
    if today is None:
        today = datetime.now(timezone.utc).astimezone(an.paris()).date()
    return visible_pages(pages, today)


def check_sources(root: Path, fetch: Callable[[str], tuple[int, str]] = fetch_page, today: date | None = None) -> tuple[list[str], list[str]]:
    """Contrôle mécanique des sources de chaque page visible (§10 de la spec) ; rend (problèmes, lignes « vérification manuelle »).

    Chaque page doit avoir son tableau ; chaque adresse déclarée (téléchargée une seule fois par exécution) répond 200 après redirections ;
    chaque affirmation cite une source déclarée de la page et, sauf ligne « manuel : <raison> », un extrait de 12 mots au plus qui figure
    dans le texte de la page citée (majuscules, espaces et guillemets normalisés) ; chaque source citée par une section est utilisée par
    au moins une affirmation. Les lignes manuelles ne sont pas des problèmes : elles sont rendues à part, pour une vérification à la main.
    Chaque problème commence par l'identifiant de la page ; BlogError (données invalides) n'est pas rattrapée.
    """
    problems: list[str] = []
    manual: list[str] = []
    fetched: dict[str, tuple[int, str]] = {}  # adresse -> (code, texte normalisé)

    def get(url: str) -> tuple[int, str]:
        if url not in fetched:
            status, body = fetch(url)
            fetched[url] = (status, normalize(visible_text(body)) if status == 200 else "")
        return fetched[url]

    for page in _sources_pages(root, today):
        page_id = page["id"]
        answers: dict[str, tuple[int, str]] = {}
        for source in page["sources"]:
            answers[source["id"]] = get(source["url"])
            if (status := answers[source["id"]][0]) != 200:
                reason = "ne répond pas" if status == 0 else f"HTTP {status}"
                problems.append(f"{page_id} : source {source['id']} ({source['url']}) : {reason}")
        claims = _claims_file(root, page_id, problems)
        if claims is None:
            continue
        used: set[str] = set()
        for row in claims:
            ref, claim, excerpt = row["source"], row["claim"], row["excerpt"]
            if ref not in answers:
                problems.append(f"{page_id} : affirmation « {claim} » : source « {ref} » non déclarée dans la page")
                continue
            used.add(ref)
            if row["manual"]:
                manual.append(f"{page_id} : source {ref} : {row['note']} (affirmation : {claim})")
                continue
            words = len(excerpt.split())
            if words == 0:
                problems.append(f"{page_id} : source {ref} : extrait vide pour l'affirmation « {claim} »")
            elif words > MAX_EXCERPT_WORDS:
                problems.append(f"{page_id} : source {ref} : extrait de {words} mots ({MAX_EXCERPT_WORDS} au plus) : « {excerpt} »")
            elif answers[ref][0] == 200 and normalize(excerpt) not in answers[ref][1]:  # une page injoignable est déjà signalée
                problems.append(f"{page_id} : source {ref} : extrait introuvable dans la page : « {excerpt} »")
        cited = {ref for section in page["sections"] for ref in section["cite"]}
        problems += [f"{page_id} : source {source['id']} : citée par une section, mais aucune affirmation du tableau ne s'y appuie"
                     for source in page["sources"] if source["id"] in cited and source["id"] not in used]
    return problems, manual


# --- Ligne de commande ------------------------------------------------------------------------------------------

def _refuse(problems: list[str]) -> int:
    """Le refus habituel : le nombre de problèmes puis un par ligne, sur la sortie d'erreur ; code de sortie 1."""
    print(f"Refus : {len(problems)} problème(s)", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def _check_sources_command(root: Path, now: datetime | None, fetch: Callable[[str], tuple[int, str]] | None) -> int:
    """--sources : les lignes manuelles sur la sortie standard, les problèmes (refus, code 1) sur la sortie d'erreur, sinon le bilan."""
    today = None if now is None else now.astimezone(an.paris()).date()
    problems, manual = check_sources(root, fetch if fetch is not None else fetch_page, today)
    if manual:
        print("Vérification manuelle :")
        for line in manual:
            print(f"  - {line}")
    if problems:
        return _refuse(problems)
    print(f"Sources : {len(_sources_pages(root, today))} page(s) vérifiée(s).")
    return 0


def main(argv: list[str], root: Path = ROOT, now: datetime | None = None, fetch: Callable[[str], tuple[int, str]] | None = None) -> int:
    """Ligne de commande (voir le haut du fichier). `fetch` remplace fetch_page pour --sources (les tests n'ont pas de réseau)."""
    trial = "--essai" in argv
    try:
        if "--verifier" in argv:
            _verify(root)
            print("blog-src : valide")
            return 0
        if "--sources" in argv:
            return _check_sources_command(root, now, fetch)
        changes = generate(root, now or datetime.now(timezone.utc))
    except an.NewsError as error:  # BlogError en dérive
        return _refuse(error.problems)
    if not trial:
        for name, content in changes.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="")
    print(f"{len(changes)} fichier(s) {'à changer' if trial else 'changé(s)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
