"""Inventaire des pages publiques du site eSportly pour le skill titres-seo : un CSV (UTF-8 avec BOM, « ; ») avec, par page,
l'adresse publiée, la langue, le title et la description actuels, et le fichier source où les changer.

Usage : py -3.13 .claude/skills/titres-seo/scripts/inventaire.py [sortie.csv]   (depuis la racine du site)
Sans argument, écrit docs/seo/inventaire-titres.csv. Les pages noindex, les renvois et les pages techniques sont laissés de côté.
"""
import csv
import html
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[4]
URL = "https://esportly.eu/"
SKIP = {"404.html", "en.html", "match.html", "check-email.html", "merci.html", "thanks.html", "verifie.html", "desinscrit.html",
        "unsubscribed.html", "inscription-erreur.html", "signup-error.html", "tv-equipes.html"}
# Les pages fr, es, de et pt-BR sont sous leur sous-dossier de langue depuis le 1er novembre 2026 ; l'anglais reste à la racine.
FOLDERS = ("", "fr", "es", "de", "pt", "blog", "fr/blog", "es/blog", "de/blog", "pt/blog", "fr/equipes", "teams", "fr/jeux", "games",
           "es/juegos", "de/spiele", "pt/jogos", "fonctions", "appareils")
# D'où vient le title d'une page : seo/titres.json pour toutes (lu par les générateurs, appliqué aux pages de jeux et
# d'équipes par titres_seo.py) ; les accueils et pages légales gardent le leur.
SOURCE = "seo/titres.json (site_chrome.seo dans les générateurs ; titres_seo.py pour jeux et équipes)"


def public_url(rel: str) -> str:
    if rel == "index.html":
        return URL
    return URL + (rel[:-5] if rel.endswith(".html") else rel)


def meta(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.S)
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def pages():
    for folder in FOLDERS:
        base = SITE / folder if folder else SITE
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.html")):
            rel = path.relative_to(SITE).as_posix()
            if rel in SKIP:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r'<meta name="robots" content="[^"]*noindex', text) or 'http-equiv="refresh"' in text:
                continue
            yield {
                "URL": public_url(rel), "Langue": meta(text, r'<html[^>]*\blang="([^"]+)"'),
                "TITLE": meta(text, r"<title>(.*?)</title>"), "DESCRIPTION": meta(text, r'<meta name="description" content="([^"]*)"'),
                "New TITLE": "", "nb car title": "", "New DESCRIPTION": "", "nb car description": "", "Mots-clés retenus": "",
                "Source": SOURCE, "nb car TITLE actuel": "", "nb car DESCRIPTION actuelle": "",
            }


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else SITE / "docs" / "seo" / "inventaire-titres.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = list(pages())
    for row in rows:
        row["nb car TITLE actuel"], row["nb car DESCRIPTION actuelle"] = len(row["TITLE"]), len(row["DESCRIPTION"])
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    by_lang = {}
    for row in rows:
        by_lang[row["Langue"]] = by_lang.get(row["Langue"], 0) + 1
    print(f"{len(rows)} pages → {out.relative_to(SITE).as_posix()} ; par langue : " + ", ".join(f"{k} {v}" for k, v in sorted(by_lang.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
