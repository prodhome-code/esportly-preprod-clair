"""Partie « News » du site : matchs importants et infos écrites à la main.

Lit news/news.json et les calendriers des grands événements, puis réécrit les 5 pages News, le bloc « News » des
5 accueils et le lastmod du sitemap. Lancé chaque matin par le job « Matchs du jour » (étape « Mise à jour des
news ») et à la main pour publier une info.
Spécification : docs/superpowers/specs/2026-10-27-news-design.md

    py -3.13 .github/scripts/actualites.py             # génère
    py -3.13 .github/scripts/actualites.py --essai     # dit ce qui changerait, sans rien écrire
    py -3.13 .github/scripts/actualites.py --verifier  # valide seulement news/news.json
"""
from __future__ import annotations

import base64
import functools
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import site_chrome

ROOT = Path(__file__).resolve().parents[2]
LANGS = ("fr", "en", "es", "de", "pt-BR")
# Chemins depuis la racine du site : les pages fr, es, de et pt-BR sont sous leur sous-dossier de langue (site_chrome.LANG_DIRS).
PAGES = {"fr": "fr/actualites.html", "en": "news.html", "es": "es/noticias.html", "de": "de/nachrichten.html", "pt-BR": "pt/ultimas-noticias.html"}
# La page « What's new » de chaque langue sert à la fois de modèle aux pages News et de cible du lien « whats-new ».
TEMPLATES = {"fr": "fr/nouveautes.html", "en": "whats-new.html", "es": "es/novedades.html", "de": "de/neuigkeiten.html", "pt-BR": "pt/novidades.html"}
WHATS_NEW = TEMPLATES
HOMES = site_chrome.HOMES
WEEKLY = {"fr": "fr/matchs-de-la-semaine.html", "en": "matches-this-week.html", "es": "es/partidos-de-la-semana.html",
          "de": "de/spiele-der-woche.html", "pt-BR": "pt/partidas-da-semana.html"}
EVENT_DIRS = site_chrome.LANG_DIRS  # la page d'un événement : <dossier de la langue><slug><suffixe>.html (fr/worlds-2026.html)
EVENT_SUFFIX = {"en": "-en"}  # l'anglais garde son suffixe : worlds-2026-en.html (l'adresse nue /worlds-2026, l'ancienne française, redirige vers /fr/)

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ITEM_KEYS = {"id", "date", "until", "pin", "link", "game", *LANGS}


# --- Adresses publiées ------------------------------------------------------------------------------------------
# Le Worker (assets sans html_handling : « auto-trailing-slash ») renvoie en 307 toute adresse en .html vers la même sans
# .html. Les adresses DÉCLARÉES (canonical, hreflang, og:url, <loc> et xhtml:link du sitemap, url / item / mainEntityOfPage /
# @id des données structurées) prennent donc la forme sans extension ; les liens de navigation (relatifs, en .html) ne
# changent pas. Ces trois fonctions sont recopiées telles quelles dans matchs.py (test_actualites le vérifie).

def public_url(path: str, site: str = "https://esportly.eu/") -> str:
    """Adresse publiée d'une page : « x.html » → site + « x », « index.html » → site, « dossier/index.html » → site + « dossier/ ».
    Accepte un chemin depuis la racine ou une adresse absolue du site ; garde le fragment. Une adresse avec « ? », d'un autre
    domaine ou d'un fichier non HTML est rendue telle quelle (un chemin devient absolu)."""
    address = path if "://" in path else site + path.lstrip("/")
    if not address.startswith(site) or "?" in address:
        return address
    address, hash_, fragment = address.partition("#")
    rest = address[len(site):]
    if rest == "index.html" or rest.endswith("/index.html"):
        rest = rest[:-len("index.html")]
    elif rest.endswith(".html"):
        rest = rest[:-len(".html")]
    return site + rest + hash_ + fragment


def public_urls(text: str, site: str = "https://esportly.eu/") -> str:
    """Les adresses déclarées d'une page ou d'un sitemap passent à leur forme publiée (public_url) ; rien d'autre ne change
    (ni les liens de navigation, ni les fins de ligne). Seules les adresses absolues du site sont touchées."""
    def convert(value: str) -> str:
        return public_url(value, site) if value.startswith(site) else value

    def tag(m: re.Match) -> str:
        found = m.group(0)
        if not ('rel="canonical"' in found or ('rel="alternate"' in found and "hreflang=" in found) or 'property="og:url"' in found):
            return found
        return re.sub(r'(?<=\s)(href|content)="([^"]*)"', lambda a: f'{a.group(1)}="{convert(a.group(2))}"', found)

    def json_ld(m: re.Match) -> str:
        return re.sub(r'("(?:url|item|mainEntityOfPage|@id)"\s*:\s*")([^"]*)(")',
                      lambda k: k.group(1) + convert(k.group(2)) + k.group(3), m.group(0))

    text = re.sub(r"<(?:link|xhtml:link|meta)\s[^>]*>", tag, text)
    text = re.sub(r"(?<=<loc>)[^<]*(?=</loc>)", lambda m: convert(m.group(0)), text)
    return re.sub(r'<script type="application/ld\+json">.*?</script>', json_ld, text, flags=re.S)


