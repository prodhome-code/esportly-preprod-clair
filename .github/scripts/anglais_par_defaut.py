"""Passage de l'accueil d'eSportly en anglais par défaut, en une fois (jetable : à supprimer après la fusion).

/ devient l'accueil anglais (l'ancien en.html), l'accueil français passe sur fr.html et en.html devient une page
de renvoi vers /. Chaque lien d'accueil garde sa destination : les deux cibles sont échangées en un seul passage
dans les pages, le sitemap et leurs données structurées. 404.html est retouché à la main.
Spécification : docs/superpowers/specs/2026-10-27-anglais-par-defaut-design.md

    py -3.13 .github/scripts/anglais_par_defaut.py --essai   # montre ce qui changerait, sans rien écrire
    py -3.13 .github/scripts/anglais_par_defaut.py           # migre
"""
from __future__ import annotations

import posixpath
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://esportly.eu/"
EXCLUDED = {"404.html"}  # retouché à la main : sa marque porte la variante /./


class Refus(Exception):
    """Départ inattendu ou lien d'accueil inconnu : rien n'est écrit."""


# Un lien vers l'accueil français mène désormais à fr.html, un lien vers l'accueil anglais mène à /.
FORWARD = {"./": "fr.html", "../": "../fr.html", "/": "/fr.html", "en.html": "./", "../en.html": "../", "/en.html": "/"}
INVERSE = {new: old for old, new in FORWARD.items()}
ABSOLUTE = {SITE: SITE + "fr.html", SITE + "en.html": SITE}
ABSOLUTE_INVERSE = {new: old for old, new in ABSOLUTE.items()}

HREF = re.compile(r'href="([^"]*)"')
HREF_SINGLE = re.compile(r"href='([^']*)'")
# Une adresse d'accueil absolue n'est échangée que précédée d'un guillemet ou de <loc> et suivie de " < ou #.
HOME_URL = re.compile(r'(?:(?<=")|(?<=<loc>))(https://esportly\.eu/(?:en\.html|fr\.html)?)(?=["<#])')
ANY_HOME_URL = re.compile(r"https://esportly\.eu/(?:en\.html|fr\.html)?(?![\w./%~-])")
UNKNOWN_FORM = re.compile(r"(?:\./|\.\./|/)?index\.html|/\./|(?:\.\./){2,}(?:en\.html)?")
# Le "url" des données structurées d'un accueil est sa propre adresse (§6) : own_url la remet au canonical après l'échange.
JSON_LD_URL = re.compile(r'("url":\s*")https://esportly\.eu/(?:fr\.html)?(")')
ESPORTLY_URL_KEY = re.compile(r'"url":\s*"(https://esportly\.eu/[^"]*)"')


def own_url(text: str, canonical: str) -> str:
    return JSON_LD_URL.sub(lambda m: m.group(1) + canonical + m.group(2), text)


def _resolves_home(target: str, depth: int) -> bool:
    """Vrai si le chemin, une fois normalisé depuis un fichier de cette profondeur, désigne un accueil."""
    path = target.partition("?")[0]
    if not path:
        return False
    base = "/".join(["d"] * depth) or "."
    resolved = posixpath.normpath(path) if path.startswith("/") else posixpath.normpath(posixpath.join(base, path))
    return resolved.lstrip("/") in ("", ".", "en.html", "index.html", "fr.html")


def _forms(depth: int) -> set[str]:
    """Valeurs de href qui désignent un accueil selon la profondeur du fichier (0 = racine, 1 = sous-dossier)."""
    forms = {"/", "/en.html"}
    if depth == 0:
        forms |= {"./", "en.html"}
    elif depth == 1:
        forms |= {"../", "../en.html"}
    return forms


def _rewrite(text: str, table: dict[str, str], absolute: dict[str, str], valid: set[str]) -> tuple[str, int]:
    count = 0

    def relative(m: re.Match) -> str:
        nonlocal count
        target, hash_, anchor = m.group(1).partition("#")
        if target not in valid:
            return m.group(0)
        count += 1
        return f'href="{table[target]}{hash_}{anchor}"'

    def address(m: re.Match) -> str:
        nonlocal count
        if m.group(1) not in absolute:
            return m.group(0)
        count += 1
        return absolute[m.group(1)]

    return HOME_URL.sub(address, HREF.sub(relative, text)), count


