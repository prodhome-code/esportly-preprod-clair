#!/usr/bin/env python3
"""Flux du blog : `blog/articles.json` et les `feed.xml` (RSS 2.0) de chaque langue.

Les pages du blog vivent dans `blog-src/pages/*.json` (lues et validées par `blog.py`).
Ce script ne régénère pas les pages : il produit ce que **l'app iOS** et les lecteurs de
flux consomment — une liste d'articles en JSON (titre et résumé dans les 5 langues) et un
flux RSS par langue.

    python3 .github/scripts/blog_feed.py [--verifier]

`--verifier` n'écrit rien : il contrôle que les fichiers publiés sont à jour et sort en
erreur sinon (utile dans le contrôle de la CI).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import blog  # noqa: E402  (même dossier)

SITE = "https://esportly.eu"
# La langue de la page d'accueil du blog est l'anglais ; les autres vivent sous /<lang>/blog/.
LANGUES = {"en": "", "fr": "fr/", "es": "es/", "de": "de/", "pt-BR": "pt/"}
LANGUE_DU_FLUX = "en"


def url_page(page_id: str, langue: str) -> str:
    return f"{SITE}/{LANGUES.get(langue, '')}blog/{page_id}"


def url_image(page: dict) -> str:
    """L'illustration de l'article, telle que le site la sert (couvertures par jeu)."""
    image = page.get("image") or {}
    fichier = image.get("file") or page.get("game") or "esportly"
    return f"{SITE}/couvertures/{fichier}.webp"


def article(page: dict) -> dict:
    """Un article prêt pour l'app : toutes ses langues, sa date, son jeu, son adresse."""
    traductions = {}
    for langue in LANGUES:
        data = page.get(langue) or {}
        if data.get("title"):
            traductions[langue] = {
                "title": data["title"],
                "description": data.get("description") or "",
                "url": url_page(page["id"], langue),
            }
    return {
        "id": page["id"],
        "kind": page.get("kind"),
        "game": page.get("game"),
        "date": page["date"],
        "updated": page.get("updated") or page["date"],
        "image": url_image(page),
        "translations": traductions,
    }


def trier(pages: list[dict]) -> list[dict]:
    """Le plus récent d'abord ; à date égale, l'identifiant décide (résultat stable)."""
    return sorted(pages, key=lambda p: (-date.fromisoformat(p["date"]).toordinal(), p["id"]))


def flux(pages: list[dict], langue: str) -> str:
    lignes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>eSportly — {'le blog' if langue == 'fr' else 'the blog'}</title>",
        f"    <link>{SITE}/{LANGUES[langue]}blog</link>",
        f"    <atom:link href=\"{SITE}/{LANGUES[langue]}blog/feed.xml\" rel=\"self\" type=\"application/rss+xml\" />",
        f"    <description>{escape('Les nouveautés de l’app, les coulisses et les conseils d’usage.' if langue == 'fr' else 'App news, behind the scenes and tips.')}</description>",
        f"    <language>{langue}</language>",
    ]
    for page in pages:
        data = page.get(langue) or {}
        if not data.get("title"):
            continue
        lien = url_page(page["id"], langue)
        lignes += [
            "    <item>",
            f"      <title>{escape(data['title'])}</title>",
            f"      <link>{lien}</link>",
            f'      <guid isPermaLink="true">{lien}</guid>',
            f"      <description>{escape(data.get('description') or '')}</description>",
            f"      <pubDate>{date.fromisoformat(page['date']).strftime('%a, %d %b %Y 00:00:00 +0100')}</pubDate>",
            f'      <category>{escape(page.get("game") or "esportly")}</category>',
            "    </item>",
        ]
    lignes += ["  </channel>", "</rss>", ""]
    return "\n".join(lignes)


def main() -> int:
    verifier = "--verifier" in sys.argv
    pages = trier(blog.visible_pages(blog.load_pages(RACINE), date.today()))

    a_ecrire: dict[Path, str] = {
        RACINE / "blog" / "articles.json": json.dumps(
            {"updated": date.today().isoformat(), "articles": [article(p) for p in pages]},
            ensure_ascii=False, indent=2) + "\n",
    }
    for langue, prefixe in LANGUES.items():
        dossier = RACINE / prefixe / "blog" if prefixe else RACINE / "blog"
        a_ecrire[dossier / "feed.xml"] = flux(pages, langue)

    perimes = []
    for chemin, contenu in a_ecrire.items():
        actuel = chemin.read_text(encoding="utf-8") if chemin.exists() else None
        if actuel == contenu:
            continue
        if verifier:
            perimes.append(str(chemin.relative_to(RACINE)))
            continue
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
        print(f"écrit : {chemin.relative_to(RACINE)}")

    if perimes:
        print("à régénérer (python3 .github/scripts/blog_feed.py) : " + ", ".join(perimes), file=sys.stderr)
        return 1
    print(f"{len(pages)} article(s) dans le flux")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
