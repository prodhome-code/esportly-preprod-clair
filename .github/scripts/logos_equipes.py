"""Logos des équipes : partout où le site liste des équipes, chaque entrée montre son logo et son nom.

Les listes d'équipes des pages de jeux (« Les équipes à suivre ») et des pages d'équipes (« D'autres équipes ») n'étaient que
des liens en texte, alors que la page « Toutes les équipes » montre déjà logo et nom. Ce script leur donne la même présentation,
avec les mêmes classes et les mêmes règles de style : rien de nouveau à dessiner, et aucune image à aller chercher (les 136 logos
sont déjà dans le dépôt, dans logos-equipes/).

Il ne touche qu'une liste dont **tous** les liens mènent à une fiche d'équipe connue : les listes de jeux ou de pages utiles
(« Les autres jeux », « Pour aller plus loin ») gardent leur forme. Une équipe sans logo garde son nom seul.

Rejouable sans effet : une liste déjà transformée est reconnue et laissée telle quelle.

    py -3.13 .github/scripts/logos_equipes.py           # transforme les listes
    py -3.13 .github/scripts/logos_equipes.py --essai   # dit ce qu'il ferait, sans rien écrire
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import site_chrome as sc

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}
NAV = re.compile(r'<nav class="others" aria-label="([^"]*)">(.*?)</nav>', re.S)
LINK = re.compile(r'<a href="([^"]+)">([^<]*)</a>')
# Les règles de style de la page « Toutes les équipes », recopiées telles quelles (with_css n'ajoute que ce qui manque).
STYLE = (
    ".teams{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin:0;padding:0;list-style:none}",
    ".teams a{display:flex;align-items:center;gap:12px;padding:12px;border-radius:16px;background:var(--surface);"
    "border:1px solid var(--border);color:var(--text);text-decoration:none;font-weight:600}",
    ".teams a i.tl{width:28px;height:28px;border-radius:8px;background:#fff;display:inline-flex;align-items:center;"
    "justify-content:center;flex-shrink:0}",
    ".teams a i.tl img{max-width:22px;max-height:22px;width:auto;height:auto}",
    # Le logo au-dessus, le nom en dessous : des vignettes carrées plutôt qu'une ligne de texte avec une pastille.
    ".teams{grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}",
    ".teams a{flex-direction:column;text-align:center;gap:8px;padding:14px 10px;font-size:14px;line-height:1.25}",
    ".teams a i.tl{width:56px;height:56px;border-radius:14px}",
    ".teams a i.tl img{max-width:44px;max-height:44px}",
)


def logos(root: Path) -> dict[str, str]:
    """{identifiant de la fiche: nom du fichier du logo} : le premier logo présent dans logos-equipes/ pour cette organisation.
    Une fiche sans logo local n'est pas dans le résultat : son entrée gardera son nom seul."""
    found: dict[str, str] = {}
    for path in sorted((root / "equipes").glob("*.json")):
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue  # index-pages.json, minces.json : ce ne sont pas des fiches
        for team in data.get("equipes") or []:
            if not isinstance(team, dict):
                continue
            name = f"{team.get('id')}.webp"
            if (root / "logos-equipes" / name).is_file():
                found.setdefault(path.stem, name)
                break
    return found


def team_slug(href: str) -> str | None:
    """L'identifiant de la fiche visée par un lien (« ../../fr/equipes/t1.html », « t1.html » entre voisines), None sinon."""
    tail = href.rsplit("/", 1)[-1]
    return tail[:-5] if tail.endswith(".html") and re.fullmatch(r"[a-z0-9-]+", tail[:-5]) else None


def render(page: str, rel: str, known: set[str], logo_of: dict[str, str]) -> str:
    """La page avec ses listes d'équipes transformées. `rel` : chemin de la page depuis la racine, pour la profondeur des logos."""
    up = "../" * rel.count("/")

    def one(found: re.Match) -> str:
        links = LINK.findall(found.group(2))
        slugs = [team_slug(href) for href, _ in links]
        if len(links) < 2 or any(slug is None or slug not in known for slug in slugs):
            return found.group(0)  # liste de jeux, de pages utiles… : on n'y touche pas
        items = []
        for (href, name), slug in zip(links, slugs):
            logo = logo_of.get(slug or "")
            badge = f'<i class="tl"><img src="{up}logos-equipes/{logo}" alt="" width="128" height="116" loading="lazy"></i>' if logo else ""
            items.append(f'<li><a href="{href}">{badge}<span>{name}</span></a></li>')
        return f'<ul class="teams" aria-label="{found.group(1)}">{"".join(items)}</ul>'

    return NAV.sub(one, page)


def pages(root: Path):
    for path in sorted(root.rglob("*.html")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def main(argv: list[str], root: Path = ROOT) -> int:
    logo_of = logos(root)
    known = {path.stem for path in (root / "equipes").glob("*.json")} - {"index-pages", "minces"}
    changed = []
    for path in pages(root):
        rel = path.relative_to(root).as_posix()
        before = path.read_text(encoding="utf-8")
        after = render(before, rel, known, logo_of)
        # Le style va sur toute page qui liste des équipes, même celles déjà en logos (« Toutes les équipes ») : elles passent
        # ainsi à la même présentation, logo au-dessus et nom en dessous.
        if 'class="teams"' in after:
            after = sc.with_css(after, "\n".join(STYLE))
        if after == before:
            continue
        changed.append(rel)
        if "--essai" not in argv:
            path.write_text(after, encoding="utf-8", newline="")
    print(f"Logos d'équipes : {len(changed)} page(s) {'à transformer' if '--essai' in argv else 'transformée(s)'} "
          f"({len(logo_of)} organisations avec un logo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
