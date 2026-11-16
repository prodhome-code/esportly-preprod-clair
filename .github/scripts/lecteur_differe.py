"""Direct différé : une vignette au lieu d'un lecteur en erreur, sur les pages de match.

YouTube refuse l'intégration d'un direct qui n'a pas encore commencé (erreur 153) : la page affichait un
cadre noir avec un message d'erreur. Elle montre désormais la vignette de la vidéo, un bouton lecture et
une phrase qui dit où on en est (« le direct n'a pas encore commencé » avant le coup d'envoi). Le lecteur
ne se crée qu'au clic (lecteur.js), donc rien ne se charge pour rien et l'erreur disparaît.

Les pages déjà publiées sont reprises ; les prochaines sont fabriquées avec la même vignette par
live_match.py. Rejouable sans effet.

    python3 .github/scripts/lecteur_differe.py --essai
    python3 .github/scripts/lecteur_differe.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ESSAI = "--essai" in sys.argv[1:]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}

NOTES = {
    "fr": ("Le direct n’a pas encore commencé.", "Le direct est en cours : appuie pour regarder."),
    "en": ("The stream hasn’t started yet.", "The match is live: tap to watch."),
    "es": ("La retransmisión aún no ha empezado.", "El partido está en directo: toca para verlo."),
    "de": ("Der Stream hat noch nicht begonnen.", "Das Match läuft: zum Ansehen tippen."),
    "pt": ("A transmissão ainda não começou.", "A partida está ao vivo: toca para ver."),
}

CADRE = re.compile(
    r'<div class="wframe"><iframe src="(https://www\.youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{6,})[^"]*)"'
    r' title="([^"]*)"[^>]*></iframe></div>')
DEBUT = re.compile(r'"startDate"\s*:\s*"([^"]+)"')
LANGUE = re.compile(r'<html[^>]*\blang="([A-Za-z-]+)"')


def vignette(m: re.Match[str], debut: str, langue: str) -> str:
    src, video, titre = m.group(1), m.group(2), m.group(3)
    attendre, en_cours = NOTES[langue]
    embed = src + ("&" if "?" in src else "?") + "autoplay=1"
    return _bouton(embed, "", titre, debut, attendre, en_cours)


def _bouton(embed: str, page: str, titre: str, debut: str, attendre: str, en_cours: str, libelle: str = "") -> str:
    """Le bouton-vignette. Sans adresse de page, on en déduit une chaîne : pas de photo d'ancienne émission."""
    chaine = re.search(r"live_stream\?channel=(UC[A-Za-z0-9_-]+)", embed)
    classe = "wposter sans-photo" if chaine else "wposter"
    contenu = (f'<span class="wlab">{html.escape(libelle or titre)}</span>'
               if chaine else "" )
    return (f'<div class="wframe wfacade"><button class="{classe}" type="button" '
            f'data-embed="{embed}" data-page="{page}" data-start="{debut}" data-title="{titre}" '
            f'data-note-wait="{html.escape(attendre, quote=True)}" data-note-live="{html.escape(en_cours, quote=True)}">'
            f'{contenu}<span class="wplay" aria-hidden="true"></span>'
            f'<span class="wnote">{html.escape(attendre)}</span></button></div>')


VIGNETTE = re.compile(r'<div class="wframe wfacade"><button class="wposter[^"]*".*?</button></div>', re.S)
EMBED = re.compile(r'data-embed="([^"]*?/embed/([A-Za-z0-9_-]{6,})[^"]*)"')
TITRE = re.compile(r'data-title="([^"]*)"')
DEPART = re.compile(r'data-start="([^"]*)"')
NOTE_ATTENTE = re.compile(r'data-note-wait="([^"]*)"')
NOTE_ATTENTE_LIVE = re.compile(r'data-note-live="([^"]*)"')


def reparer(page: str) -> str:
    """Remet à niveau une vignette posée par une version précédente (data-page, referrer, phrase)."""
    trouve = LANGUE.search(page)
    langue = trouve.group(1)[:2] if trouve else "en"
    langue = langue if langue in NOTES else "en"

    def refaire(m: re.Match[str]) -> str:
        bloc = m.group(0)
        embed, titre, depart = EMBED.search(bloc), TITRE.search(bloc), DEPART.search(bloc)
        if not embed:
            return bloc
        src, video = embed.group(1), embed.group(2)
        attendre, en_cours = NOTES[langue]
        chaine = re.search(r"live_stream\?channel=(UC[A-Za-z0-9_-]+)", src)
        if chaine:
            # déjà un direct de chaîne : on garde le lecteur de la chaîne et son nom
            libelle = next((n for n, i in _chaines().items() if i == chaine.group(1)), "")
            return _bouton(src, f"https://www.youtube.com/channel/{chaine.group(1)}/live",
                           titre.group(1) if titre else "", depart.group(1) if depart else "",
                           attendre, en_cours, libelle)
        return _bouton(src, f"https://www.youtube.com/watch?v={video}",
                       titre.group(1) if titre else "", depart.group(1) if depart else "",
                       attendre, en_cours)

    return VIGNETTE.sub(refaire, page)


