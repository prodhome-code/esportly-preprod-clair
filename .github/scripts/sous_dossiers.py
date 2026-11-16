"""Passage des pages fr, es, de et pt-BR du site sous leur sous-dossier de langue (/fr/, /es/, /de/, /pt/), en une fois.

L'anglais reste à la racine ; les quatre autres langues gardent leurs chemins traduits sous leur dossier (/jeux/valorant devient
/fr/jeux/valorant, /live-fr devient /fr/live, /blog-es/valorant devient /es/blog/valorant). Les accueils, l'anglais (les pages
d'événements anglaises gardent leur suffixe : /worlds-2026-en), les pages de confirmation françaises (/merci, /verifie, /desinscrit,
/inscription-erreur : adresses des fonctions Supabase), en.html, match.html, tv-equipes.html, 404.html, les widgets, les images de
partage et les fiches JSON des équipes ne bougent pas. Chaque ancienne adresse redirige en 301 (_redirects). Les décisions B (adresse
nue pour l'anglais) et E (confirmations sous /fr/) de la spec, d'abord en ligne, ont été refusées par Johan le 1/11 et annulées.
Spécification : docs/superpowers/specs/2026-10-31-sous-dossiers-langues-design.md

    py -3.13 .github/scripts/sous_dossiers.py --essai   # montre ce qui changerait, sans rien écrire
    py -3.13 .github/scripts/sous_dossiers.py           # migre (refuse si c'est déjà fait)
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://esportly.eu/"
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "seo"}

# Pages à la racine qui changent de place : fichier → nouveau chemin (depuis la racine du site). Les familles à suffixe de langue
# (blog-fr, live-fr, worlds-2026-es…) perdent leur suffixe dans leur dossier ; les pages françaises sans suffixe (esl-pro-league,
# worlds-2026, vct-champions-2026) sont les originales du site ; leurs adresses nues redirigent vers /fr/… et l'anglais garde -en.
_SUFFIXED = ("blog", "live", "worlds-2026", "vct-champions-2026", "esl-pro-league")
_ROOT_PAGES = {
    "fr": ("accessibilite", "actualites", "blog-fr", "cgu", "confidentialite", "equipes", "esl-pro-league", "live-fr",
           "matchs-de-la-semaine", "mentions-legales", "nouveautes", "presse", "vct-champions-2026", "worlds-2026"),
    "es": ("accesibilidad", "blog-es", "esl-pro-league-es", "live-es", "noticias", "novedades", "partidos-de-la-semana", "prensa",
           "privacidad", "terminos", "vct-champions-2026-es", "worlds-2026-es"),
    "de": ("barrierefreiheit", "blog-de", "datenschutz", "esl-pro-league-de", "live-de", "nachrichten", "neuigkeiten",
           "nutzungsbedingungen", "pressebereich", "spiele-der-woche", "vct-champions-2026-de", "worlds-2026-de"),
    "pt": ("acessibilidade", "blog-pt", "esl-pro-league-pt", "imprensa", "live-pt", "novidades", "partidas-da-semana", "privacidade",
           "termos", "ultimas-noticias", "vct-champions-2026-pt", "worlds-2026-pt"),
}


def _target(lang: str, name: str) -> str:
    for family in _SUFFIXED:
        if name == f"{family}-{lang}":
            return f"{lang}/{family}.html"
    return f"{lang}/{name}.html"


ROOT_MOVES: dict[str, str] = {f"{name}.html": _target(lang, name) for lang, names in _ROOT_PAGES.items() for name in names}
# Adresses /fr/merci… envoyées par erreur entre le 1er et le 2 novembre 2026 (décision E annulée) : elles reviennent à la racine.
EXTRA_RULES = tuple(f"/fr/{name}{ext} /{name} 301" for name in ("merci", "verifie", "desinscrit", "inscription-erreur") for ext in ("", ".html"))
DIR_MOVES = {"jeux": "fr/jeux", "equipes": "fr/equipes", "blog-fr": "fr/blog", "juegos": "es/juegos", "blog-es": "es/blog",
             "spiele": "de/spiele", "blog-de": "de/blog", "jogos": "pt/jogos", "blog-pt": "pt/blog"}  # pages *.html seulement
XML_MOVES = {"nouveautes.xml": "fr/nouveautes.xml", "novedades.xml": "es/novedades.xml", "neuigkeiten.xml": "de/neuigkeiten.xml",
             "novidades.xml": "pt/novidades.xml"}


def public(path: str) -> str:
    """Adresse publiée (depuis la racine, sans .html) d'un fichier : « fr/blog/valorant.html » → « /fr/blog/valorant »."""
    if path == "index.html":
        return "/"
    return "/" + (path[:-5] if path.endswith(".html") else path)


