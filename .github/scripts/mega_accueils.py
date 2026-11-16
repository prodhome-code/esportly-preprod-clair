"""Mega menu des jeux sur les cinq accueils : « Jeux » n'est plus une ancre, c'est un panneau qui ouvre les 14 jeux.

Les pages fabriquées (jeux, équipes, Blog, News, Live, événements) reçoivent ce menu de `site_chrome.render_menu`, qui le pose
sur chacune d'elles. Les cinq accueils, eux, portent leur menu à la main : ce script leur applique le même, mot pour mot
(`site_chrome.games_menu` et `games_panel`), pour que la barre soit identique partout.

Il est rejouable sans effet : un accueil qui a déjà son panneau n'est pas retouché.

    py -3.13 .github/scripts/mega_accueils.py           # pose le menu
    py -3.13 .github/scripts/mega_accueils.py --essai   # dit ce qu'il ferait, sans rien écrire

Attention : les accueils sont rédigés dans le dépôt de l'application (dossier `Site/`) puis recopiés ici. Après une recopie, ce
script est à relancer — c'est précisément pour cela qu'il est rejouable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import site_chrome as sc

ROOT = Path(__file__).resolve().parents[2]
# Le bandeau défilant des accueils déborde de 4 px (ses marges négatives) et fait apparaître une barre de défilement
# horizontale sur toute la page : « clip » la supprime sans casser les éléments collants, contrairement à « hidden ».
HOME_STYLE = "body{overflow-x:clip}"
HOMES = {"en": "index.html", "fr": "fr.html", "es": "es.html", "de": "de.html", "pt-BR": "pt.html"}
HEADER = re.compile(r"<header>.*?</header>", re.S)
NAV = re.compile(r"(<nav\b[^>]*>)(.*?)(</nav>)", re.S)
# Le panneau du burger, cherché dans l'en-tête seulement et jusqu'à SA fin : non gourmande, l'expression s'arrêtait au premier
# « </div></details> », c'est-à-dire au milieu du panneau des équipes, et la suite du burger échappait au script.
PANEL = re.compile(r'(<div class="panel"[^>]*>)(.*)(</div></details>)', re.S)
JEUX = re.compile(r'<a href="#jeux">[^<]*</a>')
EQUIPES = re.compile(r'<a href="#equipes">[^<]*</a>')
# Entrées retirées du menu des accueils : leurs sections restent sur la page, seul le lien de la barre et du burger s'en va.
DROPPED = re.compile(r'<a href="#(?:fonctions|appareils|questions)">[^<]*</a>')
# L'ancien panneau des équipes du burger (avant qu'il ne porte sa propre classe) : il part, sinon il reste en double.
OLD_TEAMS = re.compile(r'<details class="megam"><summary>(?:(?!</details>).)*?<div class="teamm">.*?</div></details>', re.S)


BAR_GAMES = re.compile(r'<details class="mega">.*?</details>', re.S)
BAR_TEAMS = re.compile(r'<details class="mega team">.*?</details>', re.S)
MENU_GAMES = re.compile(r'<details class="megam">.*?</details>', re.S)
MENU_TEAMS = re.compile(r'<details class="megam team">.*?</details>', re.S)


def _panels(inside: str, lang: str, games: str, teams: str) -> str:
    """Une barre ou un panneau de burger avec les deux panneaux à leur place : « Jeux » devient celui des jeux, « Équipes » celui
    des équipes, et les entrées retirées s'en vont. Chaque panneau n'est posé que s'il manque : rejoué sur un accueil déjà fait,
    rien n'est dupliqué — c'est le piège, puisque les accueils sont recopiés depuis le dépôt de l'application."""
    inside = OLD_TEAMS.sub("", inside)
    burger = games.startswith('<details class="megam"')
    old_games, old_teams = (MENU_GAMES, MENU_TEAMS) if burger else (BAR_GAMES, BAR_TEAMS)
    # Un panneau déjà posé est REMPLACÉ par celui du jour : sans cela, un accueil gardait la version de la veille (ses
    # libellés, ses liens) pendant que les pages fabriquées, elles, suivaient.
    inside = old_games.sub(lambda _: games, inside, count=1) if old_games.search(inside) else JEUX.sub(lambda _: games, inside, count=1)
    if old_teams.search(inside):
        inside = old_teams.sub(lambda _: teams, inside, count=1)
        inside = EQUIPES.sub("", inside, count=1)  # l'ancienne ancre s'en va
    elif EQUIPES.search(inside):
        inside = EQUIPES.sub(lambda _: teams, inside, count=1)
    else:  # le menu burger n'a jamais eu d'entrée « Équipes » : son panneau se pose juste après celui des jeux
        cut = inside.find("</details>")
        inside = (inside[:cut + len("</details>")] + teams + inside[cut + len("</details>"):]) if cut >= 0 else inside + teams
    return DROPPED.sub("", inside)


def apply(page: str, lang: str) -> str | None:
    """L'accueil avec le panneau des jeux et celui des équipes, dans la barre comme dans le menu burger, les entrées retirées du
    menu en moins, le style et le script à jour ; None quand il n'y a rien à faire ou que la page ne ressemble pas à un accueil
    (ni lien « #jeux » ni panneau dans sa barre)."""
    head = HEADER.search(page)
    if head is None:
        return None
    header = head.group(0)
    nav = NAV.search(header)
    if nav is None or not (JEUX.search(nav.group(2)) or 'class="mega"' in nav.group(2)):
        return None
    bar = _panels(nav.group(2), lang, sc.games_menu(lang, "", ""), sc.teams_menu(lang, ""))
    header = header[:nav.start(2)] + bar + header[nav.end(2):]
    panel = PANEL.search(header)  # les positions ont bougé : on relit le panneau dans l'en-tête déjà modifié
    if panel is not None:
        inside = _panels(panel.group(2), lang, sc.games_panel(lang, ""), sc.teams_panel(lang, ""))
        header = header[:panel.start(2)] + inside + header[panel.end(2):]
    done = page[:head.start()] + header + page[head.end():]
    done = sc.swap_menu_script(sc.with_css(done, "\n".join(sc.MEGA_STYLE) + "\n" + HOME_STYLE))
    return done if done != page else None


def main(argv: list[str], root: Path = ROOT) -> int:
    essai, changed = "--essai" in argv, 0
    for lang, name in HOMES.items():
        path = root / name
        if not path.is_file():
            print(f"{name} : absent")
            continue
        page = path.read_text(encoding="utf-8")
        done = apply(page, lang)
        if done is None or done == page:
            print(f"{name} : déjà à jour")
            continue
        changed += 1
        print(f"{name} : panneau des jeux posé ({len(sc.GAMES)} jeux)")
        if not essai:
            path.write_text(done, encoding="utf-8")
    print(f"Mega menu : {changed} accueil(s) {'à mettre à jour' if essai else 'mis à jour'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
