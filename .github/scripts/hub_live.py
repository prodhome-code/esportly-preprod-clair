"""Hub live de la refonte 2026 : les 14 jeux et les matchs du jour, en haut des cinq accueils.

La maquette de la refonte ouvre le site sur un « hub live » : une bande avec les 14 jeux (pastille
rouge sur ceux qui ont un match aujourd'hui) puis les matchs du jour en cartes. Ce script le
fabrique pour chaque langue et le pose sur l'accueil, juste après la section d'accroche.

D'où viennent les données : de la page « Live » de la même langue (live.html, fr/live.html…),
fabriquée chaque matin par matchs.py. Aucun appel réseau, aucune clé, rien à configurer : si la
page Live existe, le hub existe ; sinon l'accueil est laissé tel quel.

Aucun JavaScript ajouté : la page garde sa CSP, le hub est du HTML et du CSS. Les horaires sont
affichés tels qu'ils sont déjà écrits dans la page Live (heure de Paris), avec les mêmes liens.

Rejouable sans effet : un accueil qui porte déjà le hub (repère REPERE) est réécrit avec les
matchs du jour, jamais dupliqué. À lancer après matchs.py / live.py dans les tâches planifiées.

    python3 .github/scripts/hub_live.py            # pose ou met à jour le hub
    python3 .github/scripts/hub_live.py --check    # dit ce qu'il ferait, sans rien écrire
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import site_chrome as sc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPERE_DEB, REPERE_FIN = "<!--hub-live-->", "<!--/hub-live-->"
STYLE_REPERE = "/*hub-live*/"
MAX_CARTES = 6  # les matchs mis en cartes ; les suivants vont dans la liste « ensuite aujourd'hui »
MAX_LISTE = 6

# Nom court de chaque jeu pour la bande du haut (la maquette affiche « LoL », « CS2 »…).
COURTS = {
    "league-of-legends": "LoL", "counter-strike-2": "CS2", "valorant": "Valo", "rocket-league": "RL",
    "dota-2": "Dota 2", "overwatch-2": "OW2", "rainbow-six-siege": "R6", "call-of-duty": "CoD",
    "mobile-legends": "MLBB", "honor-of-kings": "HoK", "ea-sports-fc": "EA FC", "starcraft-2": "SC2",
    "starcraft-brood-war": "BW", "wild-rift": "Wild Rift"}

# Textes du hub, par langue (aucun « < », « > », « & » ni guillemet droit).
TEXTES = {
    "en": dict(titre="Live hub", jeux="The 14 games", jeux_sous="One click = that game's matches",
               matchs="Today's matches", tous="All live matches", ensuite="Later today",
               heure="Times shown in Paris time", vide="No match listed today."),
    "fr": dict(titre="Hub live", jeux="Les 14 jeux", jeux_sous="Un clic = les matchs du jeu",
               matchs="Les matchs du jour", tous="Tous les lives", ensuite="Ensuite aujourd'hui",
               heure="Horaires en heure de Paris", vide="Aucun match au programme aujourd'hui."),
    "es": dict(titre="Hub en directo", jeux="Los 14 juegos", jeux_sous="Un clic = los partidos del juego",
               matchs="Los partidos de hoy", tous="Todos los directos", ensuite="Más tarde hoy",
               heure="Horarios en hora de París", vide="Hoy no hay partidos programados."),
    "de": dict(titre="Live-Hub", jeux="Die 14 Spiele", jeux_sous="Ein Klick = die Matches des Spiels",
               matchs="Die Matches von heute", tous="Alle Livespiele", ensuite="Später heute",
               heure="Zeiten in Pariser Zeit", vide="Heute sind keine Matches angesetzt."),
    "pt-BR": dict(titre="Hub ao vivo", jeux="Os 14 jogos", jeux_sous="Um clique = as partidas do jogo",
                  matchs="As partidas de hoje", tous="Todos os jogos ao vivo", ensuite="Mais tarde hoje",
                  heure="Horários no fuso de Paris", vide="Nenhuma partida programada hoje."),
}

CSS = """.hublive{padding:34px 0 10px}
.hublive h2{font-family:var(--display);font-size:clamp(26px,3vw,38px);line-height:1;margin:0 0 4px}
.hublive .hl-sub{color:var(--muted);margin:0 0 18px;font-size:15px}
.hl-wrapstrip{position:relative}
.hl-wrapstrip::after{content:"";position:absolute;top:0;bottom:14px;right:0;width:46px;pointer-events:none;
 background:linear-gradient(to right,rgba(0,0,0,0),var(--nuit))}
