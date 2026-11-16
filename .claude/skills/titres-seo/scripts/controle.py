"""Contrôle des titles et métadescriptions SEO d'un CSV du site eSportly : signale les lignes à reprendre, ne réécrit rien.

Usage : py -3.13 .claude/skills/titres-seo/scripts/controle.py <fichier.csv>
Colonnes attendues : URL, Langue (fr, en, es, de, pt-BR), TITLE et DESCRIPTION (actuels), New TITLE, nb car title,
New DESCRIPTION, nb car description, Mots-clés retenus. Règles : .claude/skills/titres-seo/regles.md (title de 55 à 63 caractères
sans marque en suffixe ; description de 120 à 155).
"""
import csv
import io
import re
import sys
import unicodedata
from collections import namedtuple
from urllib.parse import urlsplit

COL_URL, COL_LANG = "URL", "Langue"
COL_OLD, COL_OLD_DESC = "TITLE", "DESCRIPTION"
COL_NEW, COL_COUNT = "New TITLE", "nb car title"
COL_NEW_DESC, COL_COUNT_DESC = "New DESCRIPTION", "nb car description"
COL_KW = "Mots-clés retenus"
COLUMNS = (COL_URL, COL_LANG, COL_OLD, COL_OLD_DESC, COL_NEW, COL_COUNT, COL_NEW_DESC, COL_COUNT_DESC, COL_KW)
REQUIRED = (COL_URL, COL_LANG, COL_NEW, COL_NEW_DESC)

BRAND = " – eSportly"
TITLE_MIN, TITLE_MAX = 55, 63
DESC_MIN, DESC_MAX = 120, 155
BRAND_WORDS = {"esportly"}

# Mots vides (jamais comptés comme répétés, toujours admis) et mots interdits, par langue. Les interdits sont des mots
# entiers, en minuscules sans accents ; « — » et « ! » sont interdits partout.
STOPWORDS = {
    "fr": {"de", "du", "des", "la", "le", "les", "l", "d", "et", "a", "au", "aux", "en", "pour", "sur", "un", "une", "ou", "son", "sa", "ses"},
    "en": {"the", "a", "an", "and", "of", "for", "to", "in", "on", "with", "your", "its", "or", "at", "by"},
    "es": {"de", "del", "la", "el", "los", "las", "y", "a", "en", "para", "con", "un", "una", "por", "o", "su", "sus", "al"},
    "de": {"der", "die", "das", "und", "fur", "mit", "von", "zu", "im", "in", "ein", "eine", "des", "dem", "den", "oder", "am"},
    "pt-BR": {"de", "do", "da", "dos", "das", "e", "a", "o", "os", "as", "em", "para", "com", "um", "uma", "no", "na", "ou", "seu", "sua"},
}
FORBIDDEN = {
    "fr": {"decouvrez", "decouvrir", "meilleur", "meilleurs", "meilleure", "incontournable", "ideal", "officiel", "gratuitement"},
    "en": {"discover", "best", "ultimate", "official", "top", "amazing"},
    "es": {"descubre", "descubrir", "mejor", "mejores", "oficial", "increible"},
    "de": {"entdecke", "entdecken", "beste", "besten", "offizielle", "offiziell", "ultimativ", "ultimative"},
    "pt-BR": {"descubra", "descobrir", "melhor", "melhores", "oficial", "incrivel"},
}
LANGS = tuple(STOPWORDS)

Issue = namedtuple("Issue", ["line", "message"])


class CsvError(Exception):
    """Fichier inexploitable : colonne manquante ou aucune ligne."""


def normalize(text):
    """Mots en minuscules, sans accents ni ponctuation."""
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return [w for w in re.split(r"[^a-z0-9]+", plain.lower()) if w]


def _stem(word):
    """Singulier approximatif : « matchs » et « match » se valent."""
    return word[:-1] if len(word) > 3 and word[-1] in "sx" else word


def _lang(row):
    return (row.get(COL_LANG) or "").strip()


def _stopwords(row):
    return STOPWORDS.get(_lang(row), set())


def allowed_words(row):
    """Mots admis dans un title : chemin de l'URL, title et description actuels (ils viennent de la page), mots-clés
    retenus, marque et mots vides."""
    path = urlsplit((row.get(COL_URL) or "").strip()).path
    keywords = re.sub(r"\([^)]*\)", " ", row.get(COL_KW) or "")
    words = normalize(path) + normalize(row.get(COL_OLD)) + normalize(row.get(COL_OLD_DESC)) + normalize(keywords)
    return {_stem(w) for w in words} | BRAND_WORDS | _stopwords(row)