def rename_page(text: str, old: str, new: str, site: str = "https://esportly.eu/") -> str:
    """Une page d'un modèle devient une autre partout : liens (« old ») et adresse publiée (sans extension, suivie de " < ou #)."""
    text = text.replace(old, new)
    return re.sub(re.escape(public_url(old, site)) + r'(?=["<#])', lambda _: public_url(new, site), text)


class NewsError(Exception):
    """Fichier de news invalide : `problems` liste tout ce qui ne va pas, et rien n'est écrit."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def _parse_date(value) -> date | None:
    if not isinstance(value, str) or not DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _check_events(events: dict, site: Path, problems: list[str]) -> None:
    for slug, config in events.items():
        if not (site / page_for(slug, "en")).is_file():
            problems.append(f"events.{slug} : page {page_for(slug, 'en')} introuvable")
        if not isinstance(config, dict):
            problems.append(f"events.{slug} : doit être un objet avec « knockout_from »")
            continue
        problems += [f"events.{slug} : champ inconnu « {key} »" for key in config if key not in ("knockout_from", "game")]
        if "game" in config and config["game"] not in site_chrome.GAMES:
            problems.append(f"events.{slug}.game : « {config['game']} » n'est pas un jeu du site")
        if "knockout_from" not in config:
            problems.append(f"events.{slug}.knockout_from : manquant")
        elif config["knockout_from"] is not None and _parse_date(config["knockout_from"]) is None:
            problems.append(f"events.{slug}.knockout_from : « {config['knockout_from']} » n'est pas une date AAAA-MM-JJ ni null")


def _check_text(where: str, entry, problems: list[str]) -> None:
    if not isinstance(entry, dict):
        problems.append(f"{where} : doit être un objet avec « title » et « text »")
        return
    problems += [f"{where} : champ inconnu « {key} »" for key in entry if key not in ("title", "text")]
    for field, longest in (("title", 80), ("text", 280)):
        value = entry.get(field)
        if not isinstance(value, str):
            problems.append(f"{where}.{field} : manquant")
        elif not 1 <= len(value) <= longest:
            problems.append(f"{where}.{field} : {len(value)} caractères (1 à {longest} attendus)")
        elif "<" in value:
            problems.append(f"{where}.{field} : contient « < »")
        elif "\n" in value or "\r" in value:
            problems.append(f"{where}.{field} : contient un retour à la ligne")


def _check_link(where: str, link, events: dict, problems: list[str], site: Path) -> None:
    """`page` (page du site), `url` (adresse https) ou `blog` (identifiant d'un article de blog-src/pages, dont la page existe en 5 langues)."""
    if not isinstance(link, dict) or len(link) != 1 or not set(link) <= {"page", "url", "blog"}:
        problems.append(f"{where} : doit être {{\"page\": …}}, {{\"url\": …}} ou {{\"blog\": …}}")
    elif "blog" in link:
        article = link["blog"]
        if not isinstance(article, str) or not ID.match(article):
            problems.append(f"{where}.blog : « {article} » invalide")
        elif not (site / "blog-src" / "pages" / f"{article}.json").is_file():
            problems.append(f"{where}.blog : article « {article} » introuvable (blog-src/pages/{article}.json)")
    elif "page" in link:
        if link["page"] not in (*events, "weekly", "whats-new"):
            problems.append(f"{where} : page « {link['page']} » inconnue")
    elif not isinstance(link["url"], str) or not link["url"].startswith("https://") or re.search(r"\s", link["url"]):
        problems.append(f"{where} : l'adresse doit commencer par https:// et ne pas contenir d'espace")


def _check_item(index: int, entry, events: dict, seen: set, problems: list[str], site: Path) -> None:
    where = f"items[{index}]"
    if not isinstance(entry, dict):
        problems.append(f"{where} : doit être un objet")
        return
    problems += [f"{where} : champ inconnu « {key} »" for key in entry if key not in ITEM_KEYS]
    item_id = entry.get("id")
    if not isinstance(item_id, str) or not ID.match(item_id):
        problems.append(f"{where}.id : « {item_id} » invalide")
    elif item_id in seen:
        problems.append(f"{where}.id : « {item_id} » en double")
    else:
        seen.add(item_id)
    day = _parse_date(entry.get("date"))
    if day is None:
        problems.append(f"{where}.date : « {entry.get('date')} » n'est pas une date AAAA-MM-JJ")
    if "until" in entry:
        until = _parse_date(entry["until"])
        if until is None:
            problems.append(f"{where}.until : « {entry['until']} » n'est pas une date AAAA-MM-JJ")
        elif day is not None and until < day:
            problems.append(f"{where}.until : {entry['until']} est avant date {entry['date']}")
    if "game" in entry and entry["game"] not in site_chrome.GAMES:
        problems.append(f"{where}.game : « {entry['game']} » n'est pas un jeu du site")
    if "pin" in entry and not isinstance(entry["pin"], bool):
        problems.append(f"{where}.pin : doit être vrai ou faux")
    if "link" in entry:
        _check_link(f"{where}.link", entry["link"], events, problems, site)
    for lang in LANGS:
        if lang not in entry:
            problems.append(f"{where} : langue « {lang} » manquante")
        else:
            _check_text(f"{where}.{lang}", entry[lang], problems)


def load_news(path: Path, site: Path) -> dict:
    """Lit et valide news/news.json (§5 de la spec) ; lève NewsError avec tous les problèmes à la fois."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise NewsError([f"{path.name} illisible : {error}"])
    if not isinstance(data, dict):
        raise NewsError(["le premier niveau doit être un objet avec « events » et « items »"])
    problems = [f"clé inconnue « {key} » au premier niveau" for key in data if key not in ("events", "items")]
    events, items = data.get("events"), data.get("items")
    if not isinstance(events, dict):
        problems.append("« events » doit être un objet")
        events = {}
    if not isinstance(items, list):
        problems.append("« items » doit être une liste")
        items = []
    _check_events(events, site, problems)
    seen: set = set()
    for index, entry in enumerate(items):
        _check_item(index, entry, events, seen, problems, site)
    if problems:
        raise NewsError(problems)
    return data


def page_for(key: str, lang: str) -> str:
    """Nom du fichier de la page désignée par une clé `link.page`, dans la langue demandée."""
    if key == "weekly":
        return WEEKLY[lang]
    if key == "whats-new":
        return WHATS_NEW[lang]
    return f"{EVENT_DIRS[lang]}{key}{EVENT_SUFFIX.get(lang, '')}.html"


def visible_items(items: list[dict], today: date) -> list[dict]:
    """Infos à afficher aujourd'hui : publiées (date ≤ aujourd'hui), non expirées (until inclus), épinglées d'abord."""
    shown = [i for i in items
             if date.fromisoformat(i["date"]) <= today and ("until" not in i or date.fromisoformat(i["until"]) >= today)]
    return sorted(shown, key=lambda i: (not i.get("pin", False), -date.fromisoformat(i["date"]).toordinal(), i["id"]))