.hl-strip{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding:2px 0 14px;margin:0;list-style:none;scroll-snap-type:x proximity}
.hl-strip li{scroll-snap-align:start}
.hl-strip::-webkit-scrollbar{display:none}
.hl-strip li{flex:0 0 auto}
.hl-tile{display:flex;align-items:center;gap:8px;min-height:52px;padding:0 14px;border-radius:999px;
 border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:700;font-size:15px;white-space:nowrap}
.hl-tile:hover{border-color:var(--or);color:var(--text)}
.hl-tile img{width:22px;height:22px;object-fit:contain}
.hl-tile .hl-dot{width:8px;height:8px;border-radius:50%;background:var(--live);flex:0 0 auto}
.hl-cards{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));margin:0;padding:0;list-style:none}
.hl-card{display:block;border:1px solid var(--border);border-radius:16px;background:var(--surface);padding:14px 16px;color:var(--text)}
.hl-card:hover{border-color:var(--or);color:var(--text)}
.hl-card .hl-when{font-size:13px;color:var(--muted);display:block;margin-bottom:8px}
.hl-card .hl-row{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px}
.hl-card .hl-row img{width:24px;height:24px;object-fit:contain}
.hl-card .hl-ini{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:7px;
 background:var(--raised);color:var(--muted);font-style:normal;font-size:11px;font-weight:700;flex:0 0 auto}
.hl-card .hl-vs{color:var(--muted);font-weight:600}
.hl-card .hl-ev{display:block;margin-top:8px;font-size:13px;color:var(--muted)}
.hl-next{margin:18px 0 0;padding:0;list-style:none;border-top:1px solid var(--border)}
.hl-next li{display:flex;gap:12px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--border);font-size:15px}
.hl-next time{font-variant-numeric:tabular-nums;font-weight:700;min-width:58px}
.hl-next .hl-ev{color:var(--muted);font-size:13px}
.hl-more{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 18px;margin-top:16px;
 border-radius:999px;background:var(--or);color:var(--on-or);font-weight:700}
.hl-more:hover{color:var(--on-or)}
@media (max-width:700px){.hublive{padding:24px 0 4px}}
"""

MATCH = re.compile(
    r'<li data-start="(?P<start>[^"]*)"[^>]*data-game="(?P<game>[^"]*)"[^>]*>\s*'
    r'<a href="(?P<href>[^"]*)">.*?<time datetime="[^"]*">(?P<when>.*?)</time>'
    r'<b>(?P<teams>.*?)</b><small>(?P<event>.*?)</small>', re.S)
# Une équipe de la page Live : logo en image, ou initiales (<i class="mono">KC</i>) quand le logo manque.
TEAM = re.compile(r'<span class="tm">\s*<i[^>]*>(?:<img src="(?P<logo>[^"]*)"[^>]*>)?(?P<ini>[^<]*)</i>(?P<name>[^<]*)</span>')


def _txt(s: str) -> str:
    """Le texte d'un fragment HTML, sans balise."""
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def matchs_de(page: Path) -> list[dict]:
    """Les matchs du jour lus dans une page Live. Liste vide si la page manque."""
    if not page.exists():
        return []
    texte = page.read_text(encoding="utf-8")
    out = []
    for m in MATCH.finditer(texte):
        equipes = [{"logo": t.group("logo") or "", "ini": (t.group("ini") or "").strip(),
                    "name": t.group("name").strip()}
                   for t in TEAM.finditer(m.group("teams"))]
        if len(equipes) != 2 or any(sc.is_betting(e["name"]) for e in equipes):
            continue
        heure = _txt(m.group("when"))
        out.append({"href": m.group("href"), "game": m.group("game"), "a": equipes[0], "b": equipes[1],
                    "when": heure, "hhmm": heure.split("·")[-1].strip(), "event": _txt(m.group("event"))})
    return out


def _relier(chemin: str, depuis_live: str) -> str:
    """Un lien écrit dans la page Live (vu d'elle) ramené à la racine du site, où vivent les accueils."""
    base = depuis_live.rsplit("/", 1)[0] if "/" in depuis_live else ""
    tronc = chemin
    while tronc.startswith("../"):
        tronc = tronc[3:]
        base = base.rsplit("/", 1)[0] if "/" in base else ""
    return f"{base}/{tronc}" if base else tronc