def _forbidden(row, text):
    """Les mots interdits de la langue, rendus comme ils sont écrits (« Découvrez » → découvrez), puis « — » et « ! »."""
    banned = FORBIDDEN.get(_lang(row), set())
    words = [w.lower() for w in re.findall(r"[^\W\d_]+", text) if normalize(w) and normalize(w)[0] in banned]
    found = [f"interdit : {w}" for w in dict.fromkeys(words)]
    found += [f"interdit : {sign}" for sign in ("—", "!") if sign in text]
    return found


def _count(row, column, actual, what):
    count = (row.get(column) or "").strip()
    if count and count != str(actual):
        return [f"{column} indique {count}, {what} en fait {actual}"]
    return []


def check_title(row):
    title = row.get(COL_NEW) or ""
    if not title.strip():
        return [f"{COL_NEW} vide"]
    issues = []
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        issues.append(f"longueur {len(title)} hors de {TITLE_MIN}-{TITLE_MAX}")
    if title != title.strip() or "  " in title:
        issues.append("espace en trop (début, fin ou double)")
    if title.rstrip().endswith(BRAND.strip()):
        issues.append(f"finit par « {BRAND.strip()} » (marque en suffixe interdite)")
    elif "esportly" in normalize(title):
        issues.append("marque dans le title (réservée aux accueils)")
    issues += _forbidden(row, title)

    seen, stop, previous = set(), _stopwords(row), None
    for word in normalize(title):
        if word in stop:
            continue
        if word in seen and word != previous:  # « Bang Bang » (libellé d'un jeu) n'est pas une répétition
            issues.append(f"mot répété : {word}")
        seen.add(word)
        previous = word

    if (row.get(COL_KW) or "").strip():
        allowed = allowed_words(row)
        for word in dict.fromkeys(normalize(title)):
            if word not in allowed and _stem(word) not in allowed:
                issues.append(f"absent de l'URL, de la page et des mots-clés : {word}")
    return issues + _count(row, COL_COUNT, len(title), "le title")


def check_description(row):
    desc = row.get(COL_NEW_DESC) or ""
    if not desc.strip():
        return [f"{COL_NEW_DESC} vide"]
    issues = []
    if not DESC_MIN <= len(desc) <= DESC_MAX:
        issues.append(f"longueur {len(desc)} hors de {DESC_MIN}-{DESC_MAX}")
    if desc != desc.strip() or "  " in desc:
        issues.append("espace en trop (début, fin ou double)")
    if not desc.rstrip().endswith("."):
        issues.append("ne finit pas par un point")
    issues += _forbidden(row, desc)
    return issues + _count(row, COL_COUNT_DESC, len(desc), "la description")


def _read_text(path):
    """UTF-8 (avec ou sans BOM), sinon Windows-1252 comme les CSV d'Excel français."""
    with open(path, "rb") as f:
        data = f.read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def read_rows(path):
    text = _read_text(path)
    header = text.splitlines()[0] if text else ""
    delimiter = max(",;\t", key=header.count)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    reader.fieldnames = [name.strip() for name in reader.fieldnames or []]
    missing = [col for col in REQUIRED if col not in reader.fieldnames]
    if missing:
        raise CsvError("colonne manquante : " + ", ".join(missing))
    rows = []
    for line, row in enumerate(reader, start=2):
        if not (row.get(COL_URL) or "").strip():
            continue
        row["_line"] = line
        rows.append(row)
    return rows


def check_duplicates(rows, column, what):
    first_line, issues = {}, []
    for row in rows:
        key = (row.get(column) or "").strip().lower()
        if not key:
            continue
        if key in first_line:
            other = first_line[key]
            issues.append(Issue(other, f"{what} identique à la ligne {row['_line']}"))
            issues.append(Issue(row["_line"], f"{what} identique à la ligne {other}"))
        else:
            first_line[key] = row["_line"]
    return issues


def check_file(path):
    rows = read_rows(path)
    if not rows:
        raise CsvError("aucune ligne lue (colonne URL vide ?)")
    issues = []
    for row in rows:
        if _lang(row) not in LANGS:
            issues.append(Issue(row["_line"], f"langue inconnue : {_lang(row)} ({', '.join(LANGS)})"))
        issues += [Issue(row["_line"], msg) for msg in check_title(row) + check_description(row)]
    issues += check_duplicates(rows, COL_NEW, "title") + check_duplicates(rows, COL_NEW_DESC, "description")
    return sorted(issues)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    try:
        issues = check_file(argv[1])
    except CsvError as error:
        print(f"Fichier inexploitable : {error}")
        return 2
    for issue in issues:
        print(f"ligne {issue.line} : {issue.message}")
    lines = len({i.line for i in issues})
    print(f"{len(issues)} problème(s) sur {lines} ligne(s)." if issues else "Aucun problème.")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