def swap_links(text: str, depth: int) -> tuple[str, int]:
    """Échange les deux cibles d'accueil en une seule substitution ; rend le nouveau texte et le nombre de liens."""
    return _rewrite(text, FORWARD, ABSOLUTE, _forms(depth))


def unswap_links(text: str, depth: int) -> str:
    """Échange inverse (fr.html → ./, ./ → en.html…) : sert à prouver que seuls les liens d'accueil ont changé."""
    return _rewrite(text, INVERSE, ABSOLUTE_INVERSE, {FORWARD[f] for f in _forms(depth)})[0]


def unknown_variants(text: str, depth: int) -> list[str]:
    """Liens d'accueil que l'échange ne sait pas traiter : à signaler, jamais à échanger en silence."""
    found = []
    for m in HREF.finditer(text):
        target = m.group(1).partition("#")[0]
        if ((target in FORWARD or _resolves_home(target, depth)) and target not in _forms(depth)) or UNKNOWN_FORM.fullmatch(target):
            found.append(m.group(0))
    for m in HREF_SINGLE.finditer(text):
        target = m.group(1).partition("#")[0]
        if target in FORWARD or UNKNOWN_FORM.fullmatch(target) or _resolves_home(target, depth):
            found.append(m.group(0))
    for m in ANY_HOME_URL.finditer(text):
        before, after = text[max(0, m.start() - 5):m.start()], text[m.end():m.end() + 1]
        if m.group(0).endswith("fr.html") or not ((before.endswith('"') or before.endswith("<loc>")) and after in ('"', "<", "#")):
            found.append(re.sub(r"\s+", " ", text[max(0, m.start() - 20):m.end() + 20]))
    return found


# Les 5 accueils après la migration (nom final -> langue) et le jeu hreflang commun à tous (§5 de la spec).
HOMES = {"index.html": "en", "fr.html": "fr", "es.html": "es", "de.html": "de", "pt.html": "pt-BR"}
HREFLANGS = {"fr": SITE + "fr.html", "en": SITE, "es": SITE + "es.html", "de": SITE + "de.html",
             "pt-BR": SITE + "pt.html", "x-default": SITE}
LANG = re.compile(r'<html lang="([^"]*)"')
CANONICAL = re.compile(r'<link rel="canonical" href="([^"]*)"')
ALTERNATE = re.compile(r'<link rel="alternate" hreflang="([^"]*)" href="([^"]*)"')
LOC = re.compile(r"<loc>([^<]*)</loc>")

REDIRECT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; base-uri 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url=./">
<title>eSportly</title>
<link rel="canonical" href="https://esportly.eu/">
<link rel="icon" href="embleme.svg" type="image/svg+xml">
</head>
<body><p><a href="./">eSportly</a></p></body>
</html>
"""


def check_start_state(root: Path) -> None:
    """Refuse de tourner si la migration est déjà faite (ou à moitié) ou si le départ n'est pas celui attendu."""
    if (root / "fr.html").exists():
        raise Refus("fr.html existe déjà : la migration semble déjà faite")
    for name, lang in (("index.html", "fr"), ("en.html", "en")):
        path = root / name
        if not path.is_file():
            raise Refus(f"{name} est introuvable")
        if f'<html lang="{lang}"' not in path.read_bytes().decode("utf-8"):
            raise Refus(f'{name} n\'est pas en lang="{lang}" : la migration semble déjà faite')


def renvoi_page() -> str:
    """Contenu du nouvel en.html : un renvoi vers / pour l'ancienne adresse de l'accueil anglais."""
    return REDIRECT_PAGE


def set_homes_lastmod(sitemap: str, today: str) -> str:
    """Met à jour le lastmod des 5 accueils seulement (les fins de ligne du sitemap sont conservées)."""
    for name in HOMES:
        url = SITE if name == "index.html" else SITE + name
        sitemap = re.sub(rf"(<loc>{re.escape(url)}</loc>\s*<lastmod>)[^<]*(</lastmod>)",
                         lambda m: m.group(1) + today + m.group(2), sitemap)
    return sitemap


