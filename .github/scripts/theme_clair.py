"""Thème clair par défaut (refonte 2026), sans toucher au sélecteur de thème ni à la CSP.

Le site porte déjà un thème clair complet, écrit dans chaque page sous la forme de règles
`:root[data-theme="light"] …`, appliqué uniquement quand le visiteur a choisi « clair ». La
refonte reprend ce thème clair comme apparence par défaut (c'est l'apparence de la maquette) :
fond clair, en-tête sombre, mêmes couleurs de marque (#FFC53D, #0A0E1A, #D41F34).

Comment : pour chaque page, on recopie à la fin du <style> les règles du thème clair en
remplaçant le sélecteur `[data-theme="light"]` par `:not([data-theme="dark"])`. Résultat :
- visiteur sans préférence enregistrée -> thème clair (le nouveau design) ;
- visiteur qui a choisi « sombre » -> `data-theme="dark"`, l'ancien thème, intact ;
- le bouton de thème, le JavaScript et les hachages CSP ne changent pas (aucun script touché).

Rejouable sans effet : une page déjà traitée porte le repère REPERE et n'est pas retouchée.
Ne touche pas : widgets, pages de renvoi, maquettes, pages sans thème clair.

Lancé à la main :  python3 .github/scripts/theme_clair.py [--check] [--racine DOSSIER]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPERE = "/*refonte-clair*/"
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "blog-src", "node_modules",
             ".wrangler", "worker", "widget", "maquettes"}
SKIP_PAGES = {"match.html", "tv-equipes.html", "_compare.svg.html"}
STYLE = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.S)
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def regles_claires(css: str) -> str:
    """Les règles du thème clair, réécrites pour s'appliquer par défaut (sauf thème sombre choisi)."""
    out = []
    for sel, corps in RULE.findall(css):
        sel = sel.strip()
        if 'data-theme="light"' not in sel or not corps.strip():
            continue
        # « :root[data-theme="light"] .pill » -> « :root:not([data-theme="dark"]) .pill »
        neuf = sel.replace('[data-theme="light"]', ':not([data-theme="dark"])')
        out.append(f"{neuf}{{{corps}}}")
    return "".join(out)


def traiter(page: Path) -> bool:
    """Ajoute le thème clair par défaut à une page. Vrai si la page a changé."""
    texte = page.read_text(encoding="utf-8")
    if REPERE in texte or 'data-theme="light"' not in texte:
        return False
    m = STYLE.search(texte)
    if not m:
        return False
    ajout = regles_claires(m.group(2))
    if not ajout:
        return False
    neuf = texte[:m.end(2)] + REPERE + ajout + texte[m.end(2):]
    page.write_text(neuf, encoding="utf-8")
    return True


def pages(racine: Path):
    for p in sorted(racine.rglob("*.html")):
        rel = p.relative_to(racine)
        if set(rel.parts) & SKIP_DIRS or rel.name in SKIP_PAGES:
            continue
        yield p


def main() -> int:
    args = sys.argv[1:]
    racine = ROOT
    if "--racine" in args:
        racine = Path(args[args.index("--racine") + 1]).resolve()
    check = "--check" in args
    touchees = []
    for p in pages(racine):
        if check:
            t = p.read_text(encoding="utf-8")
            if REPERE not in t and 'data-theme="light"' in t:
                touchees.append(p)
        elif traiter(p):
            touchees.append(p)
    mot = "à traiter" if check else "traitées"
    print(f"{len(touchees)} pages {mot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