def hub(lang: str, live_page: str, matchs: list[dict]) -> str:
    """Le HTML du hub live d'une langue (vu de l'accueil, à la racine du site)."""
    t = TEXTES[lang]
    actifs = {m["game"] for m in matchs}
    tuiles = []
    for game in sc.GAMES:
        point = '<span class="hl-dot" aria-hidden="true"></span>' if game in actifs else ""
        nom = html.escape(sc.GAME_NAMES[game], quote=True)
        tuiles.append(f'<li><a class="hl-tile" href="{sc.GAME_DIRS[lang]}/{game}.html" title="{nom}">{point}'
                      f'<img src="logos-jeux/{game}.png" alt="" width="22" height="22" loading="lazy">'
                      f'{html.escape(COURTS[game])}</a></li>')

    def blason(e: dict) -> str:
        """Le logo de l'équipe, ou ses initiales quand le site n'a pas d'image pour elle."""
        if e["logo"]:
            return (f'<img src="{html.escape(_relier(e["logo"], live_page), quote=True)}" alt="" '
                    f'width="24" height="24" loading="lazy">')
        return f'<i class="hl-ini" aria-hidden="true">{html.escape(e["ini"] or e["name"][:2].upper())}</i>'

    cartes = []
    for m in matchs[:MAX_CARTES]:
        href = html.escape(_relier(m["href"], live_page), quote=True)
        a, b = m["a"], m["b"]
        cartes.append(
            f'<li><a class="hl-card" href="{href}">'
            f'<span class="hl-when">{html.escape(m["when"])}</span>'
            f'<span class="hl-row">{blason(a)}{html.escape(a["name"])}'
            f'<em class="hl-vs">–</em>'
            f'{blason(b)}{html.escape(b["name"])}</span>'
            f'<span class="hl-ev">{html.escape(m["event"])}</span></a></li>')

    suite = []
    for m in matchs[MAX_CARTES:MAX_CARTES + MAX_LISTE]:
        href = html.escape(_relier(m["href"], live_page), quote=True)
        suite.append(f'<li><time>{html.escape(m["hhmm"])}</time>'
                     f'<a href="{href}">{html.escape(m["a"]["name"])} – {html.escape(m["b"]["name"])}</a>'
                     f'<span class="hl-ev">{html.escape(m["event"])}</span></li>')

    corps = f'<ul class="hl-cards">{"".join(cartes)}</ul>' if cartes else f'<p class="hl-sub">{t["vide"]}</p>'
    if suite:
        corps += f'<h3 class="hl-sub" style="margin:22px 0 0">{t["ensuite"]}</h3><ul class="hl-next">{"".join(suite)}</ul>'
    return (f'{REPERE_DEB}<section class="hublive" id="hub-live" aria-labelledby="hub-live-t"><div class="wrap">'
            f'<h2 id="hub-live-t">{t["jeux"]}</h2><p class="hl-sub">{t["jeux_sous"]}</p>'
            f'<div class="hl-wrapstrip"><ul class="hl-strip">{"".join(tuiles)}</ul></div>'
            f'<h2>{t["matchs"]}</h2><p class="hl-sub">{t["heure"]}</p>{corps}'
            f'<a class="hl-more" href="{live_page}">{t["tous"]} →</a>'
            f'</div></section>{REPERE_FIN}')


def poser(accueil: Path, bloc: str) -> bool:
    """Pose ou remplace le hub dans un accueil, et son CSS. Vrai si la page a changé."""
    texte = accueil.read_text(encoding="utf-8")
    if REPERE_DEB in texte:
        neuf = re.sub(re.escape(REPERE_DEB) + ".*?" + re.escape(REPERE_FIN), lambda _: bloc, texte, flags=re.S)
    else:
        m = re.search(r'<section class="block news"', texte) or re.search(r"</section>", texte)
        if not m:
            return False
        neuf = texte[:m.start()] + bloc + texte[m.start():]
    if STYLE_REPERE not in neuf:
        s = re.search(r"</style>", neuf)
        if not s:
            return False
        neuf = neuf[:s.start()] + STYLE_REPERE + CSS + neuf[s.start():]
    if neuf == texte:
        return False
    accueil.write_text(neuf, encoding="utf-8")
    return True


def main() -> int:
    check = "--check" in sys.argv
    faits = []
    for lang, accueil in sc.HOMES.items():
        page = ROOT / accueil
        live = sc.LIVE_PAGES[lang]
        matchs = matchs_de(ROOT / live)
        if not page.exists():
            continue
        bloc = hub(lang, live, matchs)
        if check:
            print(f"{accueil} : {len(matchs)} matchs lus dans {live}")
            continue
        if poser(page, bloc):
            faits.append(f"{accueil} ({len(matchs)} matchs)")
    if not check:
        print(f"hub live posé sur {len(faits)} accueils : {', '.join(faits) if faits else 'aucun'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