def check_postconditions(files: dict[str, str]) -> list[str]:
    """Contrôles avant écriture sur les contenus sous leur nom final ; rend la liste des problèmes (vide si tout va bien)."""
    problems = []
    for name, lang in HOMES.items():
        text = files.get(name)
        if text is None:
            problems.append(f"fichier {name} : absent")
            continue
        found_lang, found_canonical = LANG.search(text), CANONICAL.search(text)
        if not found_lang or found_lang.group(1) != lang:
            problems.append(f'lang {name} : attendu "{lang}", trouvé "{found_lang and found_lang.group(1)}"')
        if not found_canonical or found_canonical.group(1) != HREFLANGS[lang]:
            problems.append(f"canonical {name} : attendu {HREFLANGS[lang]}, trouvé {found_canonical and found_canonical.group(1)}")
        if dict(ALTERNATE.findall(text)) != HREFLANGS:
            problems.append(f"hreflang {name} : le jeu (avec son auto-référence) n'est pas celui des 5 accueils")
        for found_url in ESPORTLY_URL_KEY.findall(text):
            if found_url != HREFLANGS[lang]:
                problems.append(f"url {name} : le \"url\" JSON-LD est {found_url} au lieu de {HREFLANGS[lang]}")
    sitemap = files.get("sitemap.xml")
    if sitemap is None:
        problems.append("sitemap : fichier absent")
    else:
        locs = LOC.findall(sitemap)
        if SITE + "en.html" in locs:
            problems.append(f"sitemap : {SITE}en.html ne doit plus y figurer")
        for wanted in (SITE, SITE + "fr.html"):
            if wanted not in locs:
                problems.append(f"sitemap : {wanted} est absente")
    return problems


def _scope(root: Path) -> list[Path]:
    """Fichiers concernés : tous les *.html et les *.xml de la racine, hors dossiers cachés et 404.html."""
    paths = list(root.rglob("*.html")) + list(root.glob("*.xml"))
    return sorted(p for p in paths
                  if not any(part.startswith(".") for part in p.relative_to(root).parts)
                  and p.relative_to(root).as_posix() not in EXCLUDED)


def migrate(root: Path, today: str, trial: bool) -> tuple[int, int]:
    """Rend (fichiers changés, liens échangés). Tout est calculé et contrôlé en mémoire avant la moindre écriture."""
    check_start_state(root)
    original, contents, unknown, swapped = {}, {}, [], 0
    for path in _scope(root):
        name = path.relative_to(root).as_posix()
        depth = name.count("/")
        original[name] = path.read_bytes().decode("utf-8")
        unknown += [f"  {name} : {found}" for found in unknown_variants(original[name], depth)]
        contents[name], count = swap_links(original[name], depth)
        swapped += count
        if name == "sitemap.xml":
            contents[name] = set_homes_lastmod(contents[name], today)
    if unknown:
        raise Refus("liens d'accueil de forme inconnue :\n" + "\n".join(unknown))
    contents["index.html"] = own_url(contents["index.html"], SITE + "fr.html")
    contents["en.html"] = own_url(contents["en.html"], SITE)
    final = {**contents, "fr.html": contents["index.html"], "index.html": contents["en.html"], "en.html": renvoi_page()}
    if problems := check_postconditions(final):
        raise Refus("contrôles avant écriture : " + "; ".join(problems))
    changed = {name: text for name, text in contents.items() if text != original[name]}
    if not trial:
        for name, text in changed.items():
            (root / name).write_text(text, encoding="utf-8", newline="")
        (root / "index.html").rename(root / "fr.html")
        (root / "en.html").rename(root / "index.html")
        (root / "en.html").write_text(renvoi_page(), encoding="utf-8", newline="")
    return len(changed), swapped


def main(argv: list[str], root: Path = ROOT) -> int:
    trial = "--essai" in argv
    try:
        changed, swapped = migrate(root, date.today().isoformat(), trial)
    except Refus as refused:
        print(f"Refus : {refused}", file=sys.stderr)
        return 1
    print(f"{changed} fichier(s) {'à changer' if trial else 'changé(s)'}, {swapped} lien(s) d'accueil échangé(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