@functools.cache
def paris() -> ZoneInfo:
    """Fuseau de Paris, chargé à la première utilisation : `--verifier` marche même là où zoneinfo n'a pas de base des fuseaux."""
    return ZoneInfo("Europe/Paris")


API ="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/calendrier/"  # même base que matchs.py
STAGE = re.compile(r"\b(?:quarter|semi)?-?finals?\b", re.I)


def http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: " " if m.group(1) in "nN" else m.group(1), value)


def _parse_events(text: str) -> list[dict]:
    events, current = [], None
    for line in text.replace("\r\n ", "").replace("\n ", "").splitlines():  # lignes repliées recollées
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            try:
                start = datetime.strptime(current["DTSTART"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                start = None
            if start is not None:
                events.append({"summary": _unescape(current.get("SUMMARY", "")), "description": _unescape(current.get("DESCRIPTION", "")),
                               "url": current.get("URL", ""), "status": current.get("STATUS", ""), "start": start})
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";")[0]] = value
    return events


def read_events(slug: str, fetch: Callable[[str], str] = http_get) -> list[dict] | None:
    """Calendrier d'un événement ; None si le serveur ne répond pas après un second essai."""
    for _ in range(2):
        try:
            return _parse_events(fetch(f"{API}evenement/{slug}.ics"))
        except Exception as error:  # un événement indisponible ne bloque pas les autres
            print(f"{slug} : {error}")
    return None


def is_important(event: dict, knockout_from: date | None) -> bool:
    """Condition A (début, jour de Paris, à partir de knockout_from) ou B (titre qui indique une phase décisive)."""
    if knockout_from is not None and event["start"].astimezone(paris()).date() >= knockout_from:
        return True
    return bool(STAGE.search(event["summary"]))


def select_matches(calendars: dict[str, list[dict]], events: dict, now: datetime) -> list[dict]:
    """Matchs importants (A ou B) dans la fenêtre C : de now - 3 h à now + 14 jours, annulés écartés, triés par heure."""
    chosen = []
    for slug, calendar in calendars.items():
        knockout = _parse_date(events.get(slug, {}).get("knockout_from"))
        for event in calendar:
            if event["status"] == "CANCELLED" or not now - timedelta(hours=3) <= event["start"] <= now + timedelta(days=14):
                continue
            if is_important(event, knockout):
                chosen.append({**event, "slug": slug})
    return sorted(chosen, key=lambda m: (m["start"], m["slug"], m["summary"]))


# Noms de jours et de mois recopiés de LANGS dans matchs.py (à garder cohérents).
DAYS = {"fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "pt-BR": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]}
MONTHS = {"fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
          "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
          "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
          "pt-BR": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]}

