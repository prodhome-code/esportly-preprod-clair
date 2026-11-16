"""Mesure d'audience Google Analytics sur toutes les pages du site (analytics.js, chargé seulement si le visiteur accepte).

Pour chaque page publique : la CSP s'élargit juste de ce que Google Analytics demande (script-src, img-src, connect-src) et la page
reçoit <script src="/analytics.js" defer></script> avant </body>. Les widgets (petits cadres intégrés ailleurs) et les pages de
redirection sont laissés tels quels ; les pages en noindex (équipes, remerciements) sont mesurées comme les autres. Le script est rejouable sans effet : une page déjà en règle n'est pas touchée. Il est lancé à la fin des tâches
planifiées (matchs.yml, bascule.yml), après les scripts qui fabriquent des pages à partir de modèles, pour que rien ne s'y perde.

Lancé à la main : python3 .github/scripts/analytics.py   (ajouter --check pour seulement lister les pages à mettre à jour).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = '<script src="/analytics.js" defer></script>'
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}
CSP_META = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"')
GOOGLE = {
    "script-src": ("'self'", "https://www.googletagmanager.com"),
    "img-src": ("https://*.google-analytics.com", "https://*.googletagmanager.com"),
    "connect-src": ("https://*.google-analytics.com", "https://*.analytics.google.com", "https://*.googletagmanager.com"),
}


def widen(policy: str) -> str:
    """La CSP avec les sources de Google Analytics ajoutées à chaque directive de GOOGLE (créée si elle manque, 'none' remplacé)."""
    for name, tokens in GOOGLE.items():
        found = re.search(rf"(?<![\w-]){name}(?![\w-])([^;]*)", policy)
        if found is None:
            directive = f"{name} {' '.join(tokens)}"
            base = re.search(r"base-uri", policy)
            policy = policy[:base.start()] + directive + "; " + policy[base.start():] if base else f"{policy}; {directive}"
            continue
        current = [t for t in found.group(1).split() if t != "'none'"]
        merged = current + [t for t in tokens if t not in current]
        policy = policy[:found.start()] + f"{name} {' '.join(merged)}" + policy[found.end():]
    return policy


def apply(page: str) -> str:
    """La page avec la CSP élargie et la balise de analytics.js ; inchangée si c'est une page de redirection."""
    if 'http-equiv="refresh"' in page:
        return page
    meta = CSP_META.search(page)
    body = page.rfind("</body>")
    if meta is None or body < 0:
        return page
    page = page[:meta.start(1)] + widen(meta.group(1)) + page[meta.end(1):]
    if TAG not in page:
        eol = "\r\n" if "\r\n" in page else "\n"
        body = page.rfind("</body>")
        page = page[:body] + TAG + eol + page[body:]
    return page


def pages(root: Path = ROOT):
    for path in sorted(root.rglob("*.html")):
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
