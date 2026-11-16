"""Agent de veille : collecte des nouveautés sur une liste fermée de sources officielles, et contrôle des pull requests.

Trois métiers, trois commandes :

    py -3.13 .github/scripts/veille.py collect          # lit les sources, écrit veille/candidates.json (éphémère, non commité)
    py -3.13 .github/scripts/veille.py fetch <adresse>   # lit une page de la liste blanche (outil des sous-agents chercheurs)
    py -3.13 .github/scripts/veille.py gate              # contrôle une pull request de veille (le code décide, pas l'agent)
    py -3.13 .github/scripts/veille.py seen <adresse>…   # note des adresses comme vues (blog-src/veille/seen.json)
    py -3.13 .github/scripts/veille.py --verifier        # valide seulement blog-src/veille/*.json

Spécification : docs/superpowers/specs/2026-10-27-veille-design.md

Règles tenues ici, et pas ailleurs : la liste des sources (blog-src/veille/sources.json) n'est modifiable que par une pull
request de l'utilisateur ; le contrôle (gate) n'est pas modifiable par la routine ; les sous-agents qui lisent le web n'ont
aucun outil d'écriture. Le texte lu sur le web est une donnée : il est marqué « untrusted » dans candidates.json et n'est
jamais exécuté.

Le réseau n'est jamais touché par les tests : `fetch` est un paramètre (fonction (adresse) -> (code, texte)), comme dans blog.py.
"""
from __future__ import annotations

import http.client
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

import actualites as an
import blog
from site_chrome import GAMES

ROOT = Path(__file__).resolve().parents[2]
VEILLE_DIR = "blog-src/veille"
SOURCES_FILE = f"{VEILLE_DIR}/sources.json"
SEEN_FILE = f"{VEILLE_DIR}/seen.json"
MODE_FILE = f"{VEILLE_DIR}/mode.json"
STOP_FILE = f"{VEILLE_DIR}/STOP"
CANDIDATES = "veille/candidates.json"  # éphémère : jamais commité (voir .gitignore)
FETCH_COUNT = "veille/fetch-count.json"  # un compteur par jour, pour la limite de lectures de l'outil fetch