# Libellés des pages et des blocs (tableaux de §7 et §8 de la spec).
LABELS = {
    "fr": dict(kicker="Actualités", title="Actualités et grands matchs",
               lead="Les matchs à ne pas manquer et les infos qui comptent, mises à jour au fil de l'eau.",
               cta="Être prévenu avant chaque match", matches="Matchs importants", infos="Dernières infos",
               no_match="Aucun match important dans les 14 prochains jours.", no_info="Aucune info pour l'instant.",
               more="En savoir plus", tz="heure de Paris", next_match="Prochain match important", all_news="Toutes les actualités →",
               read="Lire l'article →"),
    "en": dict(kicker="News", title="News and big matches",
               lead="The matches you can't miss and the news that matters, updated as they happen.",
               cta="Get alerted before every match", matches="Important matches", infos="Latest news",
               no_match="No important match in the next 14 days.", no_info="No news for now.",
               more="Learn more", tz="Paris time", next_match="Next big match", all_news="All news →", read="Read the article →"),
    "es": dict(kicker="Noticias", title="Noticias y grandes partidos",
               lead="Los partidos que no te puedes perder y las noticias que importan, al momento.",
               cta="Recibe un aviso antes de cada partido", matches="Partidos importantes", infos="Últimas noticias",
               no_match="Ningún partido importante en los próximos 14 días.", no_info="Sin noticias por ahora.",
               more="Saber más", tz="hora de París", next_match="Próximo partido importante", all_news="Todas las noticias →",
               read="Leer el artículo →"),
    "de": dict(kicker="Nachrichten", title="Nachrichten und große Matches",
               lead="Die Matches, die du nicht verpassen solltest, und die Neuigkeiten, die zählen, laufend aktualisiert.",
               cta="Vor jedem Match benachrichtigt werden", matches="Wichtige Matches", infos="Aktuelle Meldungen",
               no_match="Keine wichtigen Matches in den nächsten 14 Tagen.", no_info="Derzeit keine Meldungen.",
               more="Mehr erfahren", tz="Pariser Zeit", next_match="Nächstes wichtiges Match", all_news="Alle Nachrichten →",
               read="Artikel lesen →"),
    "pt-BR": dict(kicker="Notícias", title="Notícias e grandes partidas",
                  lead="As partidas imperdíveis e as notícias que importam, em tempo real.",
                  cta="Seja avisado antes de cada partida", matches="Partidas importantes", infos="Últimas notícias",
                  no_match="Nenhuma partida importante nos próximos 14 dias.", no_info="Nenhuma notícia por enquanto.",
                  more="Saiba mais", tz="horário de Paris", next_match="Próxima partida importante", all_news="Todas as notícias →",
                  read="Ler o artigo →"),
}

# Style des listes d'infos et du bloc de l'accueil, avec les variables de thème du site (une règle par ligne).
INFOS_STYLE = "\n".join([
    ".infos{list-style:none;margin:0;padding:0;display:grid;gap:10px}",
    ".infos li{padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}",
    ".infos time{display:block;font-size:14px;color:var(--soft);font-weight:600}",
    ".infos h3{margin:4px 0;font:700 22px var(--display);color:var(--text)}",
    ".infos p{margin:0 0 6px;color:var(--soft)}",
    ".infos a{font-weight:600}",
    ".infos li.match a{display:grid;gap:2px;text-decoration:none;color:var(--text)}",
    ".infos li.match small{font-size:13px;color:var(--soft);text-transform:uppercase;letter-spacing:.04em}",
    ".infos li.match time{color:var(--or)}",
    ".infos li.match b{font-size:18px}",
    ".news .more{margin:14px 0 0}",
])


def day_label(day: date, lang: str, weekday: bool) -> str:
    """« samedi 14 novembre » (avec weekday, comme les pages de matchs) ou « 14 novembre 2026 »."""
    if weekday:
        return f"{DAYS[lang][day.weekday()]} {day.day} {MONTHS[lang][day.month - 1]}"
    return f"{day.day} {MONTHS[lang][day.month - 1]} {day.year}"


def _when(start: datetime, lang: str) -> str:
    local = start.astimezone(paris())
    return f"{day_label(local.date(), lang, True)}, {local:%H:%M}"


def _data_game(game: str | None) -> str:
    """L'attribut data-game d'un élément lié à un jeu (le filtre par jeu), rien pour une info générale."""
    return f' data-game="{game}"' if game else ""


def render_matches(matches: list[dict], lang: str, games: dict[str, str] | None = None) -> str:
    """La liste des matchs importants ; `games` : événement (slug) → jeu, pour le filtre par jeu (data-game)."""
    labels, games = LABELS[lang], games or {}
    if not matches:
        return f'<p>{labels["no_match"]}</p>'
    items = "".join(f'<li{_data_game(games.get(m.get("slug")))}><a href="{html.escape(m["url"])}" target="_top"><time datetime="{m["start"].isoformat()}">{html.escape(_when(m["start"], lang))}</time>'
                    f'<b>{html.escape(m["summary"])}</b><small>{html.escape(m["description"])}</small></a></li>' for m in matches)
    return f'<ul class="matchs">{items}</ul><p class="maj">{labels["tz"]}</p>'