def poser_vignette(page: str, prefixe: str) -> str:
    """La vignette de direct dans une page en mémoire (appelée aussi par live_match.py)."""
    trouve = LANGUE.search(page)
    langue = trouve.group(1)[:2] if trouve else "en"
    langue = langue if langue in NOTES else "en"
    debut = DEBUT.search(page)
    debut_txt = debut.group(1) if debut else ""
    if '<div class="wframe"><iframe src="https://www.youtube' not in page and 'class="wposter' not in page:
        return page
    nouveau = CADRE.sub(lambda m: vignette(m, debut_txt, langue), page)
    nouveau = reparer(nouveau)
    nouveau = ramener_sur_la_chaine(nouveau)
    if "lecteur.css" not in nouveau:
        nouveau = nouveau.replace(
            "</body>",
            f'<link rel="stylesheet" href="{prefixe}lecteur.css">'
            f'<script src="{prefixe}lecteur.js" defer></script>\n</body>', 1)
    if "img-src 'self' data: https://i.ytimg.com" not in nouveau:
        nouveau = nouveau.replace("img-src 'self' data:", "img-src 'self' data: https://i.ytimg.com", 1)
    if 'data-start=""' in nouveau and debut_txt:
        nouveau = nouveau.replace('data-start=""', f'data-start="{debut_txt}"')
    return nouveau


CHAINES = {}  # libellé de chaîne YouTube -> identifiant « UC… »


def _chaines() -> dict[str, str]:
    if CHAINES:
        return CHAINES
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import diffusions
    for _mot, _jeu, flux in diffusions.CHANNELS:
        for plateforme, identifiant, libelle in flux:
            if plateforme == "youtube" and identifiant.startswith("UC"):
                CHAINES[libelle] = identifiant
    return CHAINES


def ramener_sur_la_chaine(page: str) -> str:
    """Remplace une vidéo figée par le direct de la chaîne : le match de la semaine dernière n'est plus à l'affiche."""
    chaines = _chaines()
    if not chaines:
        return page

    def chaine_pour(texte: str) -> tuple[str, str] | None:
        for libelle, identifiant in chaines.items():
            if libelle and libelle in texte:
                return identifiant, libelle
        return None

    # 1) la vignette et le lecteur
    for bloc in VIGNETTE.finditer(page):
        morceau = bloc.group(0)
        titre = TITRE.search(morceau)
        trouve = chaine_pour(titre.group(1) if titre else page)
        if not trouve:
            continue
        chaine, libelle = trouve
        attendre = NOTE_ATTENTE.search(morceau)
        en_cours = NOTE_ATTENTE_LIVE.search(morceau)
        depart = DEPART.search(morceau)
        neuf = _bouton(f"https://www.youtube-nocookie.com/embed/live_stream?channel={chaine}",
                       f"https://www.youtube.com/channel/{chaine}/live",
                       titre.group(1) if titre else "",
                       depart.group(1) if depart else "",
                       html.unescape(attendre.group(1)) if attendre else "",
                       html.unescape(en_cours.group(1)) if en_cours else "",
                       libelle)
        page = page.replace(morceau, neuf)
    # 2) les liens « Ouvrir la chaîne » / « Aussi en direct sur »
    for libelle, chaine in chaines.items():
        if libelle and libelle in page:
            page = re.sub(r'https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]+',
                          f'https://www.youtube.com/channel/{chaine}/live', page)
            break
    return page


def main() -> None:
    pages = 0
    for fichier in sorted(ROOT.rglob("*.html")):
        rel = fichier.relative_to(ROOT)
        if SKIP_DIRS.intersection(rel.parts[:-1]):
            continue
        texte = fichier.read_text(errors="ignore")
        if ('<div class="wframe"><iframe src="https://www.youtube' not in texte
                and 'class="wposter' not in texte):
            continue
        trouve = LANGUE.search(texte)
        langue = trouve.group(1)[:2] if trouve else "en"
        langue = langue if langue in NOTES else "en"
        debut = DEBUT.search(texte)
        if not debut:  # sans heure de départ, la phrase d'attente reste par défaut
            debut_txt = ""
        else:
            debut_txt = debut.group(1)
        nouveau = poser_vignette(texte, "../" * (len(rel.parts) - 1))
        if nouveau == texte:
            continue
        prefixe = "../" * (len(rel.parts) - 1)
        if "lecteur.css" not in nouveau:
            nouveau = nouveau.replace(
                "</body>",
                f'<link rel="stylesheet" href="{prefixe}lecteur.css">'
                f'<script src="{prefixe}lecteur.js" defer></script>\n</body>', 1)
        # la vignette est une image YouTube : autorise i.ytimg.com dans img-src
        if "img-src 'self' data: https://i.ytimg.com" not in nouveau:
            nouveau = nouveau.replace("img-src 'self' data:", "img-src 'self' data: https://i.ytimg.com", 1)
        # une page déjà passée avec une heure vide : on la remplit depuis les données structurées
        if 'data-start=""' in nouveau and debut_txt:
            nouveau = nouveau.replace('data-start=""', f'data-start="{debut_txt}"')
        if not ESSAI:
            fichier.write_text(nouveau)
        pages += 1
    print(f"{pages} page(s) avec une vignette de direct")


if __name__ == "__main__":
    main()