def build_map(root: Path) -> dict[str, str]:
    """Ancien chemin → nouveau chemin de chaque fichier du site qui change de place (seuls ceux qui existent)."""
    mapping = {old: new for old, new in {**ROOT_MOVES, **XML_MOVES}.items() if (root / old).is_file()}
    for old_dir, new_dir in DIR_MOVES.items():
        for path in sorted((root / old_dir).glob("*.html")) if (root / old_dir).is_dir() else ():
            mapping[f"{old_dir}/{path.name}"] = f"{new_dir}/{path.name}"
    return mapping


ABSOLUTE = re.compile(r"(https(?::|%3A)//esportly\.eu/)([A-Za-z0-9._/-]*)")  # aussi encodée dans les liens de partage (https%3A//)
VISIT = re.compile(r"(visite\?p=)(/[A-Za-z0-9/_-]*)")
ATTRIBUTE = re.compile(r'((?:href|src)=")([^"]*)(")')
CSS_URL = re.compile(r"(url\()([^)\"']*)(\))")
QUOTED_PATH = re.compile(r"(')(/[A-Za-z0-9/_.-]+\.html)(')")  # analytics.js : page: '/confidentialite.html'


def _up(depth: int) -> str:
    return "../" * depth if depth else "./"


def rewrite(text: str, old_path: str, new_path: str, mapping: dict[str, str]) -> str:
    """Le texte d'un fichier (`old_path` → `new_path`, égaux s'il ne bouge pas) avec ses liens réécrits selon la carte : adresses
    absolues du site (avec ou sans .html), compteur de visites (visite?p=), href, src et url() relatifs ou depuis la racine.
    Un lien n'est touché que si la page ou sa cible change de place ; requête et fragment sont conservés. Un lien relatif réécrit
    prend la forme « depuis la racine » (« ../../fr/jeux/valorant.html » plutôt que « valorant.html ») : les générateurs renomment
    une page de modèle par son chemin entier (actualites.rename_page), qui doit donc figurer dans chaque lien de langue."""
    by_public = {public(old): public(new) for old, new in mapping.items()}
    old_dir, new_dir = posixpath.dirname(old_path), posixpath.dirname(new_path)
    moved = old_path != new_path

    def absolute(m: re.Match) -> str:
        site, path = m.group(1), m.group(2)
        if path.endswith((".html", ".xml")):
            return site + mapping.get(path, path)
        return site + by_public.get("/" + path, "/" + path).lstrip("/")

    def visit(m: re.Match) -> str:
        return m.group(1) + by_public.get(m.group(2), m.group(2))

    def link(value: str) -> str:
        path, hash_, fragment = value.partition("#")
        path, query_mark, query = path.partition("?")
        if not path or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", path):
            return value
        tail = query_mark + query + hash_ + fragment
        if path.startswith("/"):
            target = path[1:]
            return "/" + mapping[target] + tail if target in mapping else value
        resolved = posixpath.normpath(posixpath.join(old_dir, path))
        if resolved in (".", "") or path.endswith("/") and resolved == posixpath.normpath(old_dir or "."):
            return _up(new_dir.count("/") + 1 if new_dir else 0) + tail if moved else value
        if resolved not in mapping and not moved:
            return value
        if "/" not in path and old_dir and moved and posixpath.dirname(mapping.get(resolved, "")) == new_dir:
            return value  # lien nu entre deux pages d'un même dossier déplacé (« Autres jeux ») : il reste nu, comme les générateurs l'écrivent
        return ("../" * (new_dir.count("/") + 1) if new_dir else "") + mapping.get(resolved, resolved) + tail

    text = ATTRIBUTE.sub(lambda m: m.group(1) + link(m.group(2)) + m.group(3), text)
    text = CSS_URL.sub(lambda m: m.group(1) + link(m.group(2)) + m.group(3), text)
    text = QUOTED_PATH.sub(lambda m: m.group(1) + link(m.group(2)) + m.group(3), text)
    text = VISIT.sub(visit, text)
    return ABSOLUTE.sub(absolute, text)


class Refus(Exception):
    """Migration déjà faite (ou départ inattendu) : rien n'est écrit."""


def check_start_state(root: Path) -> None:
    if (root / "fr").is_dir():
        raise Refus("le dossier fr/ existe déjà : la migration semble déjà faite")
    if not (root / "live-fr.html").is_file():
        raise Refus("live-fr.html est introuvable : le départ n'est pas celui attendu")


