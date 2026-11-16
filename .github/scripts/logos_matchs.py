"""Logos des équipes sur les cartes de match.

Une carte de match ne montrait que « Yellow Submarine – GamerLegion » en texte. Ce script met devant chaque équipe son logo
quand le site l'a (les 136 logos de logos-equipes/), et sinon ses initiales sur une pastille : toutes les cartes se ressemblent,
aucune n'a de trou.

Le calendrier ne donne que le **titre** du match (« Grand Final: Na`Vi vs TBD ») : les deux équipes en sont déduites, et le
titre est laissé tel quel quand le découpage n'est pas sûr (plus de deux morceaux, un seul camp, un nom vide). Aucune requête
réseau : les noms sont rapprochés des fiches de equipes/*.json, de leurs autres noms et de leurs sigles.

Rejouable sans effet : une carte déjà faite est reconnue et laissée telle quelle.

    py -3.13 .github/scripts/logos_matchs.py           # pose les logos
    py -3.13 .github/scripts/logos_matchs.py --essai   # dit ce qu'il ferait, sans rien écrire
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path

import site_chrome as sc

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker"}
# Les listes de la page Live portent un identifiant (<ul class="matchs" id="l-live">) : le motif ne doit pas exiger que la
# balise s'arrête tout de suite, sinon la page du jour reste sans logos.
LIST = re.compile(r'<ul class="matchs"[^>]*>.*?</ul>', re.S)
# La pastille d'état (« EN DIRECT », « À VENIR ») s'est glissée entre le lien et l'heure : sans elle dans le motif, plus une
# seule carte n'était reconnue, et les logos des équipes avaient disparu du programme.
CARD = re.compile(r'(<a\b[^>]*>(?:<span class="etat"></span>)?(?:<time[^>]*>[^<]*</time>)?)<b>([^<]+)</b>')
# « – », « - », « vs », « VS », « x » : les séparateurs vus dans les titres du calendrier.
SPLIT = re.compile(r"\s+(?:–|—|-|vs\.?|VS|v\.?)\s+")
STAGE = re.compile(r"^[^:]{1,40}:\s*")
STYLE = (
    '.matchs b{display:flex;align-items:center;flex-wrap:wrap;gap:6px}',
    '.matchs .tm{display:inline-flex;align-items:center;gap:7px;min-width:0}',
    '.matchs .tm i{width:26px;height:26px;border-radius:8px;background:#fff;display:inline-flex;align-items:center;'
    'justify-content:center;flex-shrink:0;overflow:hidden}',
    '.matchs .tm i img{max-width:20px;max-height:20px;width:auto;height:auto}',
    '.matchs .tm i.mono{font-style:normal;font-weight:700;font-size:11px;letter-spacing:.02em;background:var(--surface);'
    'color:var(--muted);border:1px solid var(--border)}',
    '.matchs b em{font-style:normal;color:var(--muted);font-weight:600;flex-shrink:0}',
    '.matchs b .stage{color:var(--muted);font-weight:600;width:100%;font-size:13px}',
)


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def key(name: str) -> str:
    """Le nom réduit à ses lettres et chiffres : « Na`Vi » et « NAVI » se retrouvent, « Team Falcons » et « TeamFalcons » aussi."""
    return re.sub(r"[^a-z0-9]+", "", strip_accents(name).lower())


def logos(root: Path) -> dict[str, str]:
    """{nom d'équipe réduit: fichier du logo}. Chaque fiche donne son organisation, ses autres noms, et pour chacune de ses
    équipes son nom et son sigle : « KC » comme « Karmine Corp » mènent au même logo."""
    found: dict[str, str] = {}
    for path in sorted((root / "equipes").glob("*.json")):
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        names = {data["organisation"]} if data.get("organisation") else set()
        names |= {name for name in (data.get("noms") or []) if isinstance(name, str)}
        logo = None
        for team in data.get("equipes") or []:
            if not isinstance(team, dict):
                continue
            names |= {value for value in (team.get("nom"), team.get("sigle")) if isinstance(value, str)}
            if logo is None and (root / "logos-equipes" / f"{team.get('id')}.webp").is_file():
                logo = f"{team['id']}.webp"
        if logo:
            for name in names:
                if key(name):
                    found.setdefault(key(name), logo)
    return found


def monogram(name: str) -> str:
    """Les initiales d'une équipe sans logo : « Bilibili Gaming » → « BG », « B8 » → « B8 ». Jamais plus de deux signes."""
    if key(name) in {"tbd", "tba", "adeterminer", "determiner"}:
        return "?"  # l'adversaire n'est pas connu : des initiales inventées tromperaient
    words = [word for word in re.split(r"[^A-Za-z0-9]+", strip_accents(name)) if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def badge(name: str, up: str, logo_of: dict[str, str]) -> str:
    logo = logo_of.get(key(name))
    if logo:
        return f'<i><img src="{up}logos-equipes/{logo}" alt="" width="128" height="116" loading="lazy"></i>'
    return f'<i class="mono" aria-hidden="true">{html.escape(monogram(name))}</i>'


def teams_of(title: str) -> tuple[str, str, str] | None:
    """(étape, équipe de gauche, équipe de droite) à partir du titre du match, None quand le découpage n'est pas sûr.
    L'étape est le « Grand Final: » du début, gardée telle quelle : elle n'apprend rien de plus que le titre d'origine."""
    stage = ""
    found = STAGE.match(title)
    if found and SPLIT.search(title[found.end():]):
        stage, title = found.group(0).rstrip(), title[found.end():]
    parts = [part.strip() for part in SPLIT.split(title)]
    if len(parts) != 2 or not all(parts) or any(len(part) > 40 for part in parts):
        return None
    return stage, parts[0], parts[1]


def render(page: str, rel: str, logo_of: dict[str, str]) -> str:
    """La page avec ses cartes de match ornées des logos. `rel` : chemin de la page depuis la racine, pour la profondeur."""
    up = "../" * rel.count("/")

    def card(found: re.Match) -> str:
        title = html.unescape(found.group(2))
        split = teams_of(title)
        if split is None:
            return found.group(0)  # titre inhabituel : on n'y touche pas plutôt que de mal le couper
        stage, left, right = split
        stage_html = f'<span class="stage">{html.escape(stage)}</span>' if stage else ""
        inside = (f'{stage_html}<span class="tm">{badge(left, up, logo_of)}{html.escape(left)}</span><em>–</em>'
                  f'<span class="tm">{badge(right, up, logo_of)}{html.escape(right)}</span>')
        return f"{found.group(1)}<b>{inside}</b>"

    return LIST.sub(lambda found: CARD.sub(card, found.group(0)), page)


def pages(root: Path):
    for path in sorted(root.rglob("*.html")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def main(argv: list[str], root: Path = ROOT) -> int:
    logo_of = logos(root)
    changed = []
    for path in pages(root):
        rel = path.relative_to(root).as_posix()
        before = path.read_text(encoding="utf-8")
        after = render(before, rel, logo_of)
        # Même test que la liste elle-même : la page Live donne un identifiant à ses listes, et son style restait dehors —
        # les logos sortaient alors en taille réelle, 128 px de haut, au milieu des cartes.
        if LIST.search(after):
            after = sc.with_css(after, "\n".join(STYLE))
        if after == before:
            continue
        changed.append(rel)
        if "--essai" not in argv:
            path.write_text(after, encoding="utf-8", newline="")
    print(f"Logos sur les matchs : {len(changed)} page(s) {'à faire' if '--essai' in argv else 'faite(s)'} "
          f"({len(logo_of)} noms d'équipes reconnus)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
