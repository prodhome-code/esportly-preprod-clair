"""QR code flottant sur ordinateur, en bas à gauche de toutes les pages du site (qr-flottant.css).

Sur un écran large avec souris, un petit encadré « Scanne ce code avec ton iPhone » reste en bas à
gauche, quelle que soit la page ; sur téléphone et tablette il n'apparaît pas. L'encadré porte
maintenant un petit iPhone qui flotte et une ligne de balayage sur le QR ; il charge aussi
/app-store-qr.js, qui ouvre une modal QR quand on clique sur un badge App Store (ordinateur).
L'image est /qr-app-store.svg (l'app est sortie). Les widgets et les pages de redirection sont
laissés tels quels. Le script est rejouable : un encadré déjà là est remplacé par la version du jour.

Lancé à la main : python3 .github/scripts/qr_ordinateur.py   (--check pour seulement lister).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}
LINK = '<link rel="stylesheet" href="/qr-flottant.css">'
SCRIPT = '<script src="/app-store-qr.js" defer></script>'
# Le texte de l'accueil, sans « bêta » : il vaut aussi après la bascule vers l'App Store.
TEXTS = {
    "fr": "Sur ordinateur&nbsp;? Scanne ce code avec ton iPhone pour ouvrir eSportly.",
    "en": "On a computer? Scan this code with your iPhone to open eSportly.",
    "es": "¿En el ordenador? Escanea este código con tu iPhone para abrir eSportly.",
    "de": "Am Computer? Scanne den Code mit deinem iPhone, um eSportly zu öffnen.",
    "pt": "No computador? Escaneie o código com seu iPhone para abrir eSportly.",
}
LANG = re.compile(r'<html[^>]*\blang="([A-Za-z-]+)"')
QRFIX = re.compile(r'<div class="qrfix">.*?</div>', re.S)
# Un petit iPhone stylisé (cadre, encoche, bouton) : rappelle vers quoi le code mène.
PHONE = ('<svg class="qrfix-phone" viewBox="0 0 24 44" width="24" height="44" aria-hidden="true">'
         '<rect x="1" y="1" width="22" height="42" rx="5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
         '<rect x="8.5" y="4" width="7" height="1.4" rx="0.7" fill="currentColor"/>'
         '<circle cx="12" cy="39.5" r="1.2" fill="none" stroke="currentColor" stroke-width="1.2"/>'
         '</svg>')


def box(page: str) -> str:
    """L'encadré (sans le <link> ni le <script>), dans la langue de la page (l'anglais à défaut)."""
    found = LANG.search(page)
    text = TEXTS.get(found.group(1).lower()[:2], TEXTS["en"]) if found else TEXTS["en"]
    return ('<div class="qrfix">'
            '<span class="qrfix-qrwrap"><img src="/qr-app-store.svg" alt="" width="76" height="76" loading="lazy">'
            '<span class="qrfix-scan" aria-hidden="true"></span></span>'
            f'<span class="qrfix-txt"><span class="qrfix-logo"><img src="/embleme.svg" alt="" width="22" height="22" loading="lazy"><b><i>e</i>Sportly</b></span><span>{text}</span></span>'
            f'{PHONE}'
            '</div>')


def apply(page: str) -> str:
    """La page avec l'encadré (remplacé s'il existait déjà) ; inchangée si page de redirection ou sans </body>."""
    body = page.rfind("</body>")
    if 'http-equiv="refresh"' in page or body < 0:
        return page
    new = box(page)
    if 'class="qrfix"' in page:
        page = QRFIX.sub(lambda _: new, page, count=1)
    else:
        eol = "\r\n" if "\r\n" in page else "\n"
        page = page[:body] + LINK + new + eol + page[body:]
    # Le script de la modal, une seule fois (après le <link> s'il est là).
    if SCRIPT not in page:
        if LINK in page:
            page = page.replace(LINK, LINK + SCRIPT, 1)
        else:
            page = page.replace(new, SCRIPT + new, 1)
    return page


def pages(root: Path = ROOT):
    for path in sorted(root.rglob("*.html")):
        # match.html mène à l'app par un vrai bouton, avec son propre QR : pas d'encadré flottant en plus.
        if path.name == "match.html":
            continue
        if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def main(argv: list[str], root: Path = ROOT) -> int:
    changed = []
    for path in pages(root):
        before = path.read_bytes().decode("utf-8")
        after = apply(before)
        if after != before:
            changed.append(path.relative_to(root).as_posix())
            if "--check" not in argv:
                path.write_text(after, encoding="utf-8", newline="")
    print(f"{len(changed)} page(s) {'à mettre à jour' if '--check' in argv else 'mise(s) à jour'}")
    return 1 if changed and "--check" in argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