def scope(root: Path) -> list[str]:
    """Les fichiers dont les liens sont réécrits : toutes les pages hors dossiers techniques (widgets compris), sitemap et flux XML
    de la racine, analytics.js."""
    found = [path.relative_to(root).as_posix() for path in sorted(root.rglob("*.html"))
             if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1])]
    found += [path.name for path in sorted(root.glob("*.xml"))]
    if (root / "analytics.js").is_file():
        found.append("analytics.js")
    return found


def redirects(mapping: dict[str, str]) -> str:
    """Le fichier _redirects (Workers Assets de Cloudflare) : une règle 301 par ancienne adresse publiée et par sa forme .html, une par
    flux XML, puis les jokers de secours des dossiers (sauf equipes, dont les fiches JSON restent en place), toujours en dernier."""
    lines = ["# Anciennes adresses des pages fr, es, de et pt-BR (sous-dossiers de langue depuis le 1er novembre 2026) : 301 vers la",
             "# nouvelle adresse. Écrit par .github/scripts/sous_dossiers.py ; les jokers des dossiers restent en dernier.", ""]
    taken = {public(new) for new in mapping.values()}  # une adresse qui devient celle d'une autre page (worlds-2026 : l'anglaise) ne redirige pas
    for old in sorted(mapping):
        new = public(mapping[old])
        if public(old) in taken:
            continue
        if old.endswith(".html"):
            lines += [f"{public(old)} {new} 301", f"/{old} {new} 301"]
        else:
            lines.append(f"/{old} /{mapping[old]} 301")
    lines += [*EXTRA_RULES, ""]
    lines += [f"/{old}/* /{new}/:splat 301" for old, new in DIR_MOVES.items() if old != "equipes"]
    return "\n".join(lines) + "\n"


def _lastmod(sitemap: str, loc: str, day: str) -> str:
    return re.sub(rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]*(</lastmod>)", lambda m: m.group(1) + day + m.group(2), sitemap, count=1)


def plan(root: Path, today) -> tuple[dict[str, bytes], list[str]]:
    """Ce que la migration écrit : {nouveau chemin: contenu} (fichiers déplacés ou dont un lien change, sitemap avec le lastmod du jour
    pour les pages déplacées, seo/titres.json aux clés renommées, _redirects) et la liste des anciens chemins à supprimer."""
    check_start_state(root)
    mapping = build_map(root)
    files: dict[str, bytes] = {}
    for old in scope(root):
        new = mapping.get(old, old)
        text = (root / old).read_bytes().decode("utf-8")
        out = rewrite(text, old, new, mapping)
        if old == "sitemap.xml":
            for moved_old, moved_new in mapping.items():
                if moved_old.endswith(".html"):
                    out = _lastmod(out, SITE + public(moved_new).lstrip("/"), today.isoformat())
        if new != old or out != text:
            files[new] = out.encode("utf-8")
    seo = root / "seo" / "titres.json"
    if seo.is_file():
        by_public = {public(old): public(new) for old, new in mapping.items()}
        raw = seo.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        renamed = {by_public.get(key, key): value for key, value in data.items()}
        if renamed != data:
            eol = "\r\n" if b"\r\n" in raw else "\n"  # les fins de ligne du fichier sont conservées
            files["seo/titres.json"] = (json.dumps(renamed, indent=1, ensure_ascii=False).replace("\n", eol) + eol).encode("utf-8")
    files["_redirects"] = redirects(mapping).encode("utf-8")
    return files, list(mapping)


def main(argv: list[str], root: Path = ROOT) -> int:
    try:
        files, removed = plan(root, date.today())
    except Refus as refus:
        print(f"Refus : {refus}", file=sys.stderr)
        return 1
    rules = sum(1 for line in files["_redirects"].decode("utf-8").splitlines() if line and not line.startswith("#"))
    print(f"{len(removed)} fichier(s) déplacé(s), {len(files) - 1} fichier(s) écrit(s) (déplacés et réécrits compris), {rules} règle(s) de redirection")
    if "--essai" in argv:
        return 0
    for old in removed:  # d'abord les anciens (worlds-2026.html : l'ancienne page française part, l'anglaise prend le nom)
        os.remove(root / old)
    for old in sorted({posixpath.dirname(old) for old in removed} - {""}, reverse=True):
        if (root / old).is_dir() and not any((root / old).iterdir()):
            (root / old).rmdir()
    for new, content in files.items():
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / new).write_bytes(content)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
