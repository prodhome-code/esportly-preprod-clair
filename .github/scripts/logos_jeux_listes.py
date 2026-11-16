"""Listes d'équipes : le logo du jeu devant le nom du jeu, et des cartes alignées.

Sur une page d'équipe, « FURIA teams in eSportly » montrait le logo de chaque équipe puis son jeu en
petit, sans repère visuel : impossible de distinguer d'un coup d'œil un Counter-Strike d'un Rocket
League. Chaque ligne reçoit donc le logo du jeu (le même PNG que le menu « Jeux »), à 18 px, juste avant
le nom du jeu.

Les espacements sont aussi remis d'aplomb : le script logos_equipes.py avait laissé sur ces pages des
règles `.teams` prévues pour la page « Toutes les équipes » (colonnes de 132 px, cartes en colonne), qui
rétrécissaient les cartes des pages d'équipe. Une règle finale, plus spécifique et placée en fin de
feuille, fixe la grille et le rythme interne ; les pages qui listent des équipes en liens gardent leur
mise en page.

Rejouable sans effet.

    python3 .github/scripts/logos_jeux_listes.py --essai
    python3 .github/scripts/logos_jeux_listes.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ESSAI = "--essai" in sys.argv[1:]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}

# Logos dessinés en blanc : sur une carte claire, ils disparaissent. On les dessine en masque, de la
# couleur du texte, comme les pages de jeu (« glogo mono »).
MONO = {"call-of-duty", "counter-strike-2", "ea-sports-fc", "honor-of-kings", "overwatch-2",
        "rocket-league", "starcraft-brood-war"}

CSS = (
    ".teams{grid-template-columns:repeat(auto-fill,minmax(258px,1fr));gap:12px}",
    ".teams li{gap:14px;padding:14px 16px;min-height:78px}",
    ".teams li .sg.logo{min-width:52px;height:52px;border-radius:15px;padding:7px}",
    ".teams li .sg.logo img{max-width:56px;max-height:38px}",
    ".teams li small{display:flex;align-items:center;gap:7px;margin-top:3px;line-height:1.2}",
    ".teams small img.gl{width:18px;height:18px;flex-shrink:0;object-fit:contain}",
    ".teams li a{display:inline-flex;align-items:center;gap:6px;padding:0;border:0;background:none;"
    "border-radius:0;font-weight:600;text-decoration:none;min-height:0}",
    ".teams small .gl-mono{width:26px;height:18px;flex-shrink:0;background:currentColor;"
    "-webkit-mask:var(--src) center/contain no-repeat;mask:var(--src) center/contain no-repeat}",
)

# <small><a href="../games/dota-2.html">Dota 2</a></small> → logo inséré après <small>
LIGNE = re.compile(r'<small>(?=<a href="((?:[^"]*/)?)(?:games|jeux|juegos|spiele|jogos)/([a-z0-9-]+)\.html">)')


def main() -> None:
    pages = fichiers = liens = 0
    for fichier in sorted(ROOT.rglob("*.html")):
        rel = fichier.relative_to(ROOT)
        if SKIP_DIRS.intersection(rel.parts[:-1]):
            continue
        texte = fichier.read_text(errors="ignore")
        if '<ul class="teams">' not in texte:
            continue
        prefixe = "../" * (len(rel.parts) - 1)

        def ajouter(m: re.Match[str]) -> str:
            nonlocal liens
            jeu = m.group(2)
            liens += 1
            if jeu in MONO:
                return (f'<small><i class="gl gl-mono" aria-hidden="true" '
                        f'style="--src:url({prefixe}logos-jeux/{jeu}.png)"></i>')
            return (f'<small><img class="gl" src="{prefixe}logos-jeux/{jeu}.png" alt="" '
                    f'width="18" height="18" loading="lazy">')

        avant = liens
        texte = re.sub(
            r'<img class="gl" src="([^"]*logos-jeux/([a-z0-9-]+)\.png)" alt="" width="18" height="18" loading="lazy">',
            lambda m: (f'<i class="gl gl-mono" aria-hidden="true" style="--src:url({m.group(1)})"></i>'
                       if m.group(2) in MONO else m.group(0)),
            texte)
        nouveau = LIGNE.sub(ajouter, texte)
        if liens > avant and CSS[0] not in nouveau:
            nouveau = nouveau.replace("</style>", "".join(CSS) + "</style>", 1)
        # la règle du masque peut manquer sur une page déjà passée une fois
        if ".gl-mono{" not in nouveau and 'class="gl gl-mono"' in nouveau:
            nouveau = nouveau.replace("</style>", CSS[-1] + "</style>", 1)
        if nouveau != texte:
            if not ESSAI:
                fichier.write_text(nouveau)
            fichiers += 1
    print(f"{fichiers} page(s), {liens} ligne(s) de jeu")


if __name__ == "__main__":
    main()