def _info_li(entry: dict, lang: str, with_id: bool, prefix: str) -> str:
    """`prefix` : ce qui précède un chemin depuis la racine, vu de la page qui montre l'info (site_chrome.prefix_for)."""
    texts = entry[lang]
    attr = f' id="{html.escape(entry["id"])}"' if with_id else ""
    link = ""
    if "link" in entry:
        label = LABELS[lang]["more"]
        if "blog" in entry["link"]:  # l'article de la news, une page du Blog
            href, rel, label = f'{prefix}{site_chrome.BLOG_DIRS[lang]}/{entry["link"]["blog"]}.html', "", LABELS[lang]["read"]
        elif "page" in entry["link"]:
            href, rel = prefix + page_for(entry["link"]["page"], lang), ""
        else:
            href, rel = entry["link"]["url"], ' rel="noopener"'
        link = f'<p><a href="{html.escape(href)}"{rel}>{label}</a></p>'
    label = day_label(date.fromisoformat(entry["date"]), lang, False)
    return (f'<li{attr}{_data_game(entry.get("game"))}><time datetime="{entry["date"]}">{label}</time><h3>{html.escape(texts["title"])}</h3>'
            f'<p>{html.escape(texts["text"])}</p>{link}</li>')


def render_infos(items: list[dict], lang: str, limit: int = 20) -> str:
    """La liste des infos de la page News de la langue (PAGES[lang], d'où ses liens sont vus)."""
    if not items:
        return f'<p>{LABELS[lang]["no_info"]}</p>'
    prefix = site_chrome.prefix_for(PAGES[lang])
    return '<ul class="infos">' + "".join(_info_li(i, lang, True, prefix) for i in items[:limit]) + "</ul>"


