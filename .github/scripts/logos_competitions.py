"""Logos des compétitions : chaque compétition listée montre une marque, son logo quand il existe.

Les listes de compétitions (« Toutes les compétitions ») n'étaient que du texte, alors que les listes
d'équipes montrent déjà un logo. Le relais d'eSportly sert la liste des tournois et leurs logos (fonction
Edge `logos`, remplie depuis PandaScore) : on rapproche chaque compétition du site d'un tournoi **du même
jeu**, et on pose son logo devant le nom.

PandaScore ne fournit pas de logo pour toutes les séries (DreamLeague, BLAST Slam, OCS… n'en ont pas) :
celles-là reçoivent un jeton avec leur sigle, comme les équipes sans logo (`.tm i.mono`). La liste reste
donc alignée, avec de vrais logos là où il y en a.

Rejouable sans effet : une compétition déjà marquée est laissée telle quelle, un logo déjà téléchargé
n'est pas retéléchargé.

    python3 .github/scripts/logos_competitions.py --essai    # dit ce qu'il ferait, sans rien écrire
    python3 .github/scripts/logos_competitions.py            # télécharge et pose
"""
from __future__ import annotations

import html as H
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "logos-competitions"
ESSAI = "--essai" in sys.argv[1:]

JEUX = {
    "league-of-legends": "lol", "counter-strike-2": "csgo", "valorant": "valorant",
    "dota-2": "dota2", "rocket-league": "rl", "overwatch-2": "ow",
    "rainbow-six-siege": "r6siege", "call-of-duty": "codmw", "mobile-legends": "mlbb",
    "honor-of-kings": "kog", "ea-sports-fc": "fifa", "starcraft-2": "sc2",
    "wild-rift": "wildrift",
}

# Séries dont le nom au site diffère de celui du relais.
ALIAS = {
    "iem": "intel extreme masters",
    "epl masters": "epl world series",
    "europe mena league": "mena league",
    "challenger league": "esl challenger league",
}

STYLE = (
    ".cl{width:30px;height:30px;border-radius:9px;background:#fff;display:inline-flex;"
    "align-items:center;justify-content:center;overflow:hidden;flex-shrink:0}",
    ".cl img{max-width:24px;max-height:24px;width:auto;height:auto}",
    ".cl.mono{font-style:normal;font-weight:700;font-size:11px;letter-spacing:.02em;"
    "background:var(--surface);color:var(--muted);border:1px solid var(--border)}",
    ".comps li a{display:inline-flex;align-items:center;gap:8px}",
    ".hero .cl{display:flex;width:52px;height:52px;border-radius:14px;margin:0 0 14px}",
    ".hero .cl img{max-width:36px;max-height:36px}",
    ".hero .cl.mono{font-size:15px}",
)

LIGNE = re.compile(r'<li data-game="([^"]+)"><a href="([^"]+)"><b>([^<]*)</b>', re.S)
# Les listes de compétitions d'une page de jeu : <ul class="comps"><li><a href="…">Nom</a></li>
COMP = re.compile(r'(<li><a href="((?:[^"]*/)?competitions/([a-z0-9-]+))\.html">)([^<]+)(</a></li>)')


def norm(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", H.unescape(texte)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def sans_annee(texte: str) -> str:
    return norm(re.sub(r"\b(19|20)\d{2}\b", " ", texte))


def serie(nom: str) -> str:
    return norm(re.split(r"[·|]", nom)[0])


def sigle(nom: str) -> str:
    """« BLAST Rivals · Fall » → « BR », « DreamLeague » → « DL », « OCS » → « OCS »."""
    mots = [m for m in re.split(r"[^A-Za-z0-9]+", re.split(r"[·|]", nom)[0]) if m]
    if len(mots) > 1:
        return "".join(m[0] for m in mots)[:3].upper()
    if not mots:
        return ""
    mot = mots[0]
    # Un sigle déjà écrit en capitales (OCS, IEM) se garde tel quel.
    if sum(1 for c in mot if c.isupper()) >= 2 and mot.upper() == mot:
        return mot[:3]
    # Un nom en un mot avec des majuscules internes (DreamLeague) : ce sont elles.
    capitales = [c for c in mot if c.isupper()]
    if len(capitales) >= 2:
        return "".join(capitales)[:3]
    return mot[:3].upper()


def ligues() -> list[dict]:
    host, cle = os.environ.get("RELAY_HOST", ""), os.environ.get("RELAY_KEY", "")
    if not host or not cle:
        raise SystemExit("RELAY_HOST et RELAY_KEY sont nécessaires (Config/Shared.xcconfig de l'app).")
    req = urllib.request.Request(f"https://{host}/functions/v1/logos",
                                 headers={"Authorization": f"Bearer {cle}", "apikey": cle})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())["leagues"]


def choisir(nom: str, jeu: str, table: list[dict]) -> dict | None:
    """Le tournoi du même jeu qui correspond au nom affiché, ou None."""
    code = JEUX.get(jeu)
    if not code:
        return None
    memes = [l for l in table if l.get("game") == code]
    if not memes:
        return None
    sigle_serie = ALIAS.get(serie(nom), serie(nom))
    # Un vrai logo d'abord : le même nom de série, avec une image.
    for essai in (norm(nom), sans_annee(nom), sigle_serie):
        if not essai:
            continue
        for l in memes:
            if l.get("image_url") and norm(l["name"]) == essai:
                return l
    for essai in (sigle_serie, sans_annee(nom)):
        if not essai:
            continue
        for l in memes:
            n = norm(l["name"])
            if n and l.get("image_url") and (essai.startswith(n + " ") or n.startswith(essai + " ")):
                return l
    return None


