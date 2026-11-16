"""Détection de langue : charge /langue.js dans le <head> de chaque page publique.

Le script redirige l'accueil anglais (/) vers la langue du navigateur (fr/es/de/pt) sauf si un choix
manuel a été retenu (cookie « lang »), et retient le choix fait en cliquant sur une langue du
sélecteur. Les pages de redirection (http-equiv="refresh") sont laissées telles quelles.
Rejouable : une page qui a déjà le script n'est pas touchée.

Lancé à la main : python3 .github/scripts/langue_partout.py   (--check pour lister seulement).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}
TAG = '<script src="/langue.js"></script>'


def apply(page: str) -> str:
    if TAG in page or 'http-equiv="refresh"' in page:
        return page
    head = page.find("</head>")
    if head < 0:
        return page
    return page[:head] + TAG + page[head:]


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