def render_jsonld(matches: list[dict]) -> str:
    """Données structurées SportsEvent des matchs, dans la forme des pages de matchs ; « </ » y est neutralisé."""
    if not matches:
        return ""
    entries = []
    for m in matches:
        names = [n.strip() for n in m["summary"].split("–")]
        entry = {"@context": "https://schema.org", "@type": "SportsEvent", "name": m["summary"], "startDate": m["start"].isoformat(),
                 "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
                 "location": {"@type": "VirtualLocation", "url": m["url"]}, "description": m["description"], "url": m["url"]}
        if len(names) == 2:
            entry["competitor"] = [{"@type": "SportsTeam", "name": n} for n in names]
        entries.append(entry)
    return '<script type="application/ld+json">' + json.dumps(entries, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def _match_li(next_match: dict | None, lang: str) -> str:
    if next_match is None:
        return ""
    labels = LABELS[lang]
    return (
        f'<li class="match"><a href="{html.escape(next_match["url"])}" target="_top"><small>{labels["next_match"]}</small>'
        f'<time datetime="{next_match["start"].isoformat()}">{html.escape(_when(next_match["start"], lang))}</time>'
        f'<b>{html.escape(next_match["summary"])}</b></a></li>')


def _home_block(items: list[dict], match_li: str, lang: str) -> str:
    shown = items[:3]
    if not shown and not match_li:
        return ""
    labels = LABELS[lang]
    infos = "".join(_info_li(i, lang, False, "") for i in shown)  # l'accueil est à la racine
    return (f'<section class="block news" id="news"><div class="wrap"><h2>{labels["kicker"]}</h2><ul class="infos">{infos}'
            f'<!-- prochain-match -->{match_li}<!-- /prochain-match --></ul>'
            f'<p class="more"><a href="{PAGES[lang]}">{labels["all_news"]}</a></p></div></section>')


def render_home_block(items: list[dict], next_match: dict | None, lang: str) -> str:
    """Bloc « News » de l'accueil : 3 infos au plus, la ligne du prochain match important, le lien vers la page ; vide s'il n'y a rien."""
    return _home_block(items, _match_li(next_match, lang), lang)


# --- Bandeau de l'accueil (alimenté par les veilles) ---------------------------------
# Hiérarchie : match important en direct > prochain match important > actu la plus récente >
# bandeau App Store (repli). Le fond doré glisse et le point « en direct » clignote (bandeau.css).
STORE = "https://apps.apple.com/app/apple-store/id6819243569?pt=127103293&ct=site_esportly&mt=8"
BANDEAU_LINK = '<link rel="stylesheet" href="/bandeau.css">'
HELLO_RE = re.compile(r'<div class="hello[^"]*">.*?</div>', re.S)
LIVE_HOURS = 3  # un match commencé il y a moins de 3 h est « en direct » (le calendrier donne le début, pas la fin)
BANDEAU_TEXT = {
    "fr": dict(live="En direct", next="Prochain grand match", news="À la une",
               store="eSportly est disponible sur l'App Store", cta="Télécharge-la gratuitement →",
               qr_title="Regarde ce match sur eSportly, télécharge l'app"),
    "en": dict(live="Live now", next="Next big match", news="Top story",
               store="eSportly is out on the App Store", cta="Download it for free →",
               qr_title="Watch this match on eSportly, download the app"),
    "es": dict(live="En directo", next="Próximo gran partido", news="A la una",
               store="eSportly ya está en el App Store", cta="Descárgala gratis →",
               qr_title="Mira este partido en eSportly, descarga la app"),
    "de": dict(live="Live", next="Nächstes großes Match", news="Top-Thema",
               store="eSportly ist jetzt im App Store", cta="Kostenlos laden →",
               qr_title="Sieh dir dieses Match auf eSportly an, lade die App herunter"),
    "pt-BR": dict(live="Ao vivo", next="Próxima grande partida", news="Em destaque",
                  store="O eSportly chegou à App Store", cta="Baixe grátis →",
                  qr_title="Assista a esta partida no eSportly, baixe o app"),
}


def render_bandeau(matches: list[dict], items: list[dict], lang: str, now: datetime) -> str:
    """Le bandeau de l'accueil : match en direct, sinon prochain match, sinon actu, sinon App Store."""
    t = BANDEAU_TEXT[lang]
    for m in matches:
        if m["start"] <= now < m["start"] + timedelta(hours=LIVE_HOURS):
            return (f'<div class="hello bandeau"><a href="{STORE}" class="bandeau-qr" '
                    f'data-qr-title="{html.escape(t["qr_title"])}">'
                    f'<span class="b-live">{t["live"]}</span><b>{html.escape(m["summary"])}</b>'
                    f'<span> · <time datetime="{html.escape(m["start"].isoformat())}">'
                    f'{html.escape(_when(m["start"], lang))}</time> →</span></a></div>')
    for m in matches:
        if m["start"] > now:
            return (f'<div class="hello bandeau"><a href="{STORE}" class="bandeau-qr" '
                    f'data-qr-title="{html.escape(t["qr_title"])}">'
                    f'<span class="b-tag">{t["next"]}</span><b>{html.escape(m["summary"])}</b>'
                    f'<span> · <time datetime="{html.escape(m["start"].isoformat())}">'
                    f'{html.escape(_when(m["start"], lang))}</time> →</span></a></div>')
    if items:
        entry, href = items[0], "https://esportly.eu/"
        if "link" in entry:
            if "blog" in entry["link"]:
                href = f'/{site_chrome.BLOG_DIRS[lang]}/{entry["link"]["blog"]}.html'
            elif "page" in entry["link"]:
                href = "/" + page_for(entry["link"]["page"], lang)
            elif "url" in entry["link"]:
                href = entry["link"]["url"]
        return (f'<div class="hello bandeau"><a href="{html.escape(href)}">'
                f'<span class="b-tag">{t["news"]}</span><b>{html.escape(entry[lang]["title"])}</b></a></div>')
    return (f'<div class="hello bandeau"><a href="{STORE}"><b>{t["store"]}</b>'
            f'<span> · {t["cta"]}</span></a></div>')


def with_bandeau(page: str, bandeau: str) -> str:
    """Remplace le bandeau « hello » de l'accueil par celui du jour, et charge sa feuille de style."""
    page = HELLO_RE.sub(lambda _: bandeau, page, count=1)
    if BANDEAU_LINK not in page:
        page = page.replace(bandeau, BANDEAU_LINK + bandeau, 1)
    return page



# Recopié à l'identique de matchs.py (STYLE, LOCAL_JS, LOCAL_HASH, LOCAL_STYLE, with_local_times) : à garder identique.
STYLE = (".matchs{list-style:none;padding:0;margin:0;display:grid;gap:10px}"
         ".matchs a{display:grid;gap:2px;padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border);color:var(--text);text-decoration:none}"
         ".matchs time{font-size:15px;color:var(--or);font-weight:700}.matchs b{font-size:18px}.matchs small{font-size:14px;color:var(--soft)}"
         ".jour{font:700 26px var(--display);margin:30px 0 12px}.maj{font-size:14px;color:var(--muted)}"
         ".resultats{list-style:none;padding:0;margin:0;display:grid;gap:10px}.resultats details{padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}"
         ".resultats summary{display:grid;gap:2px;cursor:pointer;list-style:none}.resultats summary::-webkit-details-marker{display:none}.resultats summary b{font-size:18px}"
         ".resultats small{font-size:14px;color:var(--soft)}.resultats .voir{font-size:14px;font-weight:700;color:var(--text);text-decoration:underline}"
         ".resultats details[open] .voir{display:none}.score{margin:10px 0 0;font-size:18px;user-select:none}.score b{font:700 26px var(--display);margin:0 8px}"
         ".resultats summary .score{margin:10px 0 6px}"
         # Le score est flouté par son style en ligne ; l'ouverture le révèle (!important l'emporte sur le style en ligne).
         ".resultats details[open] .score{filter:none!important;user-select:auto}"
         ".evts{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}.evts a{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:999px;background:var(--surface);border:1px solid var(--border);color:var(--text);text-decoration:none;font-weight:600;font-size:15px}"
         ".cal-buttons{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.cal-google{display:inline-flex;align-items:center;min-height:54px;padding:0 24px;border-radius:999px;border:1px solid var(--border);color:var(--text);font-weight:700;text-decoration:none}")
LOCAL_JS = ("(function(){var d=document,h=d.documentElement,l=(h.lang||'fr').slice(0,2),"
            "w={fr:'chez toi',en:'your time',es:'tu hora',de:'deine Zeit',pt:'seu horário'}[l]||'your time',"
            "t=d.querySelectorAll('.matchs time[datetime]'),P='Europe/Paris';"
            "for(var i=0;i<t.length;i++){var x=new Date(t[i].getAttribute('datetime'));if(isNaN(x))continue;"
            "try{var o={hour:'2-digit',minute:'2-digit'},k=function(z){return new Intl.DateTimeFormat('en-CA',"
            "{timeZone:z,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(x)},"
            "a=k(P),b=k(undefined);if(a===b)continue;if(a.slice(0,10)!==b.slice(0,10))o.weekday='short';"
            "var s=d.createElement('span');s.className='loc';s.textContent=new Intl.DateTimeFormat(h.lang||'fr',o).format(x)+' '+w;"
            "t[i].insertAdjacentElement('afterend',s)}catch(e){}}})();")
LOCAL_HASH = base64.b64encode(hashlib.sha256(LOCAL_JS.encode("utf-8")).digest()).decode()
LOCAL_STYLE = ".matchs .loc{font-size:14px;color:var(--soft);font-weight:600}"


def with_local_times(page: str) -> str:
    """Ajoute (une fois) le script de l'heure locale, son empreinte dans la CSP et son style."""
    if LOCAL_JS not in page:
        page = re.sub(r"<script>\(function\(\)\{var d=document,h=d\.documentElement,l=.*?</script>\n?", "", page, flags=re.S)
        page = page.replace("</body>", f"<script>{LOCAL_JS}</script>\n</body>", 1)
    if f"'sha256-{LOCAL_HASH}'" not in page:
        page = re.sub(r"(script-src [^;\"]*)", lambda m: m.group(1) + f" 'sha256-{LOCAL_HASH}'", page, count=1)
    if ".matchs .loc{" not in page:
        page = page.replace("</style>", LOCAL_STYLE + "</style>", 1)
    return page


def render_page(lang: str, template: str, matches_html: str, infos_html: str, jsonld: str, home_page: str,
                names: dict[str, str] | None = None, seo: dict[str, dict[str, str]] | None = None) -> str:
    """Page News d'une langue, fabriquée comme les pages de matchs de la semaine à partir de la page « What's new », avec le menu
    et le pied de page des accueils (site_chrome.with_chrome ; `home_page` est l'accueil de la langue, d'où vient le pied de page).
    <title>, description et og:* viennent de `seo` (site_chrome.seo_texts) quand la page y est, sinon de LABELS ; le H1 reste LABELS.
    Lève NewsError si le modèle ou l'accueil n'a pas ce qu'il faut pour les recevoir."""
    labels = LABELS[lang]
    page = template
    for other, name in TEMPLATES.items():  # liens de langue, canonical et hreflang : vers les 5 pages News
        page = rename_page(page, name, PAGES[other])
    page = public_urls(page)
    page = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\r?\n?', "", page)
    title, lead = (html.escape(s) for s in site_chrome.seo(seo or {}, PAGES[lang], labels["title"], labels["lead"]))
    page = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title}</title>", page, flags=re.S)
    page = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + lead, page)
    page = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + title, page)
    page = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + lead, page)
    slug, prefix = PAGES[lang][:-5], site_chrome.prefix_for(PAGES[lang])
    page = re.sub(r"(visite\?p=/)[a-z/-]+", lambda m: m.group(1) + slug, page)
    hero = (f'<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{labels["kicker"]}</div>'
            f'<h1>{labels["title"]}</h1><p class="lead">{html.escape(labels["lead"])}</p>'
            f'<a class="cta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{slug}&amp;go=testflight">{labels["cta"]}</a></section>')
    games = re.findall(r'data-game="([a-z0-9-]+)"', matches_html + infos_html)  # les jeux dont il y a quelque chose à voir
    # Les dernières infos d'abord (c'est ce que le robot de la semaine met à jour), puis les matchs importants, puis les données structurées.
    main = (hero + site_chrome.render_filter(lang, games, names or {}) + f'<h2 class="jour">{labels["infos"]}</h2>{infos_html}'
            f'<h2 class="jour">{labels["matches"]}</h2><!-- matchs-importants -->{matches_html}<!-- /matchs-importants -->{jsonld}')
    page = re.sub(r'<main class="wrap">.*?</main>', lambda _: f'<main class="wrap">{main}</main>', page, flags=re.S)
    eol = "\r\n" if "\r\n" in page else "\n"
    if ".matchs{" not in page:
        page = page.replace("</style>", STYLE + "</style>", 1)
    if ".infos{" not in page:
        page = page.replace("</style>", INFOS_STYLE.replace("\n", eol) + eol + "</style>", 1)
    try:
        return site_chrome.with_chrome(page, lang, home_page, HOMES[lang], prefix, slug, home=site_chrome.home_link(lang, prefix),
                                       news=prefix + PAGES[lang], hub=prefix + site_chrome.HUBS[lang], label=site_chrome.BLOG_LABEL,
                                       current="news", live=prefix + site_chrome.LIVE_PAGES[lang])
    except site_chrome.ChromeError as error:
        raise NewsError([f"{PAGES[lang]} : {problem}" for problem in error.problems]) from None