def telecharger(url: str, cible: Path) -> bool:
    if cible.exists() and cible.stat().st_size > 0:
        return True
    if ESSAI:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "eSportly/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
    except Exception as e:
        print(f"    ! téléchargement impossible ({e})")
        return False
    if not data:
        return False
    DEST.mkdir(exist_ok=True)
    cible.write_bytes(data)
    return True


def main() -> None:
    table = ligues()
    print(f"relais : {len(table)} tournois, {sum(1 for l in table if l.get('image_url'))} avec logo")
    if not ESSAI:
        DEST.mkdir(exist_ok=True)
    total_logo = total_sigle = 0
    for page in ("competitions.html", "fr/competitions.html"):
        fichier = ROOT / page
        if not fichier.exists():
            continue
        prefix = "" if "/" not in page else "../"
        texte = fichier.read_text()
        poses = {"logo": 0, "sigle": 0}

        def remplacer(m: re.Match[str]) -> str:
            jeu, lien, nom = m.groups()
            trouve = choisir(nom, jeu, table)
            marque = ""
            if trouve:
                image = DEST / f"{Path(lien).stem}.png"
                if telecharger(trouve["image_url"], image):
                    poses["logo"] += 1
                    marque = (f'<i class="cl"><img src="{prefix}logos-competitions/{image.name}" '
                              f'alt="" loading="lazy"></i>')
            if not marque:
                court = sigle(nom)
                if not court:
                    return m.group(0)
                poses["sigle"] += 1
                marque = f'<i class="cl mono" aria-hidden="true">{court}</i>'
            return f'<li data-game="{jeu}"><a href="{lien}"><b>{marque}{nom}</b>'

        nouveau = LIGNE.sub(remplacer, texte)
        if poses["logo"] or poses["sigle"]:
            styles = "".join(STYLE)
            if STYLE[0] not in nouveau:
                nouveau = nouveau.replace("</style>", styles + "</style>", 1)
            if not ESSAI:
                fichier.write_text(nouveau)
            total_logo += poses["logo"]
            total_sigle += poses["sigle"]
            print(f"{page} : {poses['logo']} logo(s) officiel(s), {poses['sigle']} sigle(s)")
    # Les listes « Compétitions suivies » des pages de jeu.
    pages_comps = 0
    for fichier in sorted(ROOT.rglob("*.html")):
        if any(part in {".git", "logos-competitions"} for part in fichier.parts):
            continue
        texte = fichier.read_text(errors="ignore")
        if 'class="comps"' not in texte:
            continue

        def marquer(m: re.Match[str]) -> str:
            avant, lien, slug, nom, fin = m.groups()
            prefix = "../" * (len(fichier.relative_to(ROOT).parts) - 1)
            image = DEST / f"{slug}.png"
            if image.exists():
                marque = (f'<i class="cl"><img src="{prefix}logos-competitions/{image.name}" '
                          f'alt="" loading="lazy"></i>')
            else:
                court = sigle(nom)
                if not court:
                    return m.group(0)
                marque = f'<i class="cl mono" aria-hidden="true">{court}</i>'
            return avant + marque + nom + fin

        nouveau = COMP.sub(marquer, texte)
        if nouveau != texte:
            styles = "".join(STYLE)
            if STYLE[0] not in nouveau:
                nouveau = nouveau.replace("</style>", styles + "</style>", 1)
            if not ESSAI:
                fichier.write_text(nouveau)
            pages_comps += 1
    print(f"pages de jeu : {pages_comps} page(s) avec logo de compétition")

    # La marque en haut des pages de compétition (fr/competitions/*.html et competitions/*.html).
    pages_heros = 0
    for fichier in sorted((ROOT / "competitions").glob("*.html")) + sorted((ROOT / "fr" / "competitions").glob("*.html")):
        texte = fichier.read_text(errors="ignore")
        if '<section class="hero">' not in texte or '<i class="cl' in texte.split("</section>")[0]:
            continue
        prefix = "../" * (len(fichier.relative_to(ROOT).parts) - 1)
        image = DEST / f"{fichier.stem}.png"
        if image.exists():
            marque = (f'<i class="cl"><img src="{prefix}logos-competitions/{image.name}" alt="" '
                      f'loading="lazy"></i>')
        else:
            # Sans logo officiel, le sigle se lit dans le titre de la page.
            titre = re.search(r"<h1>([^<]*)</h1>", texte)
            court = sigle(titre.group(1)) if titre else ""
            if not court:
                continue
            marque = f'<i class="cl mono" aria-hidden="true">{court}</i>'
        nouveau = texte.replace('<section class="hero">', '<section class="hero">' + marque, 1)
        styles = "".join(STYLE)
        if STYLE[0] not in nouveau:
            nouveau = nouveau.replace("</style>", styles + "</style>", 1)
        if not ESSAI:
            fichier.write_text(nouveau)
        pages_heros += 1
    print(f"pages de compétition : {pages_heros} marque(s) posée(s)")


if __name__ == "__main__":
    main()
