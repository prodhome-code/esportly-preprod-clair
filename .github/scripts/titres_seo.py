"""Titles et métadescriptions SEO de toutes les pages du site, d'après seo/titres.json (skill titres-seo).

Pour chaque page du fichier (clé : chemin public, « /jeux/valorant » → jeux/valorant.html), le <title>, la <meta name="description">,
og:title et og:description deviennent ceux du fichier, et le nom de la page dans ses données structurées WebPage (pages d'équipes) suit
le title. Le H1 et le reste de la page ne bougent pas. Les pages fabriquées par les scripts (Blog, News, semaine, événements, Live)
lisent déjà ce fichier à la fabrication (site_chrome.seo) : ici elles ne changent pas. Le script est rejouable sans effet : une page
déjà en règle n'est pas touchée. Il est lancé à la fin des tâches planifiées (matchs.yml), pour qu'une page de jeu ou d'équipe recopiée
d'ailleurs reçoive son title.

Lancé à la main : python3 .github/scripts/titres_seo.py   (ajouter --check pour seulement lister les pages à mettre à jour).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import site_chrome

ROOT = Path(__file__).resolve().parents[2]
TITLE = re.compile(r"<title>.*?</title>", re.S)
META = {field: re.compile(rf'(<meta {field} content=")[^"]*') for field in
        ('name="description"', 'property="og:title"', 'property="og:description"')}
WEBPAGE_NAME = re.compile(r'("@type": "WebPage", "name": ")(?:[^"\\]|\\.)*(")')


def retitle(page: str, title: str, description: str) -> str:
    """La page avec ce title et cette description (balises du <head> et nom WebPage des données structurées)."""
    head, meta = html.escape(title), html.escape(description)
    page = TITLE.sub(lambda _: f"<title>{head}</title>", page, count=1)
    for field, value in ((META['name="description"'], meta), (META['property="og:title"'], head), (META['property="og:description"'], meta)):
        page = field.sub(lambda m, value=value: m.group(1) + value, page, count=1)
    return WEBPAGE_NAME.sub(lambda m: m.group(1) + json.dumps(title, ensure_ascii=False)[1:-1] + m.group(2), page, count=1)


def apply(root: Path, write: bool = True) -> tuple[list[str], list[str]]:
    """Applique seo/titres.json aux pages de `root` : (pages changées, pages introuvables). Sans `write`, ne fait que compter."""
    changed, missing = [], []
    for key, texts in site_chrome.seo_texts(root).items():
        name = key.removeprefix("/") + ".html" if key != "/" else "index.html"
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        old = path.read_bytes().decode("utf-8")
        new = retitle(old, texts["title"], texts["description"])
        if new != old:
            changed.append(name)
            if write:
                path.write_bytes(new.encode("utf-8"))
    return changed, missing


def main(argv: list[str], root: Path = ROOT) -> int:
    check = "--check" in argv
    try:
        changed, missing = apply(root, write=not check)
    except site_chrome.ChromeError as error:
        print("\n".join(error.problems), file=sys.stderr)
        return 2
    for name in changed:
        print(("à mettre à jour : " if check else "mis à jour : ") + name)
    for name in missing:
        print(f"introuvable : {name}", file=sys.stderr)
    print(f"{len(changed)} page(s) {'à mettre à jour' if check else 'mise(s) à jour'}, {len(missing)} introuvable(s)")
    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