def update_between(page: str, start: str, end: str, content: str, name: str) -> str:
    """Remplace ce qui est entre deux marqueurs ; lève NewsError si l'un des deux manque (jamais de saut silencieux)."""
    first = page.find(start)
    last = page.find(end, first + len(start)) if first >= 0 else -1
    if first < 0 or last < 0:
        raise NewsError([f"{name} : marqueurs {start} … {end} introuvables"])
    return page[:first + len(start)] + content + page[last:]


def extract_between(page: str, start: str, end: str) -> str | None:
    """Contenu entre deux marqueurs, ou None s'ils manquent (sert à reprendre la veille)."""
    first = page.find(start)
    last = page.find(end, first + len(start)) if first >= 0 else -1
    return None if first < 0 or last < 0 else page[first + len(start):last]


def set_lastmod(sitemap: str, loc: str, day: str) -> str:
    """Met à jour le lastmod de l'entrée d'une page, sans toucher au reste (fins de ligne comprises)."""
    pattern = re.compile(rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]*(</lastmod>)")
    if not pattern.search(sitemap):
        raise NewsError([f"sitemap.xml : entrée {loc} introuvable"])
    return pattern.sub(lambda m: m.group(1) + day + m.group(2), sitemap, count=1)


MATCHES_MARKERS = ("<!-- matchs-importants -->", "<!-- /matchs-importants -->")
NEXT_MATCH_MARKERS = ("<!-- prochain-match -->", "<!-- /prochain-match -->")
HOME_MARKERS = ("<!-- news-accueil -->", "<!-- /news-accueil -->")
JSON_LD = re.compile(r'<script type="application/ld\+json">.*?</script>', re.S)