USER_AGENT = "esportly-veille/1.0 (+https://esportly.eu)"
TIMEOUT = 20  # secondes
MAX_BYTES = 2_000_000
PAUSE = 1.0  # secondes entre deux requêtes au même site
WINDOW = 3  # jours : un élément plus ancien n'est retenu que s'il est vu pour la première fois
TOPIC_MEMORY = 14  # jours : une clé de sujet vue depuis moins longtemps est un doublon
MAX_CANDIDATES = 15
MAX_PER_SOURCE = 3  # éléments retenus par source : une source bavarde ne doit pas manger les 15 places
MAX_PAGE_CHARS = 20_000
MAX_LINKS_PER_PAGE = 40
MAX_READS_PER_DAY = 40  # lectures de l'outil fetch (sous-agents chercheurs)
MAX_PER_DAY = 3  # articles publiés par jour, au plus
MIN_WORDS, MAX_WORDS = 150, 450  # texte anglais d'un article
MAX_RUN = 6  # mots identiques d'affilée tolérés avec une source
MAX_OVERLAP_SOURCE = 0.15  # recouvrement des suites de 5 mots avec une source
MAX_OVERLAP_PAGE = 0.40  # recouvrement des suites de 5 mots avec une page existante
SHINGLE = 5
KINDS = ("release", "news", "guide")
TYPES = ("release", "patch", "esport", "guide")
SOURCE_KEYS = {"id", "name", "url", "feed", "kind", "games", "types", "lang", "note", "also"}
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
WORD = re.compile(r"[\w'-]+", re.UNICODE)
SKIP_SUFFIX = (".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".xml", ".json", ".pdf", ".zip")
# Derniers segments d'adresse qui désignent une rubrique et non un article : jamais retenus comme sujet.
NAV_LAST = frozenset("about contact privacy terms legal login signin signup register search schedule schedules teams team "
                     "tickets ticket standings results matches match news events event shop store support help faq "
                     "careers press partners".split())
TITLE_MAX = 140
TITLE_AUTHOR = re.compile(r"\s*(?:[A-Z][\w.'-]*\s+){0,4}(?:Staff|Team|Writer|Editor)\s*•.*$")  # « … Fan FestLoL Esports Staff • Novemb »
TITLE_DATE = re.compile(r"\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                        r"\s+\d{1,2},\s+\d{4}\s*$")
TITLE_TAIL = re.compile(r"\s*(?:Read More|Read more|Lire la suite|En savoir plus|Learn more|Continuer la lecture)\s*$")
LOCALE = re.compile(r"^/([a-z]{2}(?:-[A-Za-z]{2})?)(?:/|$)")  # « /en-US/ », « /fr/ » : la langue dans l'adresse
IGNORED_FILES = ("__pycache__/", ".pyc")  # écrits par Python lui-même : jamais un fichier de la pull request
_LAST_READ: dict[str, float] = {}  # hôte -> instant monotone de la dernière lecture
_ROBOTS: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class VeilleError(Exception):
    """Données de la veille invalides : `problems` liste tout ce qui ne va pas."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problème(s)")


class HorsListe(Exception):
    """Adresse hors de la liste blanche des domaines déclarés (une redirection comprise)."""


# --- Lecture des fichiers de blog-src/veille ----------------------------------------------------------------------

def _read_json(path: Path, problems: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        problems.append(f"{path.name} : illisible : {error}")
        return None


def load_sources(root: Path = ROOT) -> list[dict]:
    """Les sources déclarées (blog-src/veille/sources.json), validées ; lève VeilleError en listant tous les problèmes."""
    problems: list[str] = []
    data = _read_json(root / SOURCES_FILE, problems)
    if problems:
        raise VeilleError(problems)
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise VeilleError([f"{SOURCES_FILE} : doit être un objet avec « sources » (une liste)"])
    for key in data:
        if key != "sources":
            problems.append(f"{SOURCES_FILE} : clé inconnue « {key} »")
    sources, ids = [], set()
    for index, source in enumerate(data["sources"]):
        where = f"sources[{index}]"
        if not isinstance(source, dict):
            problems.append(f"{where} : doit être un objet")
            continue
        for key in source:
            if key not in SOURCE_KEYS:
                problems.append(f"{where} : champ inconnu « {key} »")
        sid = source.get("id")
        if not isinstance(sid, str) or not ID.fullmatch(sid):
            problems.append(f"{where}.id : « {sid} » invalide (minuscules, chiffres et tirets)")
        elif sid in ids:
            problems.append(f"{where}.id : « {sid} » en double")
        else:
            ids.add(sid)
        if not isinstance(source.get("name"), str) or not source.get("name"):
            problems.append(f"{where}.name : manquant")
        kind = source.get("kind")
        if kind not in ("feed", "page"):
            problems.append(f"{where}.kind : « {kind} » invalide (feed ou page)")
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            problems.append(f"{where}.url : doit être une adresse https://")
        feed = source.get("feed")
        if kind == "feed" and (not isinstance(feed, str) or not feed.startswith("https://")):
            problems.append(f"{where}.feed : obligatoire et en https:// pour kind feed")
        if kind == "page" and feed not in (None, ""):
            problems.append(f"{where}.feed : inutile pour kind page")
        games = source.get("games")
        if not isinstance(games, list) or any(not isinstance(game, str) or game not in GAMES for game in games):
            problems.append(f"{where}.games : liste de jeux parmi {', '.join(GAMES)} (vide pour une source générale)")
        types = source.get("types")
        if not isinstance(types, list) or not types or any(t not in TYPES for t in types):
            problems.append(f"{where}.types : liste non vide parmi {', '.join(TYPES)}")
        if not isinstance(source.get("lang"), str) or not source.get("lang"):
            problems.append(f"{where}.lang : manquant")
        if not isinstance(source.get("note"), str) or not source.get("note"):
            problems.append(f"{where}.note : manquante (pourquoi la source est fiable)")
        also = source.get("also", [])
        if not isinstance(also, list) or any(not isinstance(domain, str) or "://" in domain for domain in also):
            problems.append(f"{where}.also : liste de domaines (sans https://)")
        sources.append(source)
    if problems:
        raise VeilleError(problems)
    return sources


def load_seen(root: Path = ROOT) -> dict:
    """Les adresses et les clés de sujet déjà vues : {"seen": {adresse: jour}, "topics": {clé: jour}}."""
    problems: list[str] = []
    data = _read_json(root / SEEN_FILE, problems) if (root / SEEN_FILE).is_file() else {"seen": {}, "topics": {}}
    if problems:
        raise VeilleError(problems)
    if not isinstance(data, dict):
        raise VeilleError([f"{SEEN_FILE} : doit être un objet"])
    seen = data.get("seen")
    topics = data.get("topics")
    if not isinstance(seen, dict) or not isinstance(topics, dict):
        raise VeilleError([f"{SEEN_FILE} : « seen » et « topics » doivent être des objets"])
    return {"seen": seen, "topics": topics}


def whitelist(sources: list[dict]) -> set[str]:
    """Les domaines autorisés : ceux des adresses déclarées, plus les domaines « also » de la même organisation."""
    allowed: set[str] = set()
    for source in sources:
        for value in (source.get("url"), source.get("feed")):
            if isinstance(value, str) and value:
                allowed.add(urllib.parse.urlsplit(value).netloc.lower())
        for domain in source.get("also", []) or []:
            allowed.add(domain.lower())
    return allowed


# --- Réseau -------------------------------------------------------------------------------------------------------

class _Redirects(urllib.request.HTTPRedirectHandler):
    """Refuse toute redirection qui sort de la liste blanche (une source ne doit pas mener ailleurs)."""

    def __init__(self, allowed: set[str]):
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc.lower() not in self.allowed:
            raise HorsListe(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Ouvreur:
    """Un ouvreur qui respecte la liste blanche, la pause entre deux lectures d'un même site et la taille maximale."""

    def __init__(self, allowed: set[str]):
        self.allowed = allowed
        self.opener = urllib.request.build_opener(_Redirects(allowed))

    def get(self, url: str) -> tuple[int, str]:
        """(code HTTP après redirections, texte) ; lève HorsListe pour une redirection sortante, 0 pour une panne réseau."""
        host = urllib.parse.urlsplit(url).netloc.lower()
        wait = PAUSE - (time.monotonic() - _LAST_READ.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _LAST_READ[host] = time.monotonic()
        for _ in range(2):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    return response.status, response.read(MAX_BYTES).decode("utf-8", errors="replace")
            except urllib.error.HTTPError as error:
                error.close()
                return error.code, ""
            except (OSError, http.client.HTTPException, ValueError):  # dont délai dépassé et connexion coupée
                continue
        return 0, ""


def robots_ok(url: str) -> bool:
    """Vrai si robots.txt autorise notre agent (ou tous les agents) à lire cette adresse.

    Un robots.txt illisible est un refus : on ne lit pas une page dont on n'a pas pu vérifier la permission.
    """
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _ROBOTS:
        try:
            request = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=ssl.create_default_context()) as response:
                text = response.read(MAX_BYTES).decode("utf-8", errors="replace")
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(text.splitlines())
            _ROBOTS[base] = parser
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (404, 410):  # aucun robots.txt : rien n'est interdit (RFC 9309)
                _ROBOTS[base] = urllib.robotparser.RobotFileParser()
            else:  # 401, 403, 5xx : permission inconnue, on ne lit pas
                _ROBOTS[base] = None
        except Exception:  # panne réseau : refus prudent, mémorisé pour l'exécution
            _ROBOTS[base] = None
    parser = _ROBOTS[base]
    if parser is None:
        return False
    return parser.can_fetch(USER_AGENT, url) or parser.can_fetch("*", url)


def canonical(url: str) -> str:
    """L'adresse sans paramètres de suivi ni fragment (la forme comparée et stockée)."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/") or "/", "", ""))


def domain_ok(url: str, allowed: set[str]) -> bool:
    return urllib.parse.urlsplit(url).netloc.lower() in allowed


# --- Flux et pages ------------------------------------------------------------------------------------------------

def _text(node) -> str:
    return " ".join((node.text or "").split())


def _child(node, *names):
    for child in node:
        if child.tag.rsplit("}", 1)[-1].lower() in names:
            return child
    return None


def _day(value: str) -> date | None:
    """Le jour d'un horodatage de flux (RFC 822 pour RSS, ISO 8601 pour Atom) ; None s'il est illisible."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date()


def parse_feed(text: str, source_url: str) -> list[dict]:
    """Les éléments d'un flux RSS ou Atom : [{title, url, published}] ; lève ValueError si ce n'est pas un flux lisible.

    Un flux n'a ni DTD ni entités : un texte qui en contient vient d'ailleurs (donnée de tiers) et est refusé.
    """
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("flux avec DTD ou entités, refusé")
    root = ET.fromstring(text)
    items = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        title_node = _child(node, "title")
        link, published = "", None
        link_node = _child(node, "link")
        if link_node is not None:
            link = (link_node.get("href") or _text(link_node)).strip()
        for name in ("pubdate", "published", "updated", "date"):
            found = _child(node, name)
            if found is not None and (day := _day(_text(found))) is not None:
                published = day
                break
        if not link or title_node is None:
            continue
        link = urllib.parse.urljoin(source_url, link)
        if urllib.parse.urlsplit(link).scheme not in ("http", "https"):
            continue
        items.append({"title": _text(title_node), "url": link, "published": published})
    return items


class _Links(HTMLParser):
    """Collecte les liens d'une page avec leur texte visible."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._parts).split())))
            self._href, self._parts = None, []

    def handle_data(self, data):
        if self._href is not None and not self._skip:
            self._parts.append(data)


def page_items(text: str, page_url: str, max_links: int = MAX_LINKS_PER_PAGE) -> list[dict]:
    """Les liens d'une page HTML qui ressemblent à des articles du même site : [{title, url, published: None}].

    Aucune date n'est devinée : un élément sans date (kind page) n'est retenu que s'il est vu pour la première fois.
    """
    parser = _Links()
    parser.feed(text)
    parser.close()
    host = urllib.parse.urlsplit(page_url).netloc.lower()
    items, used = [], set()
    locale = LOCALE.match(urllib.parse.urlsplit(page_url).path)
    for href, title in parser.links:
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        url = urllib.parse.urljoin(page_url, href)
        parts = urllib.parse.urlsplit(url)
        if parts.netloc.lower() != host or parts.path.lower().endswith(SKIP_SUFFIX):
            continue
        if locale and not LOCALE.match(parts.path):  # une page « /en-US/… » mène à des articles sans langue :
            url = f"{parts.scheme}://{parts.netloc}{locale.group(0).rstrip('/')}{parts.path}"  # on garde la langue de
            parts = urllib.parse.urlsplit(url)  # la page, sinon le robot de contrôle lit une autre langue que nous
        clean = canonical(url)
        last = parts.path.strip("/").rsplit("/", 1)[-1].lower().removesuffix(".html")
        if clean in used or clean in (canonical(page_url), canonical(f"https://{host}/")) or len(parts.path.strip("/")) < 3:
            continue
        if last in NAV_LAST or last.isdigit():
            continue
        if len(title) < 20:
            continue
        original = title
        title = TITLE_AUTHOR.sub("", title).strip()  # le texte d'un lien contient souvent l'auteur et la date :
        if " • " in title:  # le début suffit, le rédacteur écrit son propre titre
            left = title.split(" • ")[0].strip()
            title = left if len(left) >= 20 else title
        title = TITLE_TAIL.sub("", title)
        title = TITLE_DATE.sub("", title)
        if len(title) < 20:  # le nettoyage a trop coupé : on garde le texte d'origine
            title = original
        title = title[:TITLE_MAX].rsplit(" ", 1)[0].strip() if len(title) > TITLE_MAX else title
        used.add(clean)
        items.append({"title": title, "url": url, "published": None})
        if len(items) >= max_links:
            break
    return items


def topic_key(title: str, game: str | None, kind: str | None) -> str:
    """La clé de sujet d'un élément : jeu, type et titre normalisé (« lol|esport|worlds 2026 les quarts »)."""
    words = [word for word in WORD.findall(blog.normalize(title)) if len(word) > 2][:8]
    return f"{game or 'esport'}|{kind or 'news'}|{' '.join(words)}"


# --- Collecte -----------------------------------------------------------------------------------------------------

def collect(root: Path = ROOT, now: datetime | None = None, fetch: Callable[[str], tuple[int, str]] | None = None,
            robots: Callable[[str], bool] | None = None) -> dict:
    """Lit les sources, garde ce qui est nouveau, télécharge le texte de chaque page retenue et écrit candidates.json.

    Rend le contenu écrit (et l'écrit sous <racine>/veille/candidates.json). `fetch(url) -> (code, texte)` remplace le réseau
    dans les tests ; les redirections hors liste blanche sont refusées comme en vrai (HorsListe).
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(an.paris()).date()
    sources = load_sources(root)
    allowed = whitelist(sources)
    seen = load_seen(root)
    get = fetch or _Ouvreur(allowed).get
    permission = robots or robots_ok
    items: list[dict] = []
    outage: list[str] = []
    for source in sources:
        address = source["feed"] if source["kind"] == "feed" else source["url"]
        if not permission(address):
            outage.append(f"{source['id']} : robots.txt refuse ou illisible")
            continue
        try:
            status, text = get(address)
        except HorsListe as error:
            outage.append(f"{source['id']} : redirection hors liste blanche ({error})")
            continue
        if status != 200 or not text:
            outage.append(f"{source['id']} : HTTP {status}")
            continue
        try:
            found = parse_feed(text, address) if source["kind"] == "feed" else page_items(text, source["url"])
        except (ValueError, ET.ParseError) as error:
            outage.append(f"{source['id']} : {error}")
            continue
        game = (source.get("games") or [None])[0]
        kind = (source.get("types") or [None])[0]
        for item in found:
            items.append({**item, "source": source["id"], "game": game, "type": kind, "lang": source.get("lang", "en")})
    candidates, refused = [], []
    seen_urls, seen_topics = [], []
    per_source: dict[str, int] = {}
    for item in sorted(items, key=lambda entry: (entry["published"] or today, entry["title"]), reverse=True):
        url = canonical(item["url"])
        key = topic_key(item["title"], item["game"], item["type"])
        if url in seen["seen"]:
            continue
        if item["published"] is not None and (today - item["published"]).days > WINDOW:
            continue
        if key in seen["topics"]:
            try:
                if (today - date.fromisoformat(seen["topics"][key])).days < TOPIC_MEMORY:
                    refused.append({"url": item["url"], "titre": item["title"], "raison": "sujet déjà traité"})
                    continue
            except (TypeError, ValueError):
                pass
        if url in seen_urls or key in seen_topics or len(candidates) >= MAX_CANDIDATES:
            continue
        if per_source.get(item["source"], 0) >= MAX_PER_SOURCE:
            continue
        seen_urls.append(url)
        seen_topics.append(key)
        per_source[item["source"]] = per_source.get(item["source"], 0) + 1
        candidates.append({"title": item["title"], "url": url, "key": key, "source": item["source"], "game": item["game"],
                           "type": item["type"], "lang": item["lang"],
                           "published": item["published"].isoformat() if item["published"] else None,
                           "text": "", "untrusted": True})
    if not candidates:
        outage.append("aucun élément nouveau")
    for candidate in candidates:  # le texte des pages retenues : ce que lisent le chercheur et le vérificateur
        if not domain_ok(candidate["url"], allowed) or not permission(candidate["url"]):
            candidate["text"] = ""
            continue
        try:
            status, text = get(candidate["url"])
        except HorsListe:
            candidate["text_error"] = "redirection hors liste blanche"
            status, text = 0, ""
        if status == 200:
            candidate["text"] = blog.visible_text(text)[:MAX_PAGE_CHARS]
        else:
            candidate["text_error"] = f"HTTP {status}"  # page illisible : le chercheur n'a rien à en tirer
    payload = {"generated": now.isoformat(timespec="seconds"), "sources_essayees": len(sources),
               "en_panne": outage, "elements_vus": len(items), "candidates": candidates, "refuses": refused[:20]}
    path = root / CANDIDATES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def fetch_command(argv: list[str], root: Path = ROOT, fetch: Callable[[str], tuple[int, str]] | None = None) -> int:
    """L'outil de lecture des sous-agents : liste blanche, robots.txt, 40 lectures par jour et par exécution comprise."""
    if not argv:
        print("usage : veille.py fetch <adresse>", file=sys.stderr)
        return 2
    url = argv[0]
    sources = load_sources(root)
    allowed = whitelist(sources)
    if not domain_ok(url, allowed):
        print(f"Refus : {url} n'est pas dans la liste blanche ({', '.join(sorted(allowed))})", file=sys.stderr)
        return 1
    if not robots_ok(url):
        print(f"Refus : robots.txt n'autorise pas la lecture de {url}", file=sys.stderr)
        return 1
    counter_path = root / FETCH_COUNT
    today = datetime.now(timezone.utc).astimezone(an.paris()).date().isoformat()
    counts = {}
    if counter_path.is_file():
        try:
            counts = json.loads(counter_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts = {}
    counts = {today: int(counts.get(today, 0))}
    if counts[today] >= MAX_READS_PER_DAY:
        print(f"Refus : {MAX_READS_PER_DAY} lectures atteintes aujourd'hui", file=sys.stderr)
        return 1
    status, text = (fetch or _Ouvreur(allowed).get)(url)
    if status != 200:
        print(f"Refus : {url} : HTTP {status}", file=sys.stderr)
        return 1
    counts[today] += 1
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text(json.dumps(counts), encoding="utf-8")
    print(blog.visible_text(text)[:MAX_PAGE_CHARS])
    return 0


def seen_command(argv: list[str], root: Path = ROOT) -> int:
    """Note des adresses comme vues (jour de Paris), pour que la collecte ne les represente pas."""
    if not argv:
        print("usage : veille.py seen <adresse>…", file=sys.stderr)
        return 2
    data = load_seen(root)
    today = datetime.now(timezone.utc).astimezone(an.paris()).date().isoformat()
    for url in argv:
        data["seen"][canonical(url)] = today
    path = root / SEEN_FILE
    path.write_text(json.dumps({"seen": dict(sorted(data["seen"].items())), "topics": data["topics"]},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(argv)} adresse(s) notée(s) comme vue(s).")
    return 0


# --- Contrôle d'une pull request de veille ------------------------------------------------------------------------

def _words(text: str) -> list[str]:
    return WORD.findall(blog.normalize(text))


def article_text(page: dict, lang: str = "en") -> str:
    """Le texte d'un article dans une langue : intertitres et paragraphes, dans l'ordre."""
    parts = []
    for section in page.get("sections", []):
        body = section.get(lang) or {}
        parts.append(body.get("heading", ""))
        parts.extend(body.get("text", []))
    return " ".join(part for part in parts if part)


def longest_run(left: list[str], right: list[str]) -> int:
    """La plus longue suite de mots identiques consécutifs entre deux textes (0 s'il n'y en a pas)."""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for word in left:
        current = [0]
        for index, other in enumerate(right, start=1):
            run = previous[index - 1] + 1 if word == other else 0
            current.append(run)
            if run > best:
                best = run
        previous = current
    return best


def shingles(words: list[str], size: int = SHINGLE) -> set[tuple[str, ...]]:
    return {tuple(words[index:index + size]) for index in range(max(0, len(words) - size + 1))}


def overlap(left: set[tuple[str, ...]], right: set[tuple[str, ...]], size: int) -> float:
    """Part des suites du texte de gauche qu'on retrouve dans celui de droite (0 si le gauche est trop court)."""
    if not left or len(left) < max(1, size):
        return 0.0
    return len(left & right) / len(left)


def _page_files(files: list[str]) -> list[str]:
    return [Path(name).stem for name in files if name.startswith("blog-src/pages/") and name.endswith(".json")]


def changed_files(root: Path = ROOT) -> list[str] | None:
    """Les fichiers changés par la branche (git diff depuis origin/main + fichiers non suivis) ; None hors dépôt git."""
    try:
        diff = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMR", "origin/main...HEAD"],
                              capture_output=True, text=True, check=True, timeout=60).stdout
        untracked = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
                                   capture_output=True, text=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    names = {line for line in (diff + untracked).splitlines() if line.strip()}
    return sorted(name for name in names if not any(ignored in name for ignored in IGNORED_FILES))


def _path_problem(name: str) -> str | None:
    """Ce qui interdit ce fichier dans une pull request de veille ; None s'il est autorisé (contenu seul)."""
    if any(ignored in name for ignored in IGNORED_FILES):
        return None
    if name.startswith((".github/", "docs/", "seo/", "news/", "suivi/", "worker/")):
        return f"{name} : dossier hors contenu (la routine n'y touche pas)"
    if name in (SOURCES_FILE, MODE_FILE, STOP_FILE) or (name.startswith(f"{VEILLE_DIR}/") and name != SEEN_FILE):
        return f"{name} : fichier de réglage de la veille (modifiable seulement par l'utilisateur)"
    if name.startswith(("blog-src/pages/", "blog-src/claims/")):
        return None
    if name in (SEEN_FILE, "sitemap.xml") or name.endswith(".html"):
        return None
    return f"{name} : fichier hors du périmètre d'un article"


def gate(root: Path = ROOT, files: list[str] | None = None, fetch: Callable[[str], tuple[int, str]] | None = None,
         today: date | None = None) -> tuple[list[str], list[str]]:
    """Le contrôle d'une pull request de veille ; rend (problèmes, notes). Un seul problème suffit à refuser.

    Sept points de la spec §7 : chemins autorisés, format du Blog (blog.py), sources de la liste blanche, extraits retrouvés
    (blog.check_sources), originalité, volume (3 articles par jour au plus) et interrupteur STOP.
    """
    problems: list[str] = []
    notes: list[str] = []
    if (root / STOP_FILE).is_file():
        return [f"{STOP_FILE} est présent : la veille est arrêtée, rien ne se fusionne"], notes
    sources = load_sources(root)
    allowed = whitelist(sources)
    files = files if files is not None else (changed_files(root) or [])
    for name in files:
        if problem := _path_problem(name):
            problems.append(problem)
    try:
        blog._verify(root)  # noqa: SLF001 — le même format que le Blog, sans dupliquer les règles
        pages = blog.load_pages(root)
    except blog.BlogError as error:
        return problems + error.problems, notes
    today = today or datetime.now(timezone.utc).astimezone(an.paris()).date()
    new_ids = _page_files(files) or [page["id"] for page in pages.values() if page["date"] == today.isoformat()]
    new_ids = [page_id for page_id in new_ids if page_id in pages]
    if not new_ids:
        return problems + ["aucun article dans cette pull request"], notes
    if len(new_ids) > MAX_PER_DAY:
        problems.append(f"{len(new_ids)} article(s) : {MAX_PER_DAY} au plus par jour")
    published_today = [page["id"] for page in pages.values() if page["date"] == today.isoformat()]
    if len(published_today) > MAX_PER_DAY:
        problems.append(f"{len(published_today)} article(s) datés du {today.isoformat()} dans le dépôt : {MAX_PER_DAY} au plus")
    used_before = {source["url"] for page in pages.values() if page["id"] not in new_ids for source in page.get("sources", [])}
    others = [shingles(_words(article_text(page))) for page in pages.values() if page["id"] not in new_ids]
    fetched: dict[str, tuple[int, str]] = {}
    get = fetch or blog.fetch_page

    def source_text(url: str) -> tuple[int, str]:
        if url not in fetched:
            status, body = get(url)
            fetched[url] = (status, blog.normalize(blog.visible_text(body)) if status == 200 else "")
        return fetched[url]

    for page_id in new_ids:
        page = pages[page_id]
        if page["kind"] not in KINDS:
            problems.append(f"{page_id} : kind « {page['kind']} » (un article de veille est release, news ou guide)")
        words = len(_words(article_text(page)))
        if not MIN_WORDS <= words <= MAX_WORDS:
            problems.append(f"{page_id} : {words} mots en anglais ({MIN_WORDS} à {MAX_WORDS} attendus)")
        if not 1 <= len(page["sections"]) <= 3:
            problems.append(f"{page_id} : {len(page['sections'])} section(s) (1 à 3 attendues)")
        if not 1 <= len(page["sources"]) <= 5:
            problems.append(f"{page_id} : {len(page['sources'])} source(s) (1 à 5 attendues)")
        for index, section in enumerate(page["sections"], start=1):
            counts = {lang: len((section.get(lang) or {}).get("text", [])) for lang in an.LANGS}
            if len(set(counts.values())) > 1:
                problems.append(f"{page_id} : section {index} : paragraphes désalignés entre langues "
                                f"({', '.join(f'{lang} {count}' for lang, count in counts.items())})")
            numbers = {lang: set(re.findall(r"\d+", " ".join((section.get(lang) or {}).get("text", [])))) for lang in an.LANGS}
            if len({frozenset(value) for value in numbers.values()}) > 1:
                problems.append(f"{page_id} : section {index} : les nombres diffèrent d'une langue à l'autre")
        outside = [source["url"] for source in page["sources"] if not domain_ok(source["url"], allowed)]
        if outside:
            problems.append(f"{page_id} : source hors liste blanche : {', '.join(outside)}")
        if not any(source["url"] not in used_before for source in page["sources"]):
            problems.append(f"{page_id} : toutes ses sources ont déjà servi à un autre article")
        own = shingles(_words(article_text(page)))
        for source in page["sources"]:
            if not domain_ok(source["url"], allowed):
                continue
            status, text = source_text(source["url"])
            if status != 200:
                problems.append(f"{page_id} : source {source['id']} ({source['url']}) : ne répond pas (HTTP {status})")
                continue
            run = longest_run(_words(article_text(page)), _words(text))
            if run > MAX_RUN:
                problems.append(f"{page_id} : {run} mots identiques d'affilée avec la source {source['id']} ({MAX_RUN} au plus)")
            part = overlap(own, shingles(_words(text)), SHINGLE)
            if part > MAX_OVERLAP_SOURCE:
                problems.append(f"{page_id} : {part:.0%} de suites de 5 mots reprises de la source {source['id']} "
                                f"({MAX_OVERLAP_SOURCE:.0%} au plus)")
        for index, other in enumerate(others):
            part = overlap(own, other, SHINGLE)
            if part > MAX_OVERLAP_PAGE:
                problems.append(f"{page_id} : {part:.0%} de ressemblance avec une page existante ({MAX_OVERLAP_PAGE:.0%} au plus)")
                break
    source_problems, manual = blog.check_sources(root, get, today)
    problems += [problem for problem in source_problems if problem.split(" :", 1)[0] in new_ids]
    notes += manual
    return problems, notes


def verifier(root: Path = ROOT) -> None:
    """Valide blog-src/veille/*.json (sources, seen, mode) ; lève VeilleError en listant tous les problèmes."""
    problems: list[str] = []
    try:
        load_sources(root)
        load_seen(root)
    except VeilleError as error:
        problems += error.problems
    mode_path = root / MODE_FILE
    if mode_path.is_file():
        try:
            mode = json.loads(mode_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(f"{MODE_FILE} : illisible : {error}")
        else:
            if not isinstance(mode, dict) or set(mode) != {"auto_from"}:
                problems.append(f'{MODE_FILE} : doit être {{"auto_from": null}} ou {{"auto_from": "AAAA-MM-JJ"}}')
            elif mode["auto_from"] is not None and not an.DATE.fullmatch(str(mode["auto_from"])):
                problems.append(f"{MODE_FILE} : auto_from doit être null ou une date AAAA-MM-JJ")
    if problems:
        raise VeilleError(problems)


# --- Ligne de commande --------------------------------------------------------------------------------------------

def _refuse(problems: list[str]) -> int:
    print(f"Refus : {len(problems)} problème(s)", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def main(argv: list[str], root: Path = ROOT, now: datetime | None = None,
         fetch: Callable[[str], tuple[int, str]] | None = None) -> int:
    """Ligne de commande (voir le haut du fichier) ; `fetch` remplace le réseau dans les tests."""
    if "--verifier" in argv:
        try:
            verifier(root)
        except VeilleError as error:
            return _refuse(error.problems)
        print("blog-src/veille : valide")
        return 0
    command = argv[0] if argv else ""
    try:
        if command == "collect":
            payload = collect(root, now, fetch)
            print(f"{len(payload['candidates'])} candidat(s) écrit(s) dans {CANDIDATES} "
                  f"({payload['elements_vus']} élément(s) vu(s), {len(payload['en_panne'])} source(s) en panne).")
            for problem in payload["en_panne"]:
                print(f"  - {problem}")
            return 0
        if command == "fetch":
            return fetch_command(argv[1:], root, fetch)
        if command == "seen":
            return seen_command(argv[1:], root)
        if command == "gate":
            files = None
            if "--fichiers" in argv:
                files = [name for name in argv[argv.index("--fichiers") + 1:] if name]
            today = date.fromisoformat(argv[argv.index("--jour") + 1]) if "--jour" in argv else None
            problems, notes = gate(root, files, fetch, today)
            for note in notes:
                print(f"Vérification manuelle : {note}")
            if problems:
                return _refuse(problems)
            print("Pull request de veille : conforme.")
            return 0
    except VeilleError as error:
        return _refuse(error.problems)
    except HorsListe as error:
        return _refuse([f"adresse hors liste blanche : {error}"])
    print("usage : veille.py collect | fetch <adresse> | seen <adresse>… | gate [--fichiers …] [--jour AAAA-MM-JJ] | --verifier",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