def _read(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def _required(root: Path, name: str, why: str) -> str:
    content = _read(root / name)
    if content is None:
        raise NewsError([f"{name} introuvable ({why})"])
    return content


def same_eol(page: str, template: str) -> str:
    """with_local_times (copie de matchs.py) ajoute un « \\n » : on l'aligne sur les fins de ligne du modèle (CRLF en local)."""
    return re.sub(r"(?<!\r)\n", "\r\n", page) if "\r\n" in template else page


def generate(root: Path, now: datetime, fetch: Callable[[str], str] = http_get) -> dict[str, str]:
    """Calcule en mémoire les 5 pages News, le bloc des 5 accueils et le sitemap ; rend seulement les fichiers qui changent.

    Si un calendrier est indisponible, la partie « matchs importants » des pages et la ligne de l'accueil gardent la veille.
    """
    data = load_news(root / "news" / "news.json", root)
    events = data["events"]
    today = now.astimezone(paris()).date()
    items = visible_items(data["items"], today)
    calendars = {slug: read_events(slug, fetch) for slug in events}
    games = {slug: config["game"] for slug, config in events.items() if "game" in config}  # événement → jeu (filtre par jeu)
    names, seo = site_chrome.read_game_names(root), site_chrome.seo_texts(root)
    outage = any(calendar is None for calendar in calendars.values())
    matches = [] if outage else select_matches(calendars, events, now)
    sitemap = _required(root, "sitemap.xml", "lastmod des pages News")
    new_sitemap, changes = sitemap, {}
    for lang in LANGS:
        name, old = PAGES[lang], _read(root / PAGES[lang])
        template = _required(root, TEMPLATES[lang], f"modèle de {name}")
        home_name = HOMES[lang]
        home = _required(root, home_name, "accueil")
        matches_html, jsonld = render_matches(matches, lang, games), render_jsonld(matches)
        if outage and old is not None:
            kept = extract_between(old, *MATCHES_MARKERS)
            found = JSON_LD.search(old)
            matches_html = render_matches([], lang) if kept is None else kept
            jsonld = found.group(0) if found else ""
        page = same_eol(with_local_times(render_page(lang, template, matches_html, render_infos(items, lang), jsonld, home, names[lang], seo)), template)
        if page != old:
            changes[name] = page
            new_sitemap = set_lastmod(new_sitemap, public_url(name), today.isoformat())
        if outage:
            block = _home_block(items, extract_between(home, *NEXT_MATCH_MARKERS) or "", lang)
        else:
            block = render_home_block(items, matches[0] if matches else None, lang)
        new_home = with_bandeau(update_between(home, *HOME_MARKERS, block, home_name),
                                render_bandeau(matches, items, lang, now))
        if new_home != home:
            changes[home_name] = new_home
    if new_sitemap != sitemap:
        changes["sitemap.xml"] = new_sitemap
    return changes


def main(argv: list[str], root: Path = ROOT, now: datetime | None = None, fetch: Callable[[str], str] = http_get) -> int:
    trial = "--essai" in argv
    try:
        if "--verifier" in argv:
            load_news(root / "news" / "news.json", root)
            print("news/news.json : valide")
            return 0
        changes = generate(root, now or datetime.now(timezone.utc), fetch)
    except NewsError as error:
        print(f"Refus : {len(error.problems)} problème(s)", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if not trial:
        for name, content in changes.items():
            (root / name).write_text(content, encoding="utf-8", newline="")
    print(f"{len(changes)} fichier(s) {'à changer' if trial else 'changé(s)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
