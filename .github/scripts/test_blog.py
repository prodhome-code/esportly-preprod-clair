"""Tests de blog.py (partie Blog du site) : validation et visibilité des données, fragments HTML, pages, génération.

    PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONTZPATH=C:\\Users\\horny\\anaconda3\\Lib\\site-packages\\pytz\\zoneinfo \\
        py -3.13 -m unittest discover -s .github/scripts -p "test_blog.py" -v
"""
import base64
import contextlib
import hashlib
import html
import http.client
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

import actualites as an
import bascule_appstore
import site_chrome
import blog


def section(cite=("s1",), **changes) -> dict:
    """Une section valide dans les 5 langues, modifiée par `changes`."""
    entry = {"cite": list(cite), **{lang: {"heading": f"Titre {lang}", "text": ["Un paragraphe."]} for lang in an.LANGS}}
    entry.update(changes)
    return entry


def page(**changes) -> dict:
    """Une fiche de jeu valide (jeu valorant, 3 sections, 1 source), modifiée par `changes`."""
    data = {"kind": "game", "game": "valorant", "date": "2026-10-20", "updated": "2026-10-20",
            "sources": [{"id": "s1", "title": "Site officiel", "url": "https://playvalorant.com/"}],
            "sections": [section() for _ in range(3)],
            **{lang: {"title": f"Titre {lang}", "description": f"Description {lang}."} for lang in an.LANGS}}
    data.update(changes)
    return data


def guide(**changes) -> dict:
    """Un guide valide (kind modifiable : note de version), sans jeu associé sauf si `game` est donné."""
    data = page(**{"kind": "guide", **changes})
    if "game" not in changes:
        del data["game"]
    return data


def entry(page_id: str, **changes) -> dict:
    """Une page telle que la rend load_pages : le dictionnaire de la page plus son identifiant."""
    return {**page(**changes), "id": page_id}


def site(root: Path, games=("league-of-legends", "valorant")) -> Path:
    """Crée les 5 pages (vides) de chaque jeu : games/<id>.html et ses 4 équivalents."""
    for folder in blog.GAME_DIRS.values():
        (root / folder).mkdir(parents=True, exist_ok=True)
        for game in games:
            (root / folder / f"{game}.html").write_text("<html></html>", encoding="utf-8")
    return root


class Validation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = site(Path(tmp.name))
        self.pages = self.root / "blog-src" / "pages"

    def write_page(self, name: str, data) -> None:
        self.pages.mkdir(parents=True, exist_ok=True)
        (self.pages / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def write_data(self, name: str, data) -> None:
        (self.root / "blog-src").mkdir(exist_ok=True)
        (self.root / "blog-src" / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def failure(self, load, *args) -> list[str]:
        with self.assertRaises(blog.BlogError) as caught:
            load(self.root, *args)
        self.assertIsInstance(caught.exception, an.NewsError)
        self.assertEqual(caught.exception.problems, caught.exception.args[0].split("\n"))
        return caught.exception.problems

    def assert_problems(self, found: list[str], file: str, fragments: list[str]) -> None:
        """Chaque fragment figure dans un problème qui commence par le nom du fichier."""
        for fragment in fragments:
            with self.subTest(file=file, fragment=fragment):
                self.assertTrue(any(p.startswith(f"{file} : ") and fragment in p for p in found), f"{file} : {fragment}\n" + "\n".join(found))

    def test_page_valide(self):
        self.assertEqual(blog.load_pages(self.root), {})  # pas de dossier blog-src
        self.pages.mkdir(parents=True)
        self.assertEqual(blog.load_pages(self.root), {})  # dossier vide
        fiche = page()
        self.write_page("valorant", fiche)
        self.assertEqual(blog.load_pages(self.root), {"valorant": {**fiche, "id": "valorant"}})
        # Un guide rattaché à un jeu qui a sa fiche, une note de version sans jeu ; les longueurs se comptent en caractères.
        limite = guide(game="valorant", fr={"title": "é" * 70, "description": "😀" * 160},
                       sections=[section(fr={"heading": "é" * 80, "text": ["é" * 600] * 4})])
        note = guide(kind="release", updated="2026-10-21")
        self.write_page("guide-1", limite)
        self.write_page("note-1", note)
        self.assertEqual(blog.load_pages(self.root), {"valorant": {**fiche, "id": "valorant"},
                                                      "guide-1": {**limite, "id": "guide-1"}, "note-1": {**note, "id": "note-1"}})

    def test_article_de_news_et_couverture(self):
        """kind news (avec ou sans jeu) ; image {"kind": "ia"} ou {"kind": "officielle", credit, url}, avec couvertures/<id>.webp."""
        (self.root / "couvertures").mkdir()
        for name in ("pgl-2026", "algs-2026", "officielle"):
            (self.root / "couvertures" / f"{name}.webp").write_bytes(b"RIFF")
        self.write_page("valorant", page())
        self.write_page("pgl-2026", guide(kind="news", game="valorant", image={"kind": "ia"}))
        self.write_page("algs-2026", guide(kind="news", image={"kind": "ia"}))
        self.write_page("officielle", guide(image={"kind": "officielle", "credit": "Riot Games", "url": "https://riotgames.com/presse"}))
        self.write_page("sans-image", guide(kind="news"))
        self.write_page("reprise", guide(kind="news", game="valorant", image={"kind": "ia", "file": "pgl-2026"}))  # la couverture d'une autre page
        loaded = blog.load_pages(self.root)
        self.assertEqual(sorted(loaded), ["algs-2026", "officielle", "pgl-2026", "reprise", "sans-image", "valorant"])
        self.assertEqual([p["id"] for p in blog.visible_pages(loaded, date(2026, 10, 31))],
                         ["valorant", "algs-2026", "officielle", "pgl-2026", "reprise", "sans-image"])  # les news avec les guides, après les fiches
        cases = {
            "pgl-2026": guide(kind="news", image={"kind": "ia", "credit": "x"}),
            "reprise": guide(kind="news", image={"kind": "ia", "file": "absente"}),
            "reprise-2": guide(kind="news", image={"kind": "ia", "file": "Pas un id"}),
            "algs-2026": guide(kind="news", image={"kind": "photo"}),
            "officielle": guide(image={"kind": "officielle", "credit": "", "url": "http://x"}),
            "sans-fichier": guide(image={"kind": "ia"}),
            "inconnue": guide(image={"kind": "officielle", "credit": "x", "url": "https://x.org", "alt": "y"}),
        }
        for name, data in cases.items():
            self.write_page(name, data)
        found = self.failure(blog.load_pages)
        self.assert_problems(found, "pgl-2026.json", ["image.credit : inutile pour une illustration générée par IA"])
        self.assert_problems(found, "algs-2026.json", ['image : doit être {"kind": "ia"} ou {"kind": "officielle"'])
        self.assert_problems(found, "officielle.json", ["image.credit", "image.url"])
        self.assert_problems(found, "sans-fichier.json", ["image : couvertures/sans-fichier.webp introuvable"])
        self.assert_problems(found, "reprise.json", ["image : couvertures/absente.webp introuvable"])
        self.assert_problems(found, "reprise-2.json", ["image.file : « Pas un id » invalide"])
        self.assert_problems(found, "inconnue.json", ["image : champ inconnu « alt »"])

    def test_chaque_regle_de_validation(self):
        site(self.root, ("league-of-legends", "valorant", "dota-2", "wild-rift"))
        many = [{"id": f"s{n}", "title": f"Source {n}", "url": f"https://exemple.org/{n}"} for n in range(1, 10)]
        sans_de = guide()
        del sans_de["de"]
        del sans_de["sections"][1]["de"]
        sans_jeu = page()
        del sans_jeu["game"]
        textes = guide(sections=[section() for _ in range(5)])
        textes["sections"][0]["en"]["text"] = []
        textes["sections"][1]["en"]["text"] = ["a"] * 5
        textes["sections"][2]["fr"]["text"] = ["bon", "é" * 601]
        textes["sections"][3]["es"]["text"] = ["un <b>texte</b>"]
        textes["sections"][4]["de"]["text"] = ["deux\nlignes"]
        textes["sections"][4]["pt-BR"]["heading"] = "titre\rcassé"
        titre_long = section()
        titre_long["fr"]["heading"] = "x" * 81
        cases = {
            "bon-guide": guide(game="valorant"),
            "champ-inconnu": guide(titel="x"),
            "sans-de": sans_de,
            "article": guide(kind="article"),
            "valorant": sans_jeu,
            "league-of-legends": page(game="valorant"),
            "inconnu": page(game="inconnu"),
            "article-sans-fiche": guide(game="rocket-league"),
            "date-folle": guide(date="2026-13-40"),
            "updated-avant": guide(date="2026-10-28", updated="2026-10-27"),
            "sources-zero": guide(sources=[]),
            "sources-neuf": guide(sources=many),
            "sources-fautives": guide(sections=[section(cite=["s2"])], sources=[
                {"id": "x1", "title": "Un", "url": "https://exemple.org/1"},
                {"id": "s2", "title": "Deux", "url": "http://exemple.org/2"},
                {"id": "s2", "title": "Trois", "url": "javascript:alert(1)"},
                {"id": "s4", "title": "Quatre", "url": "https://a b"},
                {"id": "s5", "title": "Cinq", "url": "https://exemple.org/5"},
                {"id": "s6", "title": "Six", "url": "https://exemple.org/5"},
                {"id": "s7", "title": "Sept", "url": "https://exemple.org/" + "a" * 281},
                {"id": "s8", "title": "x" * 121, "url": "https://exemple.org/8"}]),
            "dota-2": page(game="dota-2", sections=[section(), section()]),
            "wild-rift": page(game="wild-rift", sections=[section() for _ in range(9)]),
            "guide-zero-section": guide(sections=[]),
            "guide-treize-sections": guide(sections=[section() for _ in range(13)]),
            "cite-fautive": guide(sources=many[:5], sections=[section(cite=[]), section(cite=["s9"]),
                                                              section(cite=["s1", "s2", "s3", "s4", "s5"]), section(cite=["s1", "s1"])]),
            "heading-long": guide(sections=[titre_long]),
            "textes-fautifs": textes,
            "entetes-longs": guide(fr={"title": "t" * 71, "description": "d"}, en={"title": "t", "description": "d" * 161}),
        }
        for name, data in cases.items():
            self.write_page(name, data)
        (self.pages / "casse.json").write_text("{", encoding="utf-8")
        (self.pages / "liste.json").write_text("[]", encoding="utf-8")
        found = self.failure(blog.load_pages)
        expected = {
            "champ-inconnu": ["champ inconnu « titel »"],
            "article": ["kind : « article » invalide"],
            "valorant": ["game : manquant"],
            "league-of-legends": ["game : « valorant » doit être égal à l'identifiant « league-of-legends »"],
            "inconnu": ["game : pages introuvables", "games/inconnu.html", "fr/jeux/inconnu.html", "es/juegos/inconnu.html",
                        "de/spiele/inconnu.html", "pt/jogos/inconnu.html"],
            "article-sans-fiche": ["game : « rocket-league » n'a pas de fiche de jeu"],
            "date-folle": ["date : « 2026-13-40 » n'est pas une date AAAA-MM-JJ"],
            "updated-avant": ["updated : 2026-10-27 est avant date 2026-10-28"],
            "sources-zero": ["sources : 0 source(s) (1 à 8 attendues)"],
            "sources-neuf": ["sources : 9 source(s) (1 à 8 attendues)"],
            "sources-fautives": ["sources[0].id : « x1 » invalide", "sources[1].url : doit commencer par https://",
                                 "sources[2].id : « s2 » en double", "sources[2].url : doit commencer par https://",
                                 "sources[3].url : ne doit pas contenir d'espace", "sources[5].url : « https://exemple.org/5 » en double",
                                 "sources[6].url : 301 caractères (300 au plus)", "sources[7].title : 121 caractères (1 à 120 attendus)"],
            "dota-2": ["sections : 2 section(s) (3 à 8 attendues pour une fiche de jeu)"],
            "wild-rift": ["sections : 9 section(s) (3 à 8 attendues pour une fiche de jeu)"],
            "guide-zero-section": ["sections : 0 section(s) (1 à 12 attendues)"],
            "guide-treize-sections": ["sections : 13 section(s) (1 à 12 attendues)"],
            "cite-fautive": ["sections[0].cite : 0 source(s) citée(s) (1 à 4 attendues)", "sections[1].cite[0] : « s9 » n'est pas une source déclarée",
                             "sections[2].cite : 5 source(s) citée(s) (1 à 4 attendues)", "sections[3].cite[1] : « s1 » en double"],
            "heading-long": ["sections[0].fr.heading : 81 caractères (1 à 80 attendus)"],
            "textes-fautifs": ["sections[0].en.text : 0 paragraphe(s) (1 à 4 attendus)", "sections[1].en.text : 5 paragraphe(s) (1 à 4 attendus)",
                               "sections[2].fr.text[1] : 601 caractères (1 à 600 attendus)", "sections[3].es.text[0] : contient « < »",
                               "sections[4].de.text[0] : contient un retour à la ligne", "sections[4].pt-BR.heading : contient un retour à la ligne"],
            "entetes-longs": ["fr.title : 71 caractères (1 à 70 attendus)", "en.description : 161 caractères (1 à 160 attendus)"],
            "casse": ["illisible"],
            "liste": ["doit être un objet"],
        }
        for name, fragments in expected.items():
            self.assert_problems(found, f"{name}.json", fragments)
        # Langue manquante : au premier niveau (problème sans chemin) puis dans une section (avec son chemin), deux règles distinctes.
        self.assertIn("sans-de.json : langue « de » manquante", found)
        self.assertIn("sans-de.json : sections[1] : langue « de » manquante", found)
        self.assertFalse([p for p in found if p.startswith("bon-guide.json")], found)  # un fichier valide n'a aucun problème
        self.assertFalse([p for p in found if p.startswith("sources-neuf.json : sources[")], found)  # et un fichier ne signale que ses fautes

    def test_identifiants(self):
        for name in ("Mauvais", "a b", "x..y", "league-of-legends", "bon-id-2"):
            self.write_page(name, guide())
        found = self.failure(blog.load_pages)
        self.assertEqual(len(found), 4, found)
        for name in ("Mauvais", "a b", "x..y"):
            self.assert_problems(found, f"{name}.json", ["identifiant invalide"])
        self.assert_problems(found, "league-of-legends.json", ["identifiant « league-of-legends » réservé à la fiche du jeu"])

    def test_visibilite_et_ordre(self):
        pages = {p["id"]: p for p in [
            entry("valorant"), entry("zz-jeu"), entry("counter-strike-2"), entry("league-of-legends"), entry("aa-jeu"),
            entry("dota-2", date="2026-10-28", updated="2026-10-28"),
            entry("guide-a", kind="guide", date="2026-10-25", updated="2026-10-25"),
            entry("guide-c", kind="guide", date="2026-10-26", updated="2026-10-26"),
            entry("guide-demain", kind="guide", date="2026-10-28", updated="2026-10-28"),
            entry("guide-b", kind="guide", date="2026-10-26", updated="2026-10-26"),
            entry("guide-today", kind="guide", date="2026-10-27", updated="2026-10-27"),
            entry("note-ancienne", kind="release", date="2026-10-01", updated="2026-10-01")]}
        shown = [p["id"] for p in blog.visible_pages(pages, date(2026, 10, 27))]
        self.assertEqual(shown, ["league-of-legends", "counter-strike-2", "valorant", "aa-jeu", "zz-jeu",
                                 "guide-today", "guide-b", "guide-c", "guide-a", "note-ancienne"])
        self.assertEqual(blog.visible_pages({}, date(2026, 10, 27)), [])

    def test_chaines(self):
        self.assertEqual(blog.load_channels(self.root), {})  # fichier absent
        canal = {"id": "UC" + "a" * 22, "name": "VALORANT Esports", "proof": "https://valorantesports.com/"}
        valide = {"valorant": [canal], "league-of-legends": [{**canal, "id": "UC" + "A1_-" * 5 + "bc"}, {**canal, "id": "UC" + "b" * 22}]}
        self.write_data("channels.json", valide)
        self.assertEqual(blog.load_channels(self.root), valide)
        self.write_data("channels.json", {"valorant": []})
        self.assertEqual(blog.load_channels(self.root), {"valorant": []})
        self.write_data("channels.json", {
            "league-of-legends": [{**canal, "id": "UCabc"}],
            "dota-2": [canal],
            "valorant": [canal, {**canal, "id": "UC" + "b" * 22, "name": "x" * 61}, {**canal, "id": "UC" + "c" * 22, "proof": "http://exemple.org/"},
                         {**canal, "name": "Doublon"}, {**canal, "id": "UC" + "d" * 22, "proof": "https://a b"}, {"id": "UC" + "e" * 22, "nom": "x"}]})
        found = self.failure(blog.load_channels)
        self.assert_problems(found, "channels.json", [
            "league-of-legends[0].id : « UCabc » invalide", "dota-2 : jeu introuvable", "games/dota-2.html",
            "valorant[1].name : 61 caractères (1 à 60 attendus)", "valorant[2].proof : doit commencer par https://",
            "valorant[3].id : « UC" + "a" * 22 + " » en double", "valorant[4].proof : ne doit pas contenir d'espace",
            "valorant[5] : champ inconnu « nom »", "valorant[5].name : manquant", "valorant[5].proof : manquant"])
        self.write_data("channels.json", [])
        self.assert_problems(self.failure(blog.load_channels), "channels.json", ["doit être un objet"])
        (self.root / "blog-src" / "channels.json").write_text("{", encoding="utf-8")
        self.assert_problems(self.failure(blog.load_channels), "channels.json", ["illisible"])

    def test_chaines_include(self):
        canal = {"id": "UC" + "a" * 22, "name": "LoL Esports", "proof": "https://lolesports.com/"}
        autre = lambda lettre, **champs: {**canal, "id": "UC" + lettre * 22, **champs}  # noqa: E731 : une autre chaîne, valide
        # `include` est facultatif : une chaîne sans lui, ou avec une expression valide de 1 à 200 caractères, est acceptée.
        valide = {"valorant": [canal, autre("b", include=r"\bhighlights?\b"), autre("c", include="x"),
                               autre("d", include="x" * 200), autre("e", include=r"\b(?:highlights?|top plays?|best plays?)\b")]}
        self.write_data("channels.json", valide)
        self.assertEqual(blog.load_channels(self.root), valide)
        # Une expression fautive est un problème qui nomme le jeu (chemin) et la chaîne (son nom), sans empêcher de relever les autres.
        self.write_data("channels.json", {
            "valorant": [{**canal, "include": "["}, autre("b", name="VCT", include=""), autre("c", name="Trop longue", include="x" * 201),
                         autre("d", name="Pas un texte", include=5), autre("e", name="Nulle", include=None),
                         autre("f", name="Parenthèse", include="(\\bhighlights"), autre("g", name="Bonne", include="highlights"),
                         autre("h", name="Répétition", include="a{99999999999}"), autre("i", name="Ensemble", include="[[]")],
            "league-of-legends": [autre("h", name="Sans nom", include="*highlights")]})
        found = self.failure(blog.load_channels)
        self.assert_problems(found, "channels.json", [
            "valorant[0].include : expression invalide", "valorant[1].include : 0 caractères (1 à 200 attendus)",
            "valorant[2].include : 201 caractères (1 à 200 attendus)", "valorant[3].include : doit être un texte",
            "valorant[4].include : doit être un texte", "valorant[5].include : expression invalide",
            "valorant[7].include : expression invalide : the repetition number is too large",  # une répétition démesurée lève OverflowError
            "valorant[8].include : expression invalide : Possible nested set",  # un avertissement de `re` : refusé aussi (et sans planter sous -W error)
            "league-of-legends[0].include : expression invalide"])
        names = {0: "LoL Esports", 1: "VCT", 2: "Trop longue", 3: "Pas un texte", 4: "Nulle", 5: "Parenthèse", 7: "Répétition", 8: "Ensemble"}  # 6 : valide
        for index, name in names.items():
            with self.subTest(channel=name):
                self.assertTrue(any(f"valorant[{index}].include : " in p and f"« {name} »" in p for p in found), "\n".join(found))
        self.assertTrue(any("league-of-legends[0].include : " in p and "« Sans nom »" in p for p in found), "\n".join(found))
        self.assertEqual(len(found), 9, found)  # aucun autre problème
        # Un champ inconnu reste refusé, `include` ou pas ; une chaîne sans nom est nommée par son identifiant.
        self.write_data("channels.json", {"valorant": [{**canal, "include": "highlights", "filtre": "x"}, {"id": "UC" + "b" * 22, "include": "["}]})
        found = self.failure(blog.load_channels)
        self.assert_problems(found, "channels.json", ["valorant[0] : champ inconnu « filtre »", "valorant[1].include : expression invalide"])
        self.assertTrue(any("valorant[1].include : " in p and "UC" + "b" * 22 in p for p in found), "\n".join(found))
        self.assertFalse([p for p in found if "valorant[0].include" in p], found)

    def test_topplays(self):
        self.assertEqual(blog.load_topplays(self.root), {})  # fichier absent
        video = {"id": "aB3_-xY9zQ1", "title": "Un clutch à 1 contre 5", "channel": "VALORANT Esports", "published": "2026-10-26"}
        valide = {"valorant": {"fetched": "2026-10-27", "videos": [video, {**video, "id": "ZZZZZZZZZZZ"}]}, "dota-2": {"fetched": "2026-10-27", "videos": []}}
        self.write_data("topplays.json", valide)
        self.assertEqual(blog.load_topplays(self.root), valide)
        self.write_data("topplays.json", {
            "valorant": {"fetched": "hier", "videos": [{**video, "id": "abc"}, {**video, "published": "2026-02-30"}, {**video, "title": ""}]},
            "league-of-legends": {"fetched": "2026-10-27", "videos": [], "extra": 1}})
        found = self.failure(blog.load_topplays)
        self.assert_problems(found, "topplays.json", [
            "valorant.fetched : « hier » n'est pas une date AAAA-MM-JJ", "valorant.videos[0].id : « abc » invalide",
            "valorant.videos[1].published : « 2026-02-30 » n'est pas une date AAAA-MM-JJ", "valorant.videos[2].title : vide",
            "league-of-legends : champ inconnu « extra »"])
        self.write_data("topplays.json", {"valorant": {"fetched": "2026-10-27"}})
        self.assert_problems(self.failure(blog.load_topplays), "topplays.json", ["valorant.videos : manquant"])
        (self.root / "blog-src" / "topplays.json").write_text("{", encoding="utf-8")
        self.assert_problems(self.failure(blog.load_topplays), "topplays.json", ["illisible"])

    def test_topplays_visibles(self):
        videos = [{"id": "aB3_-xY9zQ1", "title": "Un clutch", "channel": "VALORANT Esports", "published": "2026-10-12"}]
        topplays = {"quatorze-jours": {"fetched": "2026-10-13", "videos": videos},
                    "quinze-jours": {"fetched": "2026-10-12", "videos": videos},
                    "aujourdhui": {"fetched": "2026-10-27", "videos": videos},
                    "liste-vide": {"fetched": "2026-10-27", "videos": []}}
        self.assertEqual(blog.visible_topplays(topplays, date(2026, 10, 27)), {"quatorze-jours": videos, "aujourdhui": videos})
        self.assertEqual(blog.visible_topplays({}, date(2026, 10, 27)), {})


class Constantes(unittest.TestCase):
    def test_constantes(self):
        self.assertEqual(len(blog.GAMES), 14)
        self.assertEqual(len(set(blog.GAMES)), 14)
        self.assertEqual(blog.GAMES[:3], ("league-of-legends", "counter-strike-2", "valorant"))
        for table in (blog.GAME_DIRS, blog.BLOG_DIRS, blog.HUBS):
            self.assertEqual(set(table), set(an.LANGS))
            self.assertEqual(len(set(table.values())), 5)
        self.assertEqual(blog.GAME_DIRS["fr"], "fr/jeux")
        self.assertEqual(blog.BLOG_DIRS["pt-BR"], "pt/blog")
        self.assertEqual(blog.HUBS["en"], "blog.html")


# --- Fragments HTML ---------------------------------------------------------------------------------------------

class Reader(HTMLParser):
    """Lit un fragment comme le fait un navigateur : balises avec leurs attributs (entités décodées) et textes."""

    def __init__(self, fragment: str):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.texts: list[str] = []
        self.feed(fragment)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.texts.append(data)

    def names(self) -> list[str]:
        return [tag for tag, _ in self.tags]

    def values(self, tag: str, attr: str) -> list[str]:
        return [attrs[attr] for name, attrs in self.tags if name == tag and attr in attrs]

    def text(self) -> str:
        return "".join(self.texts)

    def shape(self) -> list[tuple[str, list[str]]]:
        """Les balises et les noms de leurs attributs, sans les valeurs : identique quand seul le texte des données change."""
        return [(tag, sorted(attrs)) for tag, attrs in self.tags]


def source(number: int, **changes) -> dict:
    return {"id": f"s{number}", "title": f"Source {number}", "url": f"https://example.org/page-{number}", **changes}


def video(code: str, **changes) -> dict:
    return {"id": code, "title": f"Vidéo {code}", "channel": "VALORANT Esports", "published": "2026-10-12", **changes}


def written(cite, heading: str, *paragraphs: str) -> dict:
    """Une section dont chaque texte porte le code de sa langue, pour vérifier que la bonne langue est rendue."""
    return section(cite, **{lang: {"heading": f"{heading} {lang}", "text": [f"{text} {lang}" for text in paragraphs]} for lang in an.LANGS})


def fiche(game: str, **changes) -> dict:
    """Une fiche de jeu telle que la rend load_pages."""
    return entry(game, game=game, **changes)


def article(page_id: str, day: str, **changes) -> dict:
    """Un guide associé à valorant, dont le titre est « Guide <id> <langue> »."""
    titles = {lang: {"title": f"Guide {page_id} {lang}", "description": f"Résumé {page_id} {lang}."} for lang in an.LANGS}
    return entry(page_id, kind="guide", date=day, updated=day, **{**titles, **changes})


VIDEOS = [video("aB3_-xY9zQ1"), video("ZZZZZZZZZZZ", title="Deuxième"), video("0123456789a", published="2026-10-26")]
NAMES = {"valorant": "Valorant", "league-of-legends": "League of Legends", "counter-strike-2": "Counter-Strike 2"}
HOME = ("../fr.html", "Accueil")
LD_SCRIPT = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
DECLARED = re.compile(r'<link rel="canonical" href="([^"]*)"|<link rel="alternate" hreflang="[^"]*" href="([^"]*)"'
                      r'|<xhtml:link rel="alternate" hreflang="[^"]*" href="([^"]*)"|<meta property="og:url" content="([^"]*)"'
                      r'|<loc>([^<]*)</loc>|"(?:url|item|mainEntityOfPage|@id)":\s*"([^"]*)"')


def declared(text: str) -> list[str]:
    """Adresses déclarées : canonical, hreflang (page et sitemap), og:url, <loc>, url/item/mainEntityOfPage/@id des données structurées."""
    return [next(group for group in found if group) for found in DECLARED.findall(text)]
LABEL_KEYS = ["toc", "ai_image", "credit", "source_link", "kicker", "title", "head", "lead", "grid", "latest", "about", "sources", "checked", "ai", "follow", "see_game", "others",
              "topplays", "topnote", "guide", "play"]
# Note des top plays : ligne « Note des top plays » du tableau de la spec §6, recopiée telle quelle (lecteur au clic, §14).
TOPNOTES = {"en": "Videos from the game's official YouTube channels, ranked by views this week. A video loads from YouTube only when you click it.",
            "fr": "Vidéos des chaînes YouTube officielles du jeu, classées par vues cette semaine. Une vidéo ne se charge depuis YouTube que lorsque tu cliques dessus.",
            "es": "Vídeos de los canales oficiales de YouTube del juego, por vistas esta semana. Un vídeo solo se carga desde YouTube cuando haces clic en él.",
            "de": "Videos der offiziellen YouTube-Kanäle des Spiels, nach Aufrufen dieser Woche sortiert. Ein Video wird erst nach einem Klick von YouTube geladen.",
            "pt-BR": "Vídeos dos canais oficiais do jogo no YouTube, ordenados por visualizações nesta semana. Um vídeo só é carregado do YouTube quando você clica nele."}
# Libellé accessible du bouton de lecture : ligne « Lire » du tableau de la spec §6.
PLAYS = {"en": "Play: {title}", "fr": "Lire : {title}", "es": "Reproducir: {title}", "de": "Abspielen: {title}", "pt-BR": "Reproduzir: {title}"}
FRAME_SRC = "frame-src https://www.youtube-nocookie.com"  # directive ajoutée à la CSP des pages qui affichent des top plays (spec §6, §7 et §14)
WATCH = "https://www.youtube.com/watch?v="  # lien de secours d'une carte de lecture (sans JavaScript, il ouvre YouTube)
LABEL_HOLES = {"credit": {"credit"}, "about": {"game"}, "checked": {"date"}, "follow": {"game"}, "see_game": {"game"}, "guide": {"game"}, "play": {"title"}}
# Classes que les fragments emploient sans que BLOG_STYLE les définisse : les pages modèles du site ont déjà leur règle.
TEMPLATE_CLASSES = {"crumbs", "hero", "big", "kicker", "lead", "glogo", "others", "cta"}


class Labels(unittest.TestCase):
    def test_libelles_complets(self):
        self.assertEqual(set(blog.LABELS), set(an.LANGS))
        for lang in an.LANGS:
            self.assertEqual(set(blog.LABELS[lang]), set(LABEL_KEYS), lang)
            for key in LABEL_KEYS:
                with self.subTest(lang=lang, key=key):
                    value = blog.LABELS[lang][key]
                    self.assertTrue(value.strip())
                    self.assertEqual(set(re.findall(r"\{(\w*)\}", value)), LABEL_HOLES.get(key, set()))
                    self.assertEqual(set(value) & set('<>&"'), set())  # insérés tels quels dans le HTML, y compris dans un attribut
        self.assertEqual({blog.LABELS[lang]["kicker"] for lang in an.LANGS}, {"Blog"})
        self.assertEqual(blog.LABELS["en"]["ai"], "Written with AI assistance and checked against the sources cited.")
        self.assertEqual(blog.LABELS["de"]["checked"].format(date="1 März 2026"), "Geprüft am 1 März 2026")

    def test_textes_du_tableau(self):
        """Quelques valeurs recopiées du tableau « Les textes fixes de la page » et de la section 8 de la spec."""
        labels = blog.LABELS
        self.assertEqual(labels["pt-BR"]["title"], "Os jogos por trás das partidas")
        for lang, note in TOPNOTES.items():
            self.assertEqual(labels[lang]["topnote"], note, lang)
        for lang, play in PLAYS.items():
            self.assertEqual(labels[lang]["play"], play, lang)
        self.assertEqual(labels["fr"]["play"].format(title="Grosse action"), "Lire : Grosse action")
        self.assertEqual(labels["fr"]["follow"].format(game="Valorant"), "Suivre Valorant avec eSportly")
        self.assertEqual(labels["de"]["see_game"].format(game="Dota 2"), "Das kann eSportly für Dota 2")
        self.assertEqual(labels["en"]["about"].format(game="Valorant"), "Articles about Valorant")
        self.assertEqual(labels["fr"]["ai"], "Rédigé avec l'aide de l'IA et vérifié par rapport aux sources citées.")
        self.assertEqual(labels["en"]["guide"], "Guide: {game}, the game and its pro scene →")
        self.assertEqual(labels["fr"]["guide"], "Guide : {game}, le jeu et sa scène pro →")
        self.assertEqual(labels["es"]["guide"], "Guía: {game}, el juego y su escena profesional →")
        self.assertEqual(labels["de"]["guide"], "Ratgeber: {game} und seine Profiszene →")
        self.assertEqual(labels["pt-BR"]["guide"], "Guia: {game}, o jogo e sua cena profissional →")

    def test_libelles_sans_watch(self):
        """Les vidéos sont des cartes de lecture au clic : pas de libellé « Voir sur YouTube », la note ne parle pas de liens, 21 clés."""
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(len(blog.LABELS[lang]), 21)
                self.assertEqual(set(blog.LABELS[lang]), set(LABEL_KEYS))
                self.assertNotIn("watch", blog.LABELS[lang])
                note = blog.LABELS[lang]["topnote"]
                self.assertEqual(note, TOPNOTES[lang])
                for mention in ("link", "lien", "enlace", "öffnen", "ouvre", "abre", "open"):  # liens, ouverture de YouTube
                    self.assertNotIn(mention, note.lower())


class Fragments(unittest.TestCase):
    def test_sections_et_citations(self):
        sources = [source(1), source(2), source(3)]
        sections = [written(["s1", "s2"], "Premier", "Un", "Deux"), written(["s3"], "Deuxième", "Trois"),
                    written(["s2", "s1"], "Troisième", "Quatre")]
        shown = blog.render_sections(entry("valorant", sources=sources, sections=sections), "fr")
        self.assertEqual(re.findall(r'<h2 id="([^"]*)">', shown), ["s1", "s2", "s3"])  # les ancres du sommaire
        self.assertIn('<section class="sec"><h2 id="s1">Premier fr</h2><p>Un fr</p><p>Deux fr</p>'
                      '<p class="cite">Sources : <a href="#src1">[1]</a> <a href="#src2">[2]</a></p></section>', shown)
        self.assertIn('<p class="cite">Sources : <a href="#src3">[3]</a></p>', shown)
        self.assertIn('<p class="cite">Sources : <a href="#src2">[2]</a> <a href="#src1">[1]</a></p>', shown)  # ordre de cite
        order = [shown.index(text) for text in ["Premier fr", "Un fr", "Deux fr", "Deuxième fr", "Trois fr", "Troisième fr", "Quatre fr"]]
        self.assertEqual(order, sorted(order))
        self.assertEqual(Reader(shown).values("a", "href"), ["#src1", "#src2", "#src3", "#src2", "#src1"])
        # Les numéros suivent la position dans « sources » ; le texte est celui de la langue demandée.
        one = blog.render_sections(entry("valorant", sources=sources, sections=[written(["s3"], "A", "B")]), "en")
        self.assertIn('<p class="cite">Sources: <a href="#src3">[3]</a></p>', one)
        self.assertIn('<h2 id="s1">A en</h2>', one)
        self.assertIn('<p class="cite">Fuentes: ', blog.render_sections(entry("valorant", sections=[written(["s1"], "A", "B")]), "es"))

    def test_liste_des_sources(self):
        sources = [source(1, title='A & B "x"', url="https://www.example.org/a?x=1&y=2"), source(2, url="https://example.org:8443/z")]
        shown = blog.render_sources(entry("valorant", sources=sources), "en")
        self.assertTrue(shown.startswith('<h2 id="sources">Sources</h2><ol class="sources"><li id="src1">'))
        reader = Reader(shown)
        self.assertEqual(reader.values("li", "id"), ["src1", "src2"])
        self.assertEqual(reader.values("a", "href"), ["https://www.example.org/a?x=1&y=2", "https://example.org:8443/z"])
        self.assertEqual(reader.values("a", "rel"), ["noopener", "noopener"])
        self.assertEqual(shown.count("<small>example.org</small>"), 2)  # le domaine seul : ni « www. », ni port, ni chemin
        self.assertIn("A &amp; B &quot;x&quot;", shown)
        self.assertTrue(blog.render_sources(entry("valorant", sources=[source(1)]), "de").startswith('<h2 id="sources">Quellen</h2>'))
        # Une adresse sans domaine lisible n'affiche pas de domaine et ne fait pas échouer le rendu.
        for odd in ("https://", "https://[::1"):
            with self.subTest(url=odd):
                self.assertNotIn("<small>", blog.render_sources(entry("valorant", sources=[source(1, url=odd)]), "en"))

    def world(self, bad: bool) -> dict:
        """Les mêmes données avec ou sans texte piégé : seule la valeur des textes change, jamais la forme."""
        def t(plain: str, evil: str) -> str:
            return evil if bad else plain

        url = t("https://example.org/a", "https://example.org/a?x=\"1\"&y='2'<z>")
        sections = [section(("s1",), fr={"heading": t("Titre", "</script><img onerror=x>"), "text": [t("Texte", "<b>\"x\"</b> & 'y'")]})
                    for _ in range(3)]
        header = {"title": t("Titre", "<i>T</i>"), "description": t("Texte", '"D" <u>x</u>')}
        return {
            "url": url,
            "page": entry("valorant", sources=[source(1, title=t("Source", 'A & B "x"'), url=url)], sections=sections, fr=header),
            "videos": [video("aB3_-xY9zQ1", title=t("Titre", '<b>"x"</b>'), channel=t("Chaîne", "<i>c</i>' &"))],
            "names": {"valorant": t("Valorant", 'Val<b>"x"</b>'), "league-of-legends": t("League", "L<o>L &")},
            "home": (t("../fr.html", '../fr.html"><i>'), t("Accueil", '<i>A</i>"')),
            "articles": [article("bo5", "2026-10-25", fr={"title": t("Titre", "<h1>x</h1>"), "description": t("Texte", '"x" & <u>')})],
            "others": [fiche("league-of-legends")],
            "hub": [fiche("valorant", fr=header), article("bo5", "2026-10-25", fr=header)],
        }

    def test_echappement(self):
        renderers = {
            "sections": lambda w: blog.render_sections(w["page"], "fr"),
            "sources": lambda w: blog.render_sources(w["page"], "fr"),
            "videos": lambda w: blog.render_videos(w["videos"], "fr"),
            "page": lambda w: blog.render_guide_main(w["page"], "fr", w["names"], w["home"], w["videos"], w["articles"], w["others"]),
            "accueil": lambda w: blog.render_hub_main("fr", w["hub"], w["names"]),
            "lien": lambda w: blog.render_guide_link(w["page"], "fr", w["names"]["valorant"]),
        }
        plain, evil = self.world(False), self.world(True)
        for name, render in renderers.items():
            with self.subTest(fragment=name):
                good, bad = render(plain), render(evil)
                self.assertEqual(Reader(good).shape(), Reader(bad).shape())  # aucune balise ni attribut de plus
                for raw in ("</script>", "<img onerror", "<i>", "<u>", "<z>", "<o>", '<b>"x"', "onerror=x>"):
                    self.assertNotIn(raw, bad)
                self.assertNotIn("\n", bad)
        # Le texte relu par un navigateur est celui des données, et l'adresse d'une source reste intacte dans son href.
        self.assertIn("</script><img onerror=x>", Reader(renderers["sections"](evil)).text())
        self.assertIn("<b>\"x\"</b> & 'y'", Reader(renderers["sections"](evil)).text())
        self.assertEqual(Reader(renderers["sources"](evil)).values("a", "href"), [evil["url"]])
        self.assertIn('A & B "x"', Reader(renderers["sources"](evil)).text())
        self.assertIn("<b>\"x\"</b>", Reader(renderers["videos"](evil)).text())
        self.assertIn("<i>c</i>' &", Reader(renderers["videos"](evil)).text())
        self.assertIn('Val<b>"x"</b>', Reader(renderers["page"](evil)).text())
        self.assertEqual(Reader(renderers["page"](evil)).values("a", "href")[0], '../fr.html"><i>')
        self.assertEqual(Reader(renderers["lien"](evil)).tags[0][1], {"class": "guide"})
        self.assertIn('Val<b>"x"</b>', Reader(renderers["lien"](evil)).text())

    def test_echappement_des_donnees_structurees(self):
        url = "https://example.org/?a=\"1\"&b='2'</script><script>alert(1)</script><!--"
        title = "T </script><script>alert(1)</script> <!--"
        hostile = entry("valorant", sources=[source(1, url=url)], fr={"title": title, "description": 'D "x" & <b>'})
        crumbs = [("Accueil", "https://esportly.eu/fr.html"), ("Blog", "https://esportly.eu/fr/blog.html"), ("</script>", "https://esportly.eu/x")]
        ld = blog.render_jsonld(hostile, "fr", "https://esportly.eu/fr/blog/valorant.html", crumbs)
        self.assertEqual(ld.count("</"), 2)  # les deux balises fermantes, et rien venu des données
        payloads = LD_SCRIPT.findall(ld)
        self.assertEqual(len(payloads), 2)
        for payload in payloads:
            self.assertNotIn("</", payload)
            self.assertNotIn("<!--", payload)
        data = [json.loads(payload) for payload in payloads]  # toujours du JSON valide une fois extrait
        self.assertEqual(data[0]["citation"], [url])
        self.assertEqual(data[0]["headline"], title)
        self.assertEqual(data[0]["description"], 'D "x" & <b>')
        self.assertEqual(data[1]["itemListElement"][2]["name"], "</script>")
        self.assertNotIn("\n", ld)

    def test_videos(self):
        """Le bloc : titre, une ligne par vidéo (carte de lecture puis légende), puis la note ; aucun lien « Voir sur YouTube »."""
        shown = blog.render_videos(VIDEOS, "en")
        reader = Reader(shown)
        self.assertTrue(shown.startswith('<h2 id="plays">Top plays right now</h2><ul class="topplays"><li class="play">'
                                         f'<a class="video" href="{WATCH}aB3_-xY9zQ1" data-id="aB3_-xY9zQ1" aria-label="Play: Vidéo aB3_-xY9zQ1">'
                                         '<span class="btn" aria-hidden="true">▶</span></a><p class="legend"><b>Vidéo aB3_-xY9zQ1</b>'), shown)
        self.assertEqual(reader.names().count("li"), 3)
        self.assertEqual(reader.names().count("a"), 3)  # une carte par vidéo, rien d'autre
        self.assertEqual(reader.names().count("iframe"), 0)  # aucun lecteur avant le clic
        self.assertEqual(reader.names().count("h2"), 1)
        self.assertEqual(reader.names().count("ul"), 1)
        self.assertNotIn("Watch on YouTube", shown)
        self.assertIn("VALORANT Esports", shown)
        self.assertIn('<time datetime="2026-10-12">12 October 2026</time>', shown)
        self.assertIn("26 October 2026", shown)
        self.assertTrue(shown.endswith(f'<p class="topnote">{blog.LABELS["en"]["topnote"]}</p>'))
        self.assertEqual(blog.LABELS["en"]["topnote"], TOPNOTES["en"])
        french = blog.render_videos(VIDEOS[:1], "fr")
        for text in ("Top plays du moment", "12 octobre 2026", TOPNOTES["fr"]):
            self.assertIn(text, french)
        for gone in ("Voir sur YouTube", "Les liens ouvrent YouTube."):
            self.assertNotIn(gone, french)
        self.assertEqual(blog.render_videos([], "en"), "")

    def test_carte_de_lecture(self):
        """Chaque vidéo est une carte sans ressource de tiers (lien de secours vers YouTube, data-id, libellé accessible, bouton),
        puis une légende : titre, chaîne et date en texte. Aucune iframe, aucune image, aucune autre adresse de tiers avant le clic."""
        shown = blog.render_videos(VIDEOS, "en")
        reader = Reader(shown)
        cards = [attrs for tag, attrs in reader.tags if tag == "a"]
        self.assertEqual(len(cards), len(VIDEOS))
        for attrs, one in zip(cards, VIDEOS):
            self.assertEqual(attrs, {"class": "video", "href": f"{WATCH}{one['id']}", "data-id": one["id"],
                                     "aria-label": PLAYS["en"].format(title=one["title"])})
        self.assertEqual([attrs for tag, attrs in reader.tags if tag == "span"], [{"class": "btn", "aria-hidden": "true"}] * len(VIDEOS))
        # Une carte par ligne de liste, la légende venant après la carte.
        items = re.findall(r"<li(?: [^>]*)?>.*?</li>", shown)
        self.assertEqual(len(items), len(VIDEOS))
        for item, one in zip(items, VIDEOS):
            self.assertTrue(item.startswith(f'<li class="play"><a class="video" href="{WATCH}{one["id"]}" data-id="{one["id"]}" '), item)
            card_end = item.index("</a>") + len("</a>")
            card, legend = item[:card_end], item[card_end:]
            self.assertEqual(Reader(card).text(), "▶")  # le seul texte visible de la carte : le bouton (le nom est dans aria-label)
            for shown_text in (one["title"], one["channel"], an.day_label(date.fromisoformat(one["published"]), "en", False)):
                self.assertIn(shown_text, Reader(legend).text())
            self.assertTrue(legend.startswith('<p class="legend"><b>'), legend)
            self.assertEqual(Reader(legend).names().count("a"), 0)
            self.assertTrue(legend.endswith("</p></li>"), legend)
        for forbidden in ("autoplay", "<script", "<img", "<iframe", "youtube-nocookie", "youtu.be", "Watch on YouTube", "<video", "<link",
                          "src=", "srcset", "style="):
            self.assertNotIn(forbidden, shown)
        self.assertTrue({"img", "script", "iframe", "video", "link", "source", "embed", "object"}.isdisjoint(reader.names()))
        # La seule adresse de tiers : le lien de secours de chaque carte.
        self.assertEqual(re.findall(r"https?://[^\"' ]+", shown), [f"{WATCH}{one['id']}" for one in VIDEOS])
        for lang in an.LANGS:  # la date de la légende s'écrit dans la langue de la page
            with self.subTest(lang=lang):
                self.assertIn(blog._day("2026-10-12", lang), Reader(blog.render_videos(VIDEOS[:1], lang)).text())
        self.assertEqual(blog.render_videos([], "fr"), "")
        self.assertIn("12. Oktober 2026", Reader(blog.render_videos(VIDEOS[:1], "de")).text())

    def test_dates_dans_la_langue(self):
        wanted = {"fr": "27 octobre 2026", "en": "27 October 2026", "es": "27 de octubre de 2026", "de": "27. Oktober 2026",
                  "pt-BR": "27 de outubro de 2026"}
        for lang, label in wanted.items():
            with self.subTest(lang=lang):
                self.assertEqual(blog._day("2026-10-27", lang), label)

    def test_titre_hostile_dans_l_attribut(self):
        """Un titre ou une chaîne qui tente de sortir de l'attribut ou de la page est échappé, dans aria-label="…" comme dans la légende."""
        evil = '"><script>x</script>'
        shown = blog.render_videos([video("aB3_-xY9zQ1", title=evil, channel=evil + "'")], "fr")
        self.assertNotIn("<script", shown)
        self.assertNotIn("</script", shown)
        self.assertNotIn('"><script', shown)
        self.assertEqual(shown.count("&lt;script&gt;x&lt;/script&gt;"), 3)  # aria-label="…", titre de la légende, chaîne de la légende
        self.assertIn('aria-label="Lire : &quot;&gt;&lt;script&gt;x&lt;/script&gt;"', shown)
        self.assertIn("<b>&quot;&gt;&lt;script&gt;x&lt;/script&gt;</b>", shown)
        reader = Reader(shown)
        self.assertEqual(reader.values("a", "aria-label"), [f"Lire : {evil}"])  # relu par un navigateur : exactement le libellé et le titre
        self.assertIn(evil, reader.text())
        self.assertEqual(reader.names().count("a"), 1)
        self.assertNotIn("script", reader.names())
        card = [attrs for tag, attrs in reader.tags if tag == "a"][0]
        self.assertEqual(sorted(card), ["aria-label", "class", "data-id", "href"])  # aucun attribut de plus
        # L'identifiant, même s'il était hostile, ne sortirait ni de href ni de data-id (load_topplays ne laisse de toute façon passer que
        # 11 caractères sûrs, et le script de lecture refuse tout autre data-id).
        odd = blog.render_videos([video('a"><script>', title="T")], "en")
        self.assertNotIn("<script", odd)
        self.assertEqual(Reader(odd).names().count("a"), 1)
        self.assertEqual(Reader(odd).values("a", "href"), [f"{WATCH}a%22%3E%3Cscript%3E"])
        self.assertEqual(Reader(odd).values("a", "data-id"), ['a"><script>'])

    def test_sommaire(self):
        page = entry("valorant", sections=[written(["s1"], "Valorant en bref", "Un."), written(["s1"], "Le circuit <VCT> & co", "Deux.")])
        shown = blog.render_sections(page, "fr")
        self.assertEqual(re.findall(r'<h2 id="([^"]*)">', shown), ["s1", "s2"])  # les ancres du sommaire
        toc = blog.render_toc(page, "fr", videos=False)
        self.assertEqual(toc, '<nav class="toc" aria-label="Sommaire"><p>Sommaire</p><ol><li><a href="#s1">Valorant en bref fr</a></li>'
                              '<li><a href="#s2">Le circuit &lt;VCT&gt; &amp; co fr</a></li><li><a href="#sources">Sources</a></li></ol></nav>')
        with_plays = blog.render_toc(page, "en", videos=True)
        self.assertIn('<li><a href="#plays">Top plays right now</a></li><li><a href="#sources">Sources</a></li>', with_plays)
        self.assertIn('<h2 id="plays">', blog.render_videos(VIDEOS, "en"))
        self.assertIn('<h2 id="sources">', blog.render_sources(page, "en"))
        main_html = blog.render_guide_main(page, "fr", NAMES, HOME, VIDEOS, [], [])
        self.assertRegex(main_html, r'<div class="art"><article><section class="sec">.*</article><nav class="toc"')  # le texte, puis le sommaire

    def test_couverture(self):
        self.assertEqual(blog.render_cover(entry("valorant"), "fr"), "")
        ia = entry("valorant", image={"kind": "ia"}, fr={"title": "Valorant & co", "description": "D."})
        self.assertEqual(blog.render_cover(ia, "fr"),
                         '<figure class="cover"><img src="../../couvertures/valorant.webp" alt="Valorant &amp; co" width="1600" height="900" '
                         'decoding="async"><figcaption>Illustration générée par IA</figcaption></figure>')
        official = entry("valorant", image={"kind": "officielle", "credit": "Riot <Games>", "url": "https://riot.example/p?a=1&b=2"})
        shown = blog.render_cover(official, "de")
        self.assertIn('<figcaption>Bild: Riot &lt;Games&gt; · <a href="https://riot.example/p?a=1&amp;b=2" rel="noopener">Quelle</a></figcaption>', shown)
        main_html = blog.render_guide_main(ia, "fr", NAMES, HOME, [], [], [])
        self.assertRegex(main_html, r'</section><figure class="cover">.*</figure><div class="art">')  # après l'en-tête, avant le texte
        self.assertEqual(blog.cover_url(ia), "https://esportly.eu/couvertures/valorant.webp")
        shared = entry("vct-2026", kind="news", image={"kind": "ia", "file": "valorant"})  # un article qui reprend la couverture de son jeu
        self.assertIn('<img src="../couvertures/valorant.webp"', blog.render_cover(shared, "en"))
        self.assertEqual(blog.cover_url(shared), "https://esportly.eu/couvertures/valorant.webp")
        self.assertEqual(json.loads(LD_SCRIPT.findall(blog.render_jsonld(ia, "fr", "https://esportly.eu/fr/blog/valorant", []))[0])["image"],
                         "https://esportly.eu/couvertures/valorant.webp")

    def test_donnees_structurees(self):
        page = entry("valorant", date="2026-10-20", updated="2026-10-28", sources=[source(1), source(2)],
                     fr={"title": "Valorant : le jeu", "description": "Ce qu'est Valorant."})
        crumbs = [("Accueil", "https://esportly.eu/fr"), ("Blog", "https://esportly.eu/fr/blog"),
                  ("Valorant", "https://esportly.eu/fr/blog/valorant")]
        ld = blog.render_jsonld(page, "fr", "https://esportly.eu/fr/blog/valorant", crumbs)
        payloads = LD_SCRIPT.findall(ld)
        self.assertEqual(len(payloads), 2)
        self.assertTrue(ld.startswith('<script type="application/ld+json">') and ld.endswith("</script>"))
        art, trail = (json.loads(payload) for payload in payloads)
        self.assertEqual(art["@context"], "https://schema.org")
        self.assertEqual(art["@type"], "Article")
        self.assertEqual((art["headline"], art["description"]), ("Valorant : le jeu", "Ce qu'est Valorant."))
        self.assertEqual((art["datePublished"], art["dateModified"], art["inLanguage"]), ("2026-10-20", "2026-10-28", "fr"))
        self.assertEqual(art["mainEntityOfPage"], "https://esportly.eu/fr/blog/valorant")
        self.assertEqual(art["image"], "https://esportly.eu/partage/jeux/valorant.jpg")  # l'og:image de la page du jeu
        self.assertEqual(art["author"], {"@type": "Organization", "name": "eSportly", "url": "https://esportly.eu/"})
        self.assertEqual(art["publisher"], {"@type": "Organization", "name": "ProtoJo Digital", "url": "https://esportly.eu/",
                                            "logo": "https://esportly.eu/icone-512.png"})
        for local in (art["image"], art["publisher"]["logo"]):  # les fichiers existent dans le site
            self.assertTrue((an.ROOT / local.removeprefix("https://esportly.eu/")).is_file(), local)
        general = json.loads(LD_SCRIPT.findall(blog.render_jsonld(solo(), "fr", "https://esportly.eu/fr/blog/x", crumbs))[0])
        self.assertEqual(general["image"], "https://esportly.eu/partage/jeux/league-of-legends.jpg")  # sans jeu : le modèle (§6)
        self.assertEqual(art["citation"], ["https://example.org/page-1", "https://example.org/page-2"])
        self.assertEqual((trail["@context"], trail["@type"]), ("https://schema.org", "BreadcrumbList"))
        self.assertEqual(len(trail["itemListElement"]), 3)
        for position, (name, url) in enumerate(crumbs, start=1):
            self.assertEqual(trail["itemListElement"][position - 1], {"@type": "ListItem", "position": position, "name": name, "item": url})
        english = json.loads(LD_SCRIPT.findall(blog.render_jsonld(page, "en", "https://esportly.eu/blog/valorant.html", crumbs[:1]))[0])
        self.assertEqual((english["inLanguage"], english["headline"]), ("en", "Titre en"))

    def test_page_de_jeu(self):
        page = fiche("valorant", date="2026-10-28", updated="2026-10-28", sources=[source(1), source(2)],
                     sections=[written(["s1"], "Un", "p1"), written(["s2"], "Deux", "p2"), written(["s1", "s2"], "Trois", "p3", "p4")])
        articles = [article("comprendre-le-bo5", "2026-10-25")]
        others = [fiche("league-of-legends"), fiche("counter-strike-2")]
        shown = blog.render_guide_main(page, "fr", NAMES, HOME, VIDEOS, articles, others)
        marks = ['class="crumbs"', "<h1>Titre fr</h1>", '<p class="lead">Description fr.</p>', '<section class="sec">', 'class="topplays"',
                 'class="sources"', "Vérifié le 28 octobre 2026", 'class="ai"', 'class="follow"', "Articles sur Valorant", "Autres jeux"]
        positions = [shown.index(mark) for mark in marks]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), len(marks))
        self.assertTrue(shown.startswith('<nav class="crumbs" aria-label="Breadcrumb"><a href="../fr.html">Accueil</a> › '
                                         '<a href="../../fr/blog.html">Blog</a> › <span>Valorant</span></nav>'))
        self.assertIn('<img class="glogo" src="../../logos-jeux/valorant.png" alt="" width="58" height="48">', shown)
        self.assertEqual(shown.count("<h1"), 1)
        self.assertEqual(shown.count('<section class="sec">'), 3)
        self.assertIn('<p class="checked">Vérifié le 28 octobre 2026</p>'
                      '<p class="ai">Rédigé avec l\'aide de l\'IA et vérifié par rapport aux sources citées.</p>', shown)
        self.assertIn('<section class="follow"><h2>Suivre Valorant avec eSportly</h2>'
                      '<p><a href="../../fr/jeux/valorant.html">Voir ce que fait eSportly pour Valorant</a></p>'
                      '<a class="cta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/fr/blog/valorant&amp;go=testflight">'
                      f'{an.LABELS["fr"]["cta"]}</a></section>', shown)
        self.assertIn('<h2>Articles sur Valorant</h2><ul class="posts"><li data-game="valorant"><a href="comprendre-le-bo5.html">'
                      '<time datetime="2026-10-25">25 octobre 2026</time><b>Guide comprendre-le-bo5 fr</b>'
                      '<small>Résumé comprendre-le-bo5 fr.</small></a></li></ul>', shown)
        self.assertTrue(shown.endswith('<h2>Autres jeux</h2><nav class="others" aria-label="Autres jeux">'
                                       '<a href="league-of-legends.html">League of Legends</a><a href="counter-strike-2.html">Counter-Strike 2</a></nav>'))
        reader = Reader(shown)
        self.assertEqual(reader.names().count("img"), 1)  # le seul : le logo du jeu
        self.assertTrue({"script", "video", "link", "iframe"}.isdisjoint(reader.names()))
        self.assertEqual(reader.values("a", "data-id"), [one["id"] for one in VIDEOS])  # les 3 top plays, en cartes de lecture
        # Les seuls liens vers YouTube : les liens de secours des cartes.
        self.assertEqual([href for href in reader.values("a", "href") if "youtube" in href], [f"{WATCH}{one['id']}" for one in VIDEOS])
        self.assertNotIn("youtube-nocookie", shown)

    def test_page_de_jeu_sans_blocs_facultatifs(self):
        page = fiche("valorant", updated="2026-10-28")
        shown = blog.render_guide_main(page, "fr", NAMES, HOME, [], [], [])
        for absent in ("topplays", "Top plays", "Articles sur", "Autres jeux", 'class="others"', "YouTube"):
            self.assertNotIn(absent, shown)
        for present in ('class="sources"', 'class="follow"', "Vérifié le 28 octobre 2026", 'class="ai"'):
            self.assertIn(present, shown)
        # Sans nom connu, le jeu s'affiche sous son identifiant.
        self.assertEqual(blog.render_guide_main(page, "fr", {}, HOME, [], [], []).count("<span>valorant</span>"), 1)

    def test_page_de_jeu_dans_chaque_langue(self):
        page = fiche("valorant")
        expected = {"en": ("games", "blog.html", "blog"), "fr": ("fr/jeux", "fr/blog.html", "fr/blog"), "es": ("es/juegos", "es/blog.html", "es/blog"),
                    "de": ("de/spiele", "de/blog.html", "de/blog"), "pt-BR": ("pt/jogos", "pt/blog.html", "pt/blog")}
        for lang, (games, hub, folder) in expected.items():
            with self.subTest(lang=lang):
                shown = blog.render_guide_main(page, lang, NAMES, HOME, VIDEOS, [], [fiche("league-of-legends")])
                up = "../" if lang == "en" else "../../"  # une page du Blog est dans <langue>/blog/ hors anglais
                self.assertIn(f'<a href="{up}{hub}">Blog</a>', shown)
                self.assertIn(f'<a href="{up}{games}/valorant.html">{blog.LABELS[lang]["see_game"].format(game="Valorant")}</a>', shown)
                self.assertIn(f"visite?p=/{folder}/valorant&amp;go=testflight", shown)
                self.assertIn(f"<h1>Titre {lang}</h1>", shown)
                self.assertIn(f'<h2 id="s1">Titre {lang}</h2>', shown)
                self.assertIn(f'<nav class="toc" aria-label="{blog.LABELS[lang]["toc"]}">', shown)
                self.assertIn(blog.LABELS[lang]["ai"], shown)
                self.assertIn(blog.LABELS[lang]["checked"].format(date=blog._day("2026-10-20", lang)), shown)
                self.assertIn(f'aria-label="{blog.LABELS[lang]["others"]}"', shown)
                self.assertIn(blog.LABELS[lang]["topplays"], shown)

    def test_page_sans_jeu(self):
        solo = {**guide(), "id": "comprendre-le-bo5"}
        shown = blog.render_guide_main(solo, "fr", NAMES, HOME, [], [], [fiche("valorant")])
        self.assertNotIn("<img", shown)
        self.assertNotIn("glogo", shown)
        self.assertNotIn("follow", shown)
        self.assertNotIn("visite?p=", shown)
        self.assertNotIn("fr/jeux/", shown)
        self.assertIn('<a href="../../fr/blog.html">Blog</a> › <span>Titre fr</span></nav>', shown)
        self.assertIn("<h1>Titre fr</h1>", shown)
        self.assertIn("<h2>Autres jeux</h2>", shown)
        # Un guide rattaché à un jeu garde le logo et l'encadré du jeu, mais son fil d'Ariane finit sur son propre titre.
        about = blog.render_guide_main({**guide(game="valorant"), "id": "comprendre-le-bo5"}, "fr", NAMES, HOME, [], [], [])
        self.assertIn('src="../../logos-jeux/valorant.png"', about)
        self.assertIn("Suivre Valorant avec eSportly", about)
        self.assertIn("visite?p=/fr/blog/comprendre-le-bo5&amp;go=testflight", about)
        self.assertIn("<span>Titre fr</span></nav>", about)

    def test_accueil_du_blog(self):
        pages = [fiche("league-of-legends"), fiche("counter-strike-2"), fiche("valorant")]
        shown = blog.render_hub_main("en", pages, NAMES)
        self.assertTrue(shown.startswith('<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">Blog</div>'
                                         '<h1>The games behind the matches</h1><p class="lead">'))
        self.assertIn(blog.LABELS["en"]["lead"], shown)
        self.assertNotIn('class="cta"', shown)
        self.assertIn('<h2>Games</h2><div class="cards mini">', shown)
        self.assertEqual(re.findall(r'<a class="card" data-game="([^"]*)" href="([^"]*)"', shown),
                         [(game, f"blog/{game}.html") for game in ("league-of-legends", "counter-strike-2", "valorant")])
        self.assertNotIn("chips", shown)  # pas de filtre par jeu : les articles viennent d'abord, les jeux sont des liens en bas
        self.assertEqual(re.findall(r'<a class="card" data-game="[^"]*" href="([^"]*)"', shown),
                         ["blog/league-of-legends.html", "blog/counter-strike-2.html", "blog/valorant.html"])
        self.assertEqual(Reader(shown).values("img", "src"), [f"logos-jeux/{game}.png" for game in ("league-of-legends", "counter-strike-2", "valorant")])
        self.assertNotIn("../", shown)  # l'accueil est à la racine du site
        self.assertIn('<a class="card" data-game="valorant" href="blog/valorant.html"><img src="logos-jeux/valorant.png" alt="" width="58" height="48">'
                      '<b>Valorant</b></a>', shown)
        self.assertNotIn("Description en.", shown)  # les jeux ne sont plus que des logos et des noms : le texte est dans les articles
        self.assertNotIn("Latest articles", shown)
        self.assertNotIn('class="posts', shown)
        # L'ordre des fiches est celui qu'on donne : l'accueil ne les retrie pas. Un jeu sans nom s'affiche sous son identifiant.
        swapped = blog.render_hub_main("fr", [fiche("valorant"), fiche("dota-2")], NAMES)
        self.assertEqual(re.findall(r'<a class="card" data-game="[^"]*" href="([^"]*)"', swapped), ["../fr/blog/valorant.html", "../fr/blog/dota-2.html"])
        self.assertIn("<b>dota-2</b>", swapped)
        self.assertIn("<h2>Jeux</h2>", swapped)

    def test_derniers_articles(self):
        guides = [article(f"guide-{n:02d}", f"2026-10-{n:02d}", image={"kind": "ia"}) for n in range(1, 16)]
        pages = [fiche("valorant"), *guides[:5], fiche("league-of-legends"), *guides[5:]]  # désordre voulu
        shown = blog.render_hub_main("fr", pages, NAMES)
        self.assertEqual(shown.count('class="card"'), 2)
        self.assertEqual(shown.count("<h2>"), 2)
        self.assertIn('<h2>Derniers articles</h2><ul class="posts feed">', shown)
        self.assertTrue(shown.index("<h2>Derniers articles</h2>") < shown.index("<h2>Jeux</h2>"))  # articles d'abord, jeux en bas
        self.assertTrue(shown.endswith("</div>"))  # la grille des jeux ferme la page
        links = re.findall(r'<a href="(\.\./fr/blog/guide-[0-9]{2}\.html)"', shown)
        self.assertEqual(links, [f"../fr/blog/guide-{n:02d}.html" for n in range(15, 3, -1)])  # les 12 plus récents, du plus récent au plus ancien
        self.assertIn('<li data-game="valorant"><a href="../fr/blog/guide-15.html"><img src="../couvertures/guide-15.webp" alt="" width="1600" height="900" decoding="async" '
                      'fetchpriority="high"><span class="txt"><time datetime="2026-10-15">15 octobre 2026</time>'
                      '<b>Guide guide-15 fr</b><small>Résumé guide-15 fr.</small></span></a></li>', shown)
        self.assertIn('<img src="../couvertures/guide-14.webp" alt="" width="1600" height="900" decoding="async" loading="lazy">', shown)
        self.assertEqual(shown.count("fetchpriority"), 1)  # seule la première image est prioritaire
        self.assertNotIn("../../", shown)  # l'accueil du Blog français est dans fr/ : un seul « ../ »

    def test_carte_sans_image_ni_jeu(self):
        """Une page sans `image` n'a pas d'<img> dans sa carte, seulement le texte ; toute la carte reste un lien."""
        bare = article("sans-image", "2026-10-25")
        shown = blog.render_hub_main("fr", [bare], NAMES)
        self.assertIn('<li data-game="valorant"><a href="../fr/blog/sans-image.html"><span class="txt"><time datetime="2026-10-25">25 octobre 2026</time>'
                      '<b>Guide sans-image fr</b>', shown)
        self.assertNotIn("<img", shown)
        self.assertIn(".feed li:first-child a:has(img){", blog.BLOG_STYLE)  # deux colonnes seulement quand la carte vedette a une image

    def test_carte_echappee_couverture_reprise_et_accueil_racine(self):
        """Titre et description sont échappés ; une page qui reprend la couverture d'une autre (`image.file`) l'affiche ; l'accueil anglais,
        à la racine, n'a aucun préfixe."""
        tricky = article("tricky", "2026-10-25", image={"kind": "ia", "file": "autre-page"},
                         en={"title": "A <b>&\"x\"", "description": "<i>d</i> & co"})
        shown = blog.render_hub_main("en", [tricky], NAMES)
        self.assertIn("<b>A &lt;b&gt;&amp;&quot;x&quot;</b>", shown)
        self.assertIn("<small>&lt;i&gt;d&lt;/i&gt; &amp; co</small>", shown)
        self.assertIn('<img src="couvertures/autre-page.webp"', shown)
        self.assertIn('<a href="blog/tricky.html">', shown)
        self.assertNotIn("../", shown)

    def test_data_game_de_l_accueil(self):
        """Un guide d'un jeu porte data-game ; un guide général n'en porte pas ; l'accueil n'a aucun bouton de filtre."""
        pages = [fiche("valorant"), solo("guide-valorant", game="valorant"), solo("guide-general", game=None)]
        pages[2].pop("game")
        shown = blog.render_hub_main("fr", pages, NAMES)
        self.assertIn('<li data-game="valorant"><a href="../fr/blog/guide-valorant.html">', shown)
        self.assertIn('<li><a href="../fr/blog/guide-general.html">', shown)
        self.assertNotIn("chips", shown)
        two = blog.render_hub_main("fr", [fiche("valorant"), fiche("dota-2")], NAMES)
        self.assertNotIn("chips", two)
        self.assertNotIn('class="f"', two)

    def test_accueil_sans_fiche(self):
        shown = blog.render_hub_main("en", [], NAMES)
        self.assertIn("<h1>The games behind the matches</h1>", shown)
        self.assertNotIn("<h2>", shown)
        self.assertNotIn("cards", shown)

    def test_lien_de_guide(self):
        self.assertEqual(blog.render_guide_link(None, "fr", "Valorant"), "")
        self.assertEqual(blog.render_guide_link(fiche("valorant"), "fr", "Valorant"),
                         '<p class="guide"><a href="../../fr/blog/valorant.html">Guide : Valorant, le jeu et sa scène pro →</a></p>')
        self.assertIn('<a href="../blog/valorant.html">Guide: Valorant, the game and its pro scene →</a>',
                      blog.render_guide_link(fiche("valorant"), "en", "Valorant"))
        self.assertIn('href="../../pt/blog/valorant.html"', blog.render_guide_link(fiche("valorant"), "pt-BR", "Valorant"))
        self.assertIn("Guide: Mobile Legends: Bang &amp; Bang &lt;b&gt;",
                      blog.render_guide_link(fiche("valorant"), "en", "Mobile Legends: Bang & Bang <b>"))

    def test_fragments_sur_une_ligne(self):
        multi = [video("aB3_-xY9zQ1", title="Deux\nlignes", channel="Chaîne\r\nX"), *VIDEOS[1:]]
        page = fiche("valorant", sources=[source(1, title="Titre")], sections=[written(["s1"], "Un", "p1")] * 3)
        for lang in an.LANGS:
            pieces = [blog.render_sections(page, lang), blog.render_sources(page, lang), blog.render_videos(multi, lang), blog.render_videos([], lang),
                      blog.render_jsonld(page, lang, "https://esportly.eu/x", [("A", "https://esportly.eu/a")]),
                      blog.render_guide_main(page, lang, NAMES, HOME, multi, [article("a", "2026-10-25")], [fiche("league-of-legends")]),
                      blog.render_guide_main({**guide(), "id": "g"}, lang, NAMES, HOME, [], [], []),
                      blog.render_hub_main(lang, [page, article("a", "2026-10-25")], NAMES), blog.render_hub_main(lang, [], NAMES),
                      blog.render_guide_link(page, lang, "Valorant"), blog.render_guide_link(None, lang, "Valorant")]
            for piece in pieces:
                with self.subTest(lang=lang, start=piece[:40]):
                    self.assertNotIn("\n", piece)
                    self.assertNotIn("\r", piece)
        self.assertIn("Deux lignes", blog.render_videos(multi, "en"))


class Style(unittest.TestCase):
    def test_style(self):
        for selector in [".guide", ".cards", ".card", ".sec", ".cite", ".sources", ".topplays", ".follow", ".ai", ".feed", ".cards.mini"]:
            with self.subTest(selector=selector):
                self.assertRegex(blog.BLOG_STYLE, r"(?m)^" + re.escape(selector) + r"[\s{.:,>\[]")
        for variable in ["--surface", "--border", "--soft", "--text", "--or", "--display", "--g"]:
            self.assertIn(f"var({variable}", blog.BLOG_STYLE)
        lines = blog.BLOG_STYLE.split("\n")
        self.assertGreater(len(lines), 10)
        for line in lines:  # une règle par ligne
            self.assertTrue(line.endswith("}"), line)
            self.assertEqual(line.count("{"), line.count("}"), line)
        for external in ("url(", "@import", "http", "<", "//"):
            self.assertNotIn(external, blog.BLOG_STYLE)

    def test_style_des_lecteurs(self):
        """Carte 16/9 avec un bouton rond au centre, puis cadre 16/9 rempli par l'iframe après le clic, grille adaptative des top plays,
        légende sous chaque carte ; variables de thème seulement."""
        rules = {line.split("{")[0]: line[line.index("{") + 1:-1].split(";") for line in blog.BLOG_STYLE.split("\n") if not line.startswith("@")}
        for declaration in ("position:relative", "aspect-ratio:16/9", "overflow:hidden", "background:var(--surface)",
                            "display:grid", "place-items:center"):  # la carte (un lien, donc en ligne sans display) et le cadre du lecteur
            self.assertIn(declaration, rules[".video"])
        self.assertTrue(any(declaration.startswith("border-radius:") for declaration in rules[".video"]))
        for declaration in ("position:absolute", "inset:0", "width:100%", "height:100%", "border:0"):  # l'iframe remplit le cadre
            self.assertIn(declaration, rules[".video iframe"])
        button = rules[".video .btn"]  # le bouton rond, aux couleurs du bouton principal du site
        for declaration in ("border-radius:50%", "background:var(--or)", "color:var(--on-or)"):
            self.assertIn(declaration, button)
        widths = [declaration for declaration in button if declaration.startswith(("width:", "height:"))]
        self.assertEqual(len(widths), 2)
        self.assertEqual(len({declaration.split(":")[1] for declaration in widths}), 1)  # aussi large que haut
        self.assertIn(".video:focus-visible", rules)  # le focus du clavier se voit
        self.assertNotIn("#", "".join(button))  # aucune couleur en dur
        self.assertIn("display:grid", rules[".topplays"])  # la grille des lecteurs
        columns = [declaration for declaration in rules[".topplays"] if declaration.startswith("grid-template-columns:")]
        self.assertEqual(len(columns), 1)
        self.assertRegex(columns[0], r"^grid-template-columns:repeat\(auto-fit,minmax\(")  # une colonne sur écran étroit, davantage si la place le permet
        self.assertIn("list-style:none", rules[".topplays"])
        for selector in (".play", ".legend", ".legend b", ".legend small"):  # la légende : titre en gras, chaîne et date plus petites
            self.assertIn(selector, rules)
        self.assertIn("color:var(--soft)", rules[".legend small"])
        # Les anciens liens-cartes des top plays ont disparu : adaptés en lecteurs, pas dupliqués.
        self.assertNotIn(".topplays a", rules)
        self.assertNotIn(".topplays span", rules)
        self.assertEqual(len([line for line in blog.BLOG_STYLE.split("\n") if line.startswith(".topplays")]), 1)
        self.assertNotIn("animation", blog.BLOG_STYLE)

    def test_logos_blancs_inverses_sur_le_theme_clair(self):
        lines = blog.BLOG_STYLE.split("\n")
        explicit = [line for line in lines if line.startswith(':root[data-theme="light"] img[src$=')]
        automatic = [line for line in lines if line.startswith("@media (prefers-color-scheme:light){:root:not([data-theme]) img[src$=")]
        self.assertEqual((len(explicit), len(automatic)), (1, 1))
        for game in blog.MONO_LOGOS:
            self.assertIn(game, blog.GAMES)
            self.assertIn(f':root[data-theme="light"] img[src$="/{game}.png"]', explicit[0])
            self.assertIn(f':root:not([data-theme]) img[src$="/{game}.png"]', automatic[0])
        for line in (explicit[0], automatic[0]):
            self.assertIn("{filter:invert(1)}", line)
        own = [line for line in blog.BLOG_STYLE.split("\n") if line not in site_chrome.FILTER_STYLE]  # hors le filtre, qui nomme tous les jeux
        self.assertNotIn("valorant", "\n".join(own))  # les logos en couleur ne sont pas touchés

    @unittest.skipUnless((Path(__file__).resolve().parents[2] / "games").is_dir(), "pages de jeux absentes")
    def test_logos_blancs_comme_sur_les_pages_de_jeux(self):
        """La liste est celle des pages de jeux qui dessinent leur logo avec un masque (« glogo mono ») : elle doit rester à jour."""
        folder = Path(__file__).resolve().parents[2] / "games"
        mono = {path.stem for path in folder.glob("*.html") if 'class="glogo mono"' in path.read_text(encoding="utf-8")}
        self.assertEqual(set(blog.MONO_LOGOS), mono)

    def test_toutes_les_classes_ont_une_regle(self):
        page = fiche("valorant", sources=[source(1)], sections=[written(["s1"], "Un", "p1")] * 3)
        fragments = [blog.render_guide_main(page, "en", NAMES, HOME, VIDEOS, [article("a", "2026-10-25")], [fiche("league-of-legends")]),
                     blog.render_hub_main("en", [page, article("a", "2026-10-25")], NAMES), blog.render_guide_link(page, "en", "Valorant")]
        used = {name for fragment in fragments for _, attrs in Reader(fragment).tags for name in attrs.get("class", "").split()}
        selectors = re.sub(r"\{[^{}]*\}", "", re.sub(r"\{[^{}]*\}", "", blog.BLOG_STYLE))  # sans les déclarations, même sous @media
        defined = set(re.findall(r"\.([A-Za-z][\w-]*)", selectors))
        self.assertEqual(used - defined - TEMPLATE_CLASSES, set())
        self.assertEqual(used & TEMPLATE_CLASSES, TEMPLATE_CLASSES)  # toutes les classes de la liste sont bien employées
        self.assertGreaterEqual(len(used & defined), 12)


# --- Le script de lecture au clic, exécuté par Node ---------------------------------------------------------------
# Un faux document minimal : seuls addEventListener et createElement existent (toute autre propriété lue lève une erreur), et les
# éléments ne connaissent que les sélecteurs employés par le script. On note tout appel, pour prouver que rien n'est créé avant le clic.
NODE = shutil.which("node")
NODE_HARNESS = r"""
const vm = require("vm");
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = [];
for (const c of input.cases) {
  const log = [];
  let listener = null, focused = null;
  class El {
    constructor(tag, attrs) { this.tagName = tag.toUpperCase(); this.attrs = Object.assign({}, attrs || {}); this.children = []; this.parentNode = null; this.textContent = ""; }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
    replaceWith(other) { const p = this.parentNode; p.children[p.children.indexOf(this)] = other; other.parentNode = p; this.parentNode = null; }
    classes() { return (this.attrs["class"] || "").split(" "); }
    matches(sel) {
      if (sel === "a.video") return this.tagName === "A" && this.classes().includes("video");
      throw new Error("sélecteur inattendu : " + sel);
    }
    closest(sel) { for (let n = this; n; n = n.parentNode) if (n.matches(sel)) return n; return null; }
    querySelector(sel) {
      if (sel !== ".legend b") throw new Error("sélecteur inattendu : " + sel);
      const walk = (n) => { for (const ch of n.children) { if (ch.tagName === "B" && n.classes().includes("legend")) return ch; const f = walk(ch); if (f) return f; } return null; };
      return walk(this);
    }
    focus() { focused = this; }
  }
  const make = (tag, attrs, parent) => { const e = new El(tag, attrs); if (parent) parent.appendChild(e); return e; };
  const ul = make("ul", {class: "topplays"});
  const li = make("li", {class: "play"}, ul);
  const a = make("a", {class: "video", href: "https://www.youtube.com/watch?v=" + c.id, "data-id": c.id, "aria-label": "Play: " + c.title}, li);
  const span = make("span", {class: "btn", "aria-hidden": "true"}, a);
  const legend = make("p", {class: "legend"}, li);
  const b = make("b", {}, legend);
  b.textContent = c.title;
  const doc = {
    addEventListener(type, fn) { log.push("listen:" + type); listener = fn; },
    createElement(tag) { log.push("create:" + tag); return new El(tag); },
  };
  const document = new Proxy(doc, { get(t, k) { if (k in t) return t[k]; throw new Error("document." + String(k) + " n'est pas fourni"); } });
  vm.runInNewContext(input.script, { document }, { timeout: 1000 });
  const before = log.slice();
  const event = { target: c.on === "legend" ? b : span, button: 0, ctrlKey: !!c.ctrl, metaKey: false, shiftKey: false, altKey: false,
                  defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  if (listener) listener(event);
  const first = li.children[0];
  out.push({ before, log, prevented: event.defaultPrevented, first: { tag: first.tagName, attrs: first.attrs },
             inner: first.children.map((ch) => ({ tag: ch.tagName, attrs: ch.attrs })), legend: li.children[1] === legend,
             focused: focused && focused.tagName });
}
process.stdout.write(JSON.stringify(out));
"""


class LecteurAuClic(unittest.TestCase):
    @unittest.skipUnless(NODE, "node introuvable : le script de lecture au clic n'est pas exécuté (bac à sable vm)")
    def test_script_dans_un_bac_a_sable(self):
        """Le script n'écoute que les clics ; un clic sur une carte valide la remplace par le lecteur youtube-nocookie en lecture
        automatique ; un data-id invalide, un clic avec Ctrl ou un clic hors carte ne font rien et laissent le lien suivre son cours."""
        title = 'Vidéo <b>"x"</b> & y'
        cases = [{"id": "aB3_-xY9zQ1", "title": title}, {"id": "abc", "title": "T"}, {"id": 'a"><b>xxxxx', "title": "T"},
                 {"id": "aB3_-xY9zQ1 ", "title": "T"}, {"id": "aB3_-xY9zQ1", "title": "T", "ctrl": True},
                 {"id": "aB3_-xY9zQ1", "title": "T", "on": "legend"}]
        with tempfile.TemporaryDirectory() as folder:
            harness = Path(folder) / "harness.js"
            harness.write_text(NODE_HARNESS, encoding="utf-8")
            done = subprocess.run([NODE, str(harness)], input=json.dumps({"script": blog.PLAYER_JS, "cases": cases}),
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        played, *ignored = json.loads(done.stdout)
        # Au chargement : un seul écouteur de clics, aucun élément créé (donc aucune requête).
        self.assertEqual(played["before"], ["listen:click"])
        self.assertTrue(played["prevented"])
        self.assertEqual(played["first"], {"tag": "DIV", "attrs": {"class": "video"}})  # la carte remplacée par le cadre du lecteur
        self.assertEqual(played["inner"], [{"tag": "IFRAME", "attrs": {
            "src": "https://www.youtube-nocookie.com/embed/aB3_-xY9zQ1?autoplay=1", "title": title, "allowfullscreen": "",
            "referrerpolicy": "strict-origin-when-cross-origin", "allow": "autoplay; encrypted-media; picture-in-picture"}}])
        self.assertTrue(played["legend"])  # la légende reste en place
        self.assertEqual(played["focused"], "IFRAME")
        for case, result in zip(cases[1:], ignored):
            with self.subTest(case=case):
                self.assertEqual(result["log"], ["listen:click"])  # rien de créé
                self.assertFalse(result["prevented"])  # le lien de secours suit son cours
                self.assertEqual(result["first"]["tag"], "A")
                self.assertIsNone(result["focused"])


# --- Pages et génération : un site factice ----------------------------------------------------------------------
# Les modèles reprennent la structure des vraies pages (games/valorant.html, fr/jeux/valorant.html, whats-new.html, sitemap.xml),
# en CRLF comme l'arbre de travail, avec les marqueurs que posera le script d'application (§8 de la spec).

GAME_NAMES = {"league-of-legends": "League of Legends", "counter-strike-2": "Counter-Strike 2", "valorant": "Valorant",
              "rocket-league": "Rocket League", "dota-2": "Dota 2", "overwatch-2": "Overwatch 2", "rainbow-six-siege": "Rainbow Six Siege",
              "call-of-duty": "Call of Duty", "mobile-legends": "Mobile Legends: Bang Bang", "honor-of-kings": "Honor of Kings",
              "ea-sports-fc": "EA Sports FC", "starcraft-2": "StarCraft II", "starcraft-brood-war": "StarCraft: Brood War",
              "wild-rift": "League of Legends: Wild Rift"}
COLORS = {"league-of-legends": "#3cc8e0", "valorant": "#ff89be"}  # couleur du jeu (--g) ; les autres jeux : #888888
SITE_HOMES = {"en": ("../", "Home"), "fr": ("../../fr.html", "Accueil"), "es": ("../../es.html", "Inicio"), "de": ("../../de.html", "Start"),
              "pt-BR": ("../../pt.html", "Início")}  # une page de jeu est dans games/ ou <langue>/<jeux>/
CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; script-src 'sha256-THEME='; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://lmavqchwevcvvneblqld.supabase.co; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'none'; upgrade-insecure-requests\">")
THEME = "<script>try{var t=localStorage.getItem('esportly-theme')}catch(e){}</script>"
STYLE = ["<style>:root{--surface:#141A2B;--border:#2C3550}", ".hero{margin:32px 0}.crumbs{font-size:14px}</style>"]
SITEMAP_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\r\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\r\n'
                '<url><loc>https://esportly.eu/news.html</loc><lastmod>2026-10-27</lastmod><changefreq>daily</changefreq></url>\r\n')
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)  # le 27 octobre à Paris


def header(lang: str, home: str, link) -> str:
    """En-tête du site : la marque, puis le menu de langue (`link(langue)` donne l'adresse ; aria-current sur la langue de la page)."""
    current = ' aria-current="page"'
    items = "".join(f'<li><a href="{link(other)}" hreflang="{other}" lang="{other}"{current if other == lang else ""}>{other}</a></li>'
                    for other in an.LANGS)
    return f'<header><div class="wrap"><a class="brand" href="{home}">eSportly</a><details class="lang langs"><ul>{items}</ul></details></div></header>'


def visit_img(path: str) -> str:
    return f'<img src="{blog.VISIT}?p=/{path}" alt="" width="1" height="1" style="position:absolute;left:-9999px">'


def game_page(lang: str, game: str, block: str | None = "") -> str:
    """Une page de jeu existante ; `block` : contenu des marqueurs du lien de guide, None pour une page sans marqueurs."""
    folder, (home, label) = blog.GAME_DIRS[lang], SITE_HOMES[lang]
    alternates = [f'<link rel="alternate" hreflang="{other}" href="https://esportly.eu/{blog.GAME_DIRS[other]}/{game}.html">' for other in an.LANGS]
    guide_block = [] if block is None else [f"{blog.GUIDE_MARKERS[0]}{block}{blog.GUIDE_MARKERS[1]}"]
    return "\r\n".join([
        "<!doctype html>", f'<html lang="{lang}">', "<head>", '<meta charset="utf-8">', CSP, THEME,
        f"<title>Alertes {game} – eSportly</title>", f'<meta name="description" content="Suivre {game} sur iPhone.">',
        f'<link rel="canonical" href="https://esportly.eu/{folder}/{game}.html">', *alternates,
        f'<link rel="alternate" hreflang="x-default" href="https://esportly.eu/games/{game}.html">',
        '<link rel="icon" href="../embleme.svg" type="image/svg+xml">', '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="Alertes {game} – eSportly">', f'<meta property="og:description" content="Suivre {game} sur iPhone.">',
        f'<meta property="og:image" content="https://esportly.eu/partage/jeux/{game}.jpg">', '<meta name="twitter:card" content="summary_large_image">',
        '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}</script>', *STYLE,
        '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": []}</script>',
        "</head>", f'<body style="--g:{COLORS.get(game, "#888888")}">', header(lang, home, lambda other: f"../{blog.GAME_DIRS[other]}/{game}.html"),
        f'<main class="wrap"><nav class="crumbs" aria-label="Breadcrumb"><a href="{home}">{label}</a> › <a href="{home}#jeux">Jeux</a> › '
        f'<span>{html.escape(GAME_NAMES.get(game, game))}</span></nav>',
        f'<section class="hero"><h1>Ancien héros {game}</h1><a class="cta" href="{blog.VISIT}?p=/{folder}/{game}&amp;go=testflight">Bêta</a></section>',
        '<h2>Équipes</h2><nav class="others" aria-label="Équipes"><a href="../teams/t1.html">T1</a></nav>', *guide_block,
        "<h2>Autres jeux</h2>", '<nav class="others" aria-label="Autres jeux"><a href="league-of-legends.html">League of Legends</a></nav>',
        "</main>", '<footer><div class="wrap">eSportly · <a href="../mentions-legales.html">Mentions</a></div></footer>',
        visit_img(f"{folder}/{game}"), "</body>", "</html>", ""])


def hub_template(lang: str) -> str:
    """Une page « What's new » : lien RSS, ni fil d'Ariane ni données structurées."""
    name = an.TEMPLATES[lang]
    alternates = [f'<link rel="alternate" hreflang="{other}" href="https://esportly.eu/{an.TEMPLATES[other]}">' for other in an.LANGS]
    return "\r\n".join([
        "<!doctype html>", f'<html lang="{lang}">', "<head>", '<meta charset="utf-8">', CSP, THEME,
        "<title>What&#x27;s new – eSportly</title>", '<meta name="description" content="Les nouveautés.">',
        f'<link rel="canonical" href="https://esportly.eu/{name}">', *alternates,
        f'<link rel="alternate" hreflang="x-default" href="https://esportly.eu/{an.TEMPLATES["en"]}">',
        '<meta property="og:title" content="Nouveautés"><meta property="og:description" content="Les nouveautés.">'
        '<meta property="og:image" content="https://esportly.eu/apercu.png?v=2">', *STYLE,
        f'<link rel="alternate" type="application/rss+xml" title="RSS" href="{name[:-5]}.xml">', "</head>", '<body style="--g:#FFC53D">',
        header(lang, "./", lambda other: an.TEMPLATES[other]),
        f'<main class="wrap"><section class="hero">ANCIEN HÉROS</section><p class="rss"><a href="{name[:-5]}.xml">RSS</a></p></main>',
        '<footer><div class="wrap">eSportly</div></footer>', visit_img(name[:-5]), "</body>", "</html>", ""])


def home_page(lang: str) -> str:
    """Un accueil minimal : son pied de page (marque, bouton de la bêta, liens de l'app avec News et Blog, infos et une langue par ligne)
    est le seul morceau que les pages du Blog en reprennent."""
    flags = ""
    for other in an.LANGS:
        current = ' aria-current="page"' if other == lang else ""
        flags += (f'<li class="fl"><a href="{"./" if other == "en" else an.HOMES[other]}" hreflang="{other}" lang="{other}"{current}>'
                  f'<svg class="flag" aria-hidden="true"><path d="M0 0"/></svg>{other}</a></li>')
    return "\r\n".join([
        "<!doctype html>", f'<html lang="{lang}">', "<head><title>Accueil</title></head>", "<body>", "<main>ACCUEIL</main>",
        f'<footer><div class="wrap"><div class="fgrid"><div class="fbrand"><a class="brand" href="{"./" if lang == "en" else an.HOMES[lang]}">'
        f'<img src="embleme.svg" alt="" width="44" height="44"><span class="word"><i>e</i>Sportly</span></a><p>Pitch.</p>'
        f'<a class="fbeta" href="{blog.VISIT}?p=/{lang}&amp;go=testflight">Bêta</a></div>'
        f'<div><h3>App</h3><ul><li><a href="#jeux">Jeux</a></li><li><a href="whats-new.html">Nouveautés</a></li>'
        f'<li><a href="{an.PAGES[lang]}">News</a></li><li><a href="{blog.HUBS[lang]}">Blog</a></li></ul></div>'
        '<div><h3>Jeux</h3><ul><li><a href="games/valorant.html">Valorant</a></li><li><a href="teams.html">Équipes</a></li></ul></div>'
        f'<div><h3>Infos</h3><ul><li><a href="privacy.html">Confidentialité</a></li><li><a href="mailto:contact@example.org">Contact</a></li>{flags}</ul></div></div>'
        '<div class="fbottom"><span>© 2026 eSportly · <a href="https://example.org">Éditeur</a></span></div></div></footer>',
        "</body>", "</html>", ""])


HOME_PAGES = {lang: home_page(lang) for lang in an.LANGS}


def sitemap(block: str = "\r\n") -> str:
    return f"{SITEMAP_HEAD}{blog.SITEMAP_MARKERS[0]}{block}{blog.SITEMAP_MARKERS[1]}\r\n</urlset>\r\n"


def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def solo(page_id: str = "comprendre-le-bo5", **changes) -> dict:
    """Une page sans jeu (guide, ou note de version avec kind="release") telle que la rend load_pages."""
    return {**guide(**changes), "id": page_id}


class SiteCase(unittest.TestCase):
    """Un site factice : les pages des 14 jeux en 5 langues (marqueurs du lien de guide vides), les 5 modèles d'accueil du Blog, les 5
    accueils (leur pied de page) et le sitemap."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for lang in an.LANGS:
            write(self.root, an.TEMPLATES[lang], hub_template(lang))
            write(self.root, an.HOMES[lang], HOME_PAGES[lang])
            for game in blog.GAMES:
                write(self.root, f"{blog.GAME_DIRS[lang]}/{game}.html", game_page(lang, game))
        write(self.root, "sitemap.xml", sitemap())

    def write(self, name: str, content: str) -> None:
        write(self.root, name, content)

    def read(self, name: str) -> str:
        return (self.root / name).read_bytes().decode("utf-8")

    def publish(self, data: dict) -> None:
        """Écrit une page (telle que la rend load_pages) dans blog-src/pages/<id>.json."""
        self.write(f"blog-src/pages/{data['id']}.json", json.dumps({k: v for k, v in data.items() if k != "id"}, ensure_ascii=False))

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def apply(self, now=NOW) -> dict[str, str]:
        changes = blog.generate(self.root, now)
        for name, content in changes.items():
            self.write(name, content)
        return changes

    def failure(self, now=NOW) -> list[str]:
        with self.assertRaises(blog.BlogError) as caught:
            blog.generate(self.root, now)
        return caught.exception.problems

    def run_main(self, *argv, root=None, fetch=None, now=NOW) -> tuple[int, str, str]:
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = blog.main(list(argv), root=root or self.root, now=now, fetch=fetch)
        return code, out.getvalue(), err.getvalue()


def links(fragment: str, attribute: str = "hreflang") -> list[str]:
    """Adresses des liens qui portent l'attribut donné (hreflang : menu de langue de l'en-tête)."""
    return re.findall(rf'<a href="([^"]*)" {attribute}', fragment)


class Pages(SiteCase):
    def test_couverture_comme_image_de_partage(self):
        template = game_page("fr", "valorant")
        page = fiche("valorant", image={"kind": "ia"})
        main_html = blog.render_guide_main(page, "fr", {"valorant": "Valorant"}, ("../fr.html", "Accueil"), [], [], [])
        shown = blog.render_guide_page("fr", template, page, main_html, "", HOME_PAGES["fr"])
        self.assertIn('<meta property="og:image" content="https://esportly.eu/couvertures/valorant.webp">', shown)
        self.assertNotIn("partage/jeux/valorant.jpg", shown)
        for rule in (".cover img{display:block", ".art{display:grid", ".toc{order:-1", "main.wrap:has(.art){max-width:1240px}"):
            self.assertEqual(shown.count(rule), 1, rule)
        again = blog.render_guide_page("fr", shown, page, main_html, "", HOME_PAGES["fr"])
        self.assertEqual(again, shown)  # refabriquée, la page ne change pas

    def test_page_depuis_le_modele(self):
        template = game_page("fr", "valorant")
        page = fiche("valorant", fr={"title": "Valorant : le jeu", "description": "Ce qu'est Valorant."})
        main_html = blog.render_guide_main(page, "fr", {"valorant": "Valorant"}, ("../fr.html", "Accueil"), [], [], [])
        url = "https://esportly.eu/fr/blog/valorant"
        jsonld = blog.render_jsonld(page, "fr", url, [("Accueil", "https://esportly.eu/fr"), ("Blog", "https://esportly.eu/fr/blog"),
                                                      ("Valorant", url)])
        shown = blog.render_guide_page("fr", template, page, main_html, jsonld, HOME_PAGES["fr"])
        self.assertIn(f'<link rel="canonical" href="{url}">', shown)
        for lang in an.LANGS:
            self.assertIn(f'<link rel="alternate" hreflang="{lang}" href="https://esportly.eu/{blog.BLOG_DIRS[lang]}/valorant">', shown)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://esportly.eu/blog/valorant">', shown)
        menu = re.search(r"<header>.*?</header>", shown).group(0)
        self.assertEqual(links(menu), [f"../{blog.BLOG_DIRS[lang]}/valorant.html" for lang in an.LANGS] * 2)  # menu de langue, panneau mobile
        self.assertIn('<a href="../fr/blog/valorant.html" hreflang="fr" lang="fr" aria-current="page">', menu)
        self.assertIn('<a href="../../fr/blog.html" aria-current="page">Blog</a>', menu)
        self.assertEqual(shown.count('aria-current="page"'), 5)
        self.assertIn("<title>Valorant : le jeu</title>", shown)  # sans marque en suffixe (règle du skill titres-seo)
        self.assertIn('<meta name="description" content="Ce qu&#x27;est Valorant.">', shown)
        self.assertIn('<meta property="og:title" content="Valorant : le jeu">', shown)
        seo = {"/fr/blog/valorant": {"title": "Esport Valorant : Champions Tour, Masters et où regarder", "description": "L'esport Valorant."}}
        with_seo = blog.render_guide_page("fr", template, page, main_html, jsonld, HOME_PAGES["fr"], seo)
        self.assertIn("<title>Esport Valorant : Champions Tour, Masters et où regarder</title>", with_seo)
        self.assertIn('<meta name="description" content="L&#x27;esport Valorant.">', with_seo)
        self.assertIn('<meta property="og:title" content="Esport Valorant : Champions Tour, Masters et où regarder">', with_seo)
        self.assertIn('<meta property="og:description" content="L&#x27;esport Valorant.">', with_seo)
        self.assertIn("<h1>Valorant : le jeu</h1>", with_seo)  # le H1 et les données structurées gardent le titre de la page
        self.assertIn('"headline": "Valorant : le jeu"', with_seo)
        self.assertIn('<meta property="og:description" content="Ce qu&#x27;est Valorant.">', shown)
        self.assertIn('<meta property="og:image" content="https://esportly.eu/partage/jeux/valorant.jpg">', shown)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', shown)
        self.assertIn('<meta property="og:type" content="article">', shown)  # le modèle dit « website »
        self.assertNotIn('content="website"', shown)
        self.assertEqual([json.loads(payload)["@type"] for payload in LD_SCRIPT.findall(shown)], ["Article", "BreadcrumbList"])
        self.assertIn(jsonld + "\r\n", shown)
        self.assertNotIn("FAQPage", shown)
        self.assertEqual(re.findall(r'visite\?p=([^"&]*)', shown), ["/fr/blog/valorant"] * 5)  # boutons de la bêta (menu, panneau, encadré, pied de page), compteur
        self.assertIn(f'<main class="wrap">{main_html}</main>', shown)
        self.assertNotIn("Ancien héros", shown)
        # Hors de l'en-tête (le panneau des jeux du menu mène aux 14 jeux), seul le lien « Voir ce que fait eSportly pour
        # Valorant » mène encore à une page de jeu.
        body = re.sub(r"<header>.*?</header>", "", shown, flags=re.S)
        self.assertEqual([folder for folder in blog.GAME_DIRS.values() for _ in range(body.count(f"{folder}/valorant.html"))], ["games", "fr/jeux"])
        self.assertIn('<a href="../../fr/jeux/valorant.html">', main_html)
        self.assertEqual(shown.count(blog.BLOG_STYLE.replace("\n", "\r\n")), 1)
        self.assertEqual(blog.render_guide_page("fr", shown, page, main_html, jsonld, HOME_PAGES["fr"]), shown)  # deux appels : rien ne s'ajoute
        for fixed in (THEME, '<body style="--g:#ff89be">'):
            self.assertEqual((template.count(fixed), shown.count(fixed)), (1, 1))
        self.assertEqual((template.count(CSP), shown.count(MENU_CSP)), (1, 1))  # la CSP gagne l'empreinte du script du menu, rien d'autre
        self.assertEqual(shown.count("<script"), 4)  # le script du thème, les deux blocs de données structurées et celui du menu
        self.assertIsNone(re.search(r"(?<!\r)\n", shown))

    def test_csp_des_pages_a_videos(self):
        """Une page qui affiche des top plays reçoit le script de lecture au clic (une fois, avant </body>), son empreinte dans script-src
        et youtube-nocookie.com dans frame-src, juste avant object-src ; sinon ni script ni changement : la CSP est celle du modèle."""
        template = game_page("fr", "valorant")
        page = fiche("valorant", fr={"title": "Valorant : le jeu", "description": "Ce qu'est Valorant."})
        url = "https://esportly.eu/fr/blog/valorant.html"
        crumbs = [("Accueil", "https://esportly.eu/fr.html"), ("Blog", "https://esportly.eu/fr/blog.html"), ("Valorant", url)]
        jsonld = blog.render_jsonld(page, "fr", url, crumbs)
        with_videos = blog.render_guide_main(page, "fr", NAMES, HOME, VIDEOS, [], [])
        without = blog.render_guide_main(page, "fr", NAMES, HOME, [], [], [])
        self.assertIn('class="video"', with_videos)
        self.assertNotIn('class="video"', without)
        self.assertEqual(blog.EMBED_CSP, FRAME_SRC)

        # Le script : une ligne, sans dépendance, et son empreinte est bien le SHA-256 en base64 de son texte exact.
        self.assertNotIn("\n", blog.PLAYER_JS)
        self.assertNotIn("\r", blog.PLAYER_JS)
        self.assertNotIn("</", blog.PLAYER_JS)
        self.assertNotIn("http://", blog.PLAYER_JS)
        self.assertEqual(re.findall(r"https://[^\"']+", blog.PLAYER_JS), ["https://www.youtube-nocookie.com/embed/"])
        for absent in ("import", "require", "fetch", "XMLHttpRequest", "innerHTML", "eval", "localStorage", "document.cookie"):
            self.assertNotIn(absent, blog.PLAYER_JS)
        self.assertEqual(blog.PLAYER_HASH, base64.b64encode(hashlib.sha256(blog.PLAYER_JS.encode("utf-8")).digest()).decode())
        token = f"'sha256-{blog.PLAYER_HASH}'"

        shown = blog.render_guide_page("fr", template, page, with_videos, jsonld, HOME_PAGES["fr"])
        scripts = re.findall(r"<script>(.*?)</script>", shown, re.S)
        self.assertEqual(scripts.count(blog.PLAYER_JS), 1)  # la copie dans la page est identique au texte haché
        self.assertIn(f"\r\n<script>{blog.PLAYER_JS}</script>\r\n</body>", shown)  # sur sa ligne, juste avant </body>
        self.assertEqual(shown.count("<script"), 5)  # le script du thème, les deux blocs de données structurées, le menu et le lecteur
        meta = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">')
        policy, old_policy = meta.search(shown).group(1), meta.search(template).group(1)
        self.assertEqual(shown.count("frame-src"), 1)
        self.assertEqual(shown.count(FRAME_SRC), 1)
        self.assertEqual(shown.count(token), 1)
        expected = old_policy.replace("script-src 'sha256-THEME='", f"script-src 'sha256-THEME=' {MENU_TOKEN} {token}")
        expected = expected.replace("object-src 'none'", f"{FRAME_SRC}; object-src 'none'")
        self.assertEqual(policy, expected)  # l'empreinte en fin de script-src, frame-src juste avant object-src, rien d'autre
        self.assertIn(f"connect-src 'self'; {FRAME_SRC}; object-src 'none'; base-uri 'none'", policy)
        self.assertEqual(shown.count(CSP), 0)
        # Deux appels : ni le script, ni l'empreinte, ni la directive ne sont ajoutés une seconde fois.
        self.assertEqual(blog.render_guide_page("fr", shown, page, with_videos, jsonld, HOME_PAGES["fr"]), shown)
        # Le reste de l'en-tête n'est pas touché.
        plain = blog.render_guide_page("fr", template, page, without, jsonld, HOME_PAGES["fr"])
        head = lambda text: text.split("<main")[0]
        self.assertEqual(head(shown).replace(f"{FRAME_SRC}; ", "", 1).replace(f" {token}", "", 1), head(plain))
        self.assertEqual(shown.replace(f"<script>{blog.PLAYER_JS}</script>\r\n", "").split("</main>")[1], plain.split("</main>")[1])
        # Sans vidéo : ni script du lecteur, ni son empreinte ; la CSP est celle du modèle plus l'empreinte du menu.
        self.assertEqual(plain.count("<script"), 4)
        self.assertNotIn(blog.PLAYER_JS, plain)
        self.assertNotIn(blog.PLAYER_HASH, plain)
        self.assertEqual(plain.count(MENU_CSP), 1)
        self.assertNotIn("frame-src", plain)
        self.assertEqual(blog.render_guide_page("fr", plain, page, without, jsonld, HOME_PAGES["fr"]), plain)
        # Une directive ou une empreinte déjà présentes dans le modèle ne se dupliquent pas.
        already = template.replace("object-src 'none'", f"{FRAME_SRC}; object-src 'none'").replace("'sha256-THEME='", f"'sha256-THEME=' {token}")
        again = blog.render_guide_page("fr", already, page, with_videos, jsonld, HOME_PAGES["fr"])
        self.assertEqual((again.count(FRAME_SRC), again.count(token), again.count(blog.PLAYER_JS)), (1, 1, 1))

    def test_csp_sans_script_src(self):
        """Sans script-src dans la CSP du modèle, on n'invente pas la directive (elle changerait ce que default-src autorise) : erreur,
        avec ou sans top plays (le script du menu y est toujours)."""
        template = game_page("fr", "valorant").replace("script-src 'sha256-THEME='; ", "")
        self.assertNotIn("script-src", template)
        page = fiche("valorant")
        for videos in (VIDEOS, []):
            with self.subTest(videos=len(videos)), self.assertRaises(blog.BlogError) as caught:
                blog.render_guide_page("fr", template, page, blog.render_guide_main(page, "fr", NAMES, HOME, videos, [], []), "", HOME_PAGES["fr"])
            self.assertEqual(len(caught.exception.problems), 1)
            self.assertIn("script-src", caught.exception.problems[0])

    def test_csp_sans_object_src(self):
        """Sans object-src 'none' dans la CSP du modèle, on ne devine pas où mettre frame-src : erreur, sauf sur une page sans lecteur."""
        template = game_page("fr", "valorant").replace("object-src 'none'; ", "")
        self.assertNotIn("object-src", template)
        page = fiche("valorant")
        with_videos = blog.render_guide_main(page, "fr", NAMES, HOME, VIDEOS, [], [])
        with self.assertRaises(blog.BlogError) as caught:
            blog.render_guide_page("fr", template, page, with_videos, "", HOME_PAGES["fr"])
        self.assertEqual(len(caught.exception.problems), 1)
        self.assertIn("object-src 'none'", caught.exception.problems[0])
        self.assertIn("frame-src", caught.exception.problems[0])
        # Sans lecteur, la page se fabrique et la CSP du modèle ne gagne que l'empreinte du menu.
        shown = blog.render_guide_page("fr", template, page, blog.render_guide_main(page, "fr", NAMES, HOME, [], [], []), "", HOME_PAGES["fr"])
        self.assertEqual(shown.count(re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', template).group(0)
                                     .replace("'sha256-THEME='", f"'sha256-THEME=' {MENU_TOKEN}")), 1)
        # Un modèle sans balise de CSP ne passe pas non plus.
        with self.assertRaises(blog.BlogError):
            blog.render_guide_page("fr", re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>\r\n', "", game_page("fr", "valorant")),
                                   page, with_videos, "", HOME_PAGES["fr"])

    def test_modele_du_meme_jeu(self):
        for data in (fiche("valorant"), fiche("league-of-legends"), solo(), article("bo5-valorant", "2026-10-21")):
            self.publish(data)
        changes = blog.generate(self.root, NOW)
        expected = {"valorant": "valorant", "league-of-legends": "league-of-legends", "comprendre-le-bo5": "league-of-legends",
                    "bo5-valorant": "valorant"}
        for page_id, game in expected.items():
            with self.subTest(page=page_id):
                shown = changes[f"fr/blog/{page_id}.html"]
                self.assertIn(f'<body style="--g:{COLORS[game]}">', shown)
                self.assertIn(f'<meta property="og:image" content="https://esportly.eu/partage/jeux/{game}.jpg">', shown)
                self.assertIn(f'<link rel="canonical" href="https://esportly.eu/fr/blog/{page_id}">', shown)
                self.assertEqual(links(shown), [f"../{blog.BLOG_DIRS[lang]}/{page_id}.html" for lang in an.LANGS] * 3)
                self.assertIn(f"visite?p=/fr/blog/{page_id}\"", shown)

    def test_accueil_depuis_le_modele(self):
        template = hub_template("fr")
        main_html = blog.render_hub_main("fr", [fiche("valorant")], {"valorant": "Valorant"})
        shown = blog.render_hub_page("fr", template, main_html, HOME_PAGES["fr"])
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/blog">', shown)
        for lang in an.LANGS:
            self.assertIn(f'<link rel="alternate" hreflang="{lang}" href="https://esportly.eu/{blog.HUBS[lang][:-5]}">', shown)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://esportly.eu/blog">', shown)
        self.assertNotIn("application/rss+xml", shown)
        self.assertNotIn(".xml", shown)
        self.assertEqual(links(shown), [blog.HUBS[lang] for lang in an.LANGS] * 3)  # menu de langue, panneau mobile, pied de page
        self.assertIn('<a href="fr/blog.html" hreflang="fr" lang="fr" aria-current="page">', shown)
        self.assertIn('<a href="../fr/blog.html" aria-current="page">Blog</a>', shown)
        self.assertEqual(re.findall(r'visite\?p=([^"&]*)', shown), ["/fr/blog"] * 4)  # boutons de la bêta (menu, panneau, pied de page), compteur
        self.assertIn("<title>Guides esport : chaque jeu et sa scène pro</title>", shown)
        self.assertIn("<h1>Les jeux derrière les matchs</h1>", shown)  # le titre de la page change, pas le H1
        self.assertIn('<meta name="description" content="Ce qu&#x27;est chaque jeu, comment', shown)
        self.assertIn('<meta property="og:title" content="Guides esport : chaque jeu et sa scène pro">', shown)
        titles = {"en": "Esports guides: every game and its pro scene", "fr": "Guides esport : chaque jeu et sa scène pro",
                  "es": "Guías de esports: cada juego y su escena profesional",
                  "de": "E-Sport-Guides: jedes Spiel und seine Profiszene",
                  "pt-BR": "Guias de esports: cada jogo e sua cena profissional"}
        for lang, title in titles.items():
            with self.subTest(lang=lang):
                hub = blog.render_hub_page(lang, hub_template(lang), "", HOME_PAGES[lang])
                self.assertIn(f"<title>{html.escape(title)}</title>", hub)
                self.assertLessEqual(len(title), 70)
        seo = {"/fr/blog": {"title": "Guide esport : chaque jeu, sa scène pro, comment la suivre", "description": "Le guide."}}
        hub = blog.render_hub_page("fr", hub_template("fr"), "", HOME_PAGES["fr"], seo)
        self.assertIn("<title>Guide esport : chaque jeu, sa scène pro, comment la suivre</title>", hub)
        self.assertIn('<meta property="og:description" content="Le guide.">', hub)
        self.assertNotIn("Guide esport : chaque jeu, sa scène pro", hub.split("</head>")[1])  # le title SEO ne touche pas au corps
        self.assertIn('<meta property="og:image" content="https://esportly.eu/apercu.png?v=2">', shown)
        self.assertIn(f'<main class="wrap">{main_html}</main>', shown)
        self.assertNotIn("ANCIEN HÉROS", shown)
        self.assertNotIn("application/ld+json", shown)
        self.assertEqual(shown.count(blog.BLOG_STYLE.replace("\n", "\r\n")), 1)
        self.assertEqual(blog.render_hub_page("fr", shown, main_html, HOME_PAGES["fr"]), shown)
        for fixed in (MENU_CSP, THEME, '<body style="--g:#FFC53D">'):
            self.assertEqual(shown.count(fixed), 1)
        self.assertIsNone(re.search(r"(?<!\r)\n", shown))

    def test_noms_et_accueil_lus_dans_le_fil_d_ariane(self):
        self.assertEqual(blog.read_home(game_page("fr", "valorant")), ("../../fr.html", "Accueil"))
        self.assertEqual(blog.read_home(game_page("en", "valorant")), ("../", "Home"))
        self.assertEqual(blog.read_home('<nav class="crumbs"><a href="../a.html?x=1&amp;y=2">A &amp; B</a> › <span>J</span></nav>'),
                         ("../a.html?x=1&y=2", "A & B"))  # texte décodé : les fragments l'échappent de nouveau
        with self.assertRaises(blog.BlogError):
            blog.read_home("<main></main>")
        (self.root / blog.GAME_DIRS["de"] / "dota-2.html").unlink()
        self.write("games/valorant.html", game_page("en", "valorant").replace("<span>Valorant</span>", "<span>Val &amp; &lt;b&gt;</span>"))
        names = blog.read_names(self.root)
        self.assertEqual(set(names), set(an.LANGS))
        self.assertEqual(names["fr"], GAME_NAMES)
        self.assertNotIn("dota-2", names["de"])
        self.assertEqual(len(names["de"]), 13)
        self.assertEqual(names["en"]["valorant"], "Val & <b>")


class Generation(SiteCase):
    def test_lien_de_guide_sur_la_page_du_jeu(self):
        self.publish(fiche("valorant"))
        self.write("games/dota-2.html", game_page("en", "dota-2", block='<p class="guide"><a href="../blog/dota-2.html">Ancien lien</a></p>'))
        self.write("fr/jeux/rocket-league.html", game_page("fr", "rocket-league", block=None))
        changes = blog.generate(self.root, NOW)
        for lang in an.LANGS:
            name = f"{blog.GAME_DIRS[lang]}/valorant.html"
            link = blog.render_guide_link(fiche("valorant"), lang, "Valorant")
            self.assertEqual(changes[name], game_page(lang, "valorant", block=link))
        self.assertIn('<!-- blog-guide --><p class="guide"><a href="../blog/valorant.html">Guide: Valorant, the game and its pro scene →</a></p>'
                      '<!-- /blog-guide -->\r\n<h2>Autres jeux</h2>', changes["games/valorant.html"])
        self.assertEqual(changes["games/dota-2.html"], game_page("en", "dota-2"))  # sans fiche visible : bloc vidé
        self.assertNotIn("fr/jeux/rocket-league.html", changes)  # sans marqueurs ni fiche : rien à dire
        self.assertNotIn("games/league-of-legends.html", changes)  # bloc déjà vide
        self.write("fr/jeux/valorant.html", game_page("fr", "valorant", block=None))
        found = self.failure()
        self.assertEqual(len(found), 1, found)
        self.assertIn("fr/jeux/valorant.html", found[0])
        self.assertIn("<!-- blog-guide -->", found[0])

    def test_sitemap(self):
        self.publish(fiche("valorant", updated="2026-10-22"))
        self.publish(fiche("league-of-legends"))  # mise à jour le 2026-10-20
        self.publish(solo("note-1", kind="release", date="2026-10-21", updated="2026-10-25"))
        changes = blog.generate(self.root, NOW)
        block = an.extract_between(changes["sitemap.xml"], *blog.SITEMAP_MARKERS)
        self.assertEqual(changes["sitemap.xml"], sitemap(block))  # rien d'autre ne change
        self.assertTrue(block.startswith("\r\n<url>") and block.endswith("</url>\r\n"), block[:40])
        lines = block[2:-2].split("\r\n")
        self.assertEqual(len(lines), 20)  # 5 accueils + 3 pages × 5 langues
        locs = [re.match(r"<url><loc>https://esportly\.eu/([^<]*)</loc>", line).group(1) for line in lines]
        self.assertEqual(locs, sorted(locs))
        self.assertEqual(set(locs), {*(hub[:-5] for hub in blog.HUBS.values()), *(f"{folder}/{page_id}" for folder in blog.BLOG_DIRS.values()
                                                              for page_id in ("valorant", "league-of-legends", "note-1"))})
        alternates = "".join(f'<xhtml:link rel="alternate" hreflang="{lang}" href="https://esportly.eu/{blog.BLOG_DIRS[lang]}/valorant"/>'
                             for lang in an.LANGS)
        self.assertIn('<url><loc>https://esportly.eu/fr/blog/valorant</loc><lastmod>2026-10-22</lastmod><changefreq>weekly</changefreq>'
                      f'{alternates}<xhtml:link rel="alternate" hreflang="x-default" href="https://esportly.eu/blog/valorant"/></url>', lines)
        self.assertIn("<lastmod>2026-10-20</lastmod>", lines[locs.index("es/blog/league-of-legends")])
        self.assertIn("<lastmod>2026-10-25</lastmod>", lines[locs.index("pt/blog/note-1")])
        hub = lines[locs.index("de/blog")]
        self.assertIn("<lastmod>2026-10-25</lastmod>", hub)  # la plus récente des mises à jour visibles
        self.assertIn('hreflang="fr" href="https://esportly.eu/fr/blog"/>', hub)
        self.assertTrue(hub.endswith('<xhtml:link rel="alternate" hreflang="x-default" href="https://esportly.eu/blog"/></url>'))
        for line in lines:
            self.assertEqual(line.count("<xhtml:link "), 6)
            self.assertEqual(line.count("<changefreq>weekly</changefreq>"), 1)
        self.assertEqual(blog.sitemap_block([], "\n"), "\n")
        self.assertEqual(blog.sitemap_block([fiche("valorant")], "\n").count("\n"), 11)
        self.write("sitemap.xml", SITEMAP_HEAD + "</urlset>\r\n")
        found = self.failure()
        self.assertEqual(len(found), 1, found)
        self.assertIn("sitemap.xml", found[0])
        self.assertIn("<!-- blog -->", found[0])

    def test_adresses_declarees_sans_extension(self):
        """Le Worker renvoie (307) toute adresse en .html vers la même sans .html : aucune adresse déclarée des pages du Blog
        (canonical, hreflang, og:url, données structurées) ni de son bloc du sitemap ne finit par .html, et ce bloc liste exactement
        les canonicals des pages produites, que les modèles soient encore en .html ou déjà convertis (public_urls)."""
        for converted in (False, True):
            with self.subTest(converted=converted):
                if converted:
                    for path in sorted(self.root.rglob("*.html")):
                        path.write_bytes(an.public_urls(path.read_bytes().decode("utf-8")).encode("utf-8"))
                for data in (fiche("valorant"), fiche("league-of-legends"), solo(), article("bo5-valorant", "2026-10-21")):
                    self.publish(data)
                changes = blog.generate(self.root, NOW)
                produced = {name: content for name, content in changes.items()
                            if name in blog.HUBS.values() or name.rsplit("/", 1)[0] in blog.BLOG_DIRS.values()}
                self.assertEqual(len(produced), 25)
                canonicals = set()
                for name, content in produced.items():
                    self.assertEqual([url for url in declared(content) if ".html" in url], [], name)
                    canonicals.add(re.search(r'<link rel="canonical" href="([^"]*)"', content).group(1))
                    self.assertEqual(blog.generate(self.root, NOW).get(name), content)
                block = an.extract_between(changes["sitemap.xml"], *blog.SITEMAP_MARKERS)
                self.assertEqual([url for url in declared(block) if ".html" in url], [])
                self.assertEqual(re.findall(r"<loc>([^<]*)</loc>", block), sorted(canonicals))

    def test_titres_seo_lus_dans_le_fichier(self):
        self.publish(fiche("valorant"))
        (self.root / "seo").mkdir()
        self.write("seo/titres.json", json.dumps({"/fr/blog/valorant": {"title": "Esport Valorant : Champions Tour et Masters", "description": "Valorant."},
                                                  "/fr/blog": {"title": "Guide esport : chaque jeu et sa scène", "description": "Le guide."}}, ensure_ascii=False))
        changes = self.apply()
        self.assertIn("<title>Esport Valorant : Champions Tour et Masters</title>", changes["fr/blog/valorant.html"])
        self.assertIn('<meta name="description" content="Valorant.">', changes["fr/blog/valorant.html"])
        self.assertIn("<title>Guide esport : chaque jeu et sa scène</title>", changes["fr/blog.html"])
        self.assertIn("<title>Titre en</title>", changes["blog/valorant.html"])  # page absente du fichier : son titre, sans marque
        self.assertEqual(self.apply(), {})  # refabriquées : identiques
        self.write("seo/titres.json", '{"/fr/blog": "pas un objet"}')
        self.assertEqual(self.failure(), ["seo/titres.json : un objet {chemin: {title, description}} attendu"])

    def test_75_pages_pour_14_fiches(self):
        for game in blog.GAMES:
            self.publish(fiche(game))
        changes = blog.generate(self.root, NOW)
        pages = {f"{blog.BLOG_DIRS[lang]}/{game}.html" for lang in an.LANGS for game in blog.GAMES}
        games = {f"{blog.GAME_DIRS[lang]}/{game}.html" for lang in an.LANGS for game in blog.GAMES}
        self.assertEqual(set(changes), {*blog.HUBS.values(), *pages, *games, "sitemap.xml"})
        self.assertEqual(len(changes), 5 + 70 + 70 + 1)
        self.assertEqual(changes["sitemap.xml"].count("<url>") - sitemap().count("<url>"), 75)
        self.assertEqual(re.findall(r'<a class="card" data-game="[^"]*" href="blog/([^"]*)\.html"', changes["blog.html"]), list(blog.GAMES))
        self.assertIn("<b>Mobile Legends: Bang Bang</b>", changes["pt/blog.html"])
        others = re.search(r'<nav class="others" aria-label="Other games">(.*?)</nav>', changes["blog/valorant.html"]).group(1)
        self.assertEqual(re.findall(r'href="([^"]*)\.html"', others), [game for game in blog.GAMES if game != "valorant"])

    def test_top_plays_reserves_a_la_page_de_jeu(self):
        """Spec §7 : seule la fiche d'un jeu affiche ses top plays ; un guide ou une note de version du jeu n'a ni bloc, ni lecteur, ni frame-src."""
        self.publish(fiche("valorant"))
        self.publish(article("bo5", "2026-10-21"))  # guide rattaché à valorant
        self.publish(solo("note-1", kind="release", game="valorant", date="2026-10-22", updated="2026-10-22"))  # note de version rattachée à valorant
        self.write("blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": VIDEOS}}))
        changes = blog.generate(self.root, NOW)
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                folder, template = blog.BLOG_DIRS[lang], game_page(lang, "valorant")
                game_shown = changes[f"{folder}/valorant.html"]  # la fiche du jeu garde le bloc, le script de lecture et la CSP élargie
                self.assertEqual(game_shown.count('class="video"'), 3)
                self.assertNotIn("<iframe", game_shown)  # aucun lecteur avant le clic
                self.assertNotIn("youtube-nocookie.com/embed/aB3", game_shown)
                self.assertEqual(game_shown.count('class="topplays"'), 1)
                self.assertIn(blog.LABELS[lang]["topplays"], game_shown)
                self.assertIn(blog.LABELS[lang]["topnote"], game_shown)
                self.assertEqual(game_shown.count(FRAME_SRC), 1)
                self.assertEqual(game_shown.count(f"<script>{blog.PLAYER_JS}</script>"), 1)
                self.assertEqual(game_shown.count(f"'sha256-{blog.PLAYER_HASH}'"), 1)
                for page_id in ("bo5", "note-1"):
                    shown = changes[f"{folder}/{page_id}.html"]
                    self.assertIn(f'src="{"../" if lang == "en" else "../../"}logos-jeux/valorant.png"', shown)  # rattachée à valorant : logo gardé
                    self.assertIn(blog.LABELS[lang]["follow"].format(game="Valorant"), shown)  # ... et son encadré « Suivre » aussi
                    self.assertNotIn("<iframe", shown, page_id)
                    self.assertNotIn('class="video"', shown, page_id)
                    self.assertNotIn(blog.PLAYER_JS, shown, page_id)
                    self.assertNotIn(blog.PLAYER_HASH, shown, page_id)
                    self.assertNotIn('class="topplays"', shown, page_id)  # (les règles de BLOG_STYLE, elles, sont sur toutes les pages)
                    self.assertNotIn('class="topnote"', shown, page_id)
                    self.assertNotIn(blog.LABELS[lang]["topplays"], shown, page_id)
                    self.assertNotIn("youtube", shown, page_id)
                    self.assertNotIn("frame-src", shown, page_id)
                    self.assertEqual(shown.count(MENU_CSP), 1, page_id)  # CSP du modèle, plus la seule empreinte du menu
                    self.assertEqual(re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', shown).group(0),
                                     re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', template).group(0)
                                     .replace("'sha256-THEME='", f"'sha256-THEME=' {MENU_TOKEN}"), page_id)
        # La fiche du jeu liste le guide, et seule la fiche reçoit les cartes de lecture et leur script.
        self.assertIn('<a href="bo5.html">', changes["blog/valorant.html"])
        self.assertEqual(sum(content.count('class="video"') for content in changes.values()), 3 * 5)
        self.assertEqual(sum(content.count(blog.PLAYER_JS) for content in changes.values()), 5)
        self.assertEqual(sum(content.count("<iframe") for content in changes.values()), 0)

    def test_csp_sans_object_src_nomme_le_modele(self):
        self.publish(fiche("valorant"))
        self.publish(fiche("league-of-legends"))
        self.write("blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": VIDEOS}}))
        self.write("fr/jeux/valorant.html", game_page("fr", "valorant").replace("object-src 'none'; ", ""))
        self.write("fr/jeux/league-of-legends.html", game_page("fr", "league-of-legends").replace("object-src 'none'; ", ""))  # sans vidéo : sans effet
        before = self.snapshot()
        found = self.failure()
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("fr/jeux/valorant.html : "), found)
        self.assertIn("CSP sans object-src 'none', impossible d'ajouter frame-src", found[0])
        self.assertEqual(self.snapshot(), before)

    def test_pages_futures_et_orphelines(self):
        self.publish(fiche("valorant", date="2026-10-28", updated="2026-10-28"))
        self.assertEqual(blog.generate(self.root, NOW), {})  # publiée demain : aucune sortie aujourd'hui
        self.assertIn("fr/blog/valorant.html", blog.generate(self.root, NOW + timedelta(days=1)))
        self.write("blog/ancienne.html", "<html></html>\r\n")
        self.write("de/blog.html", "<html></html>\r\n")
        before = self.snapshot()
        found = self.failure()
        self.assertEqual(len(found), 2, found)
        self.assertTrue(found[0].startswith("blog/ancienne.html : page orpheline"), found)  # triées par chemin
        self.assertTrue(found[1].startswith("de/blog.html : page orpheline"), found)
        code, out, err = self.run_main()
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("Refus : 2 problème(s)\n  - blog/ancienne.html : page orpheline"), err)
        self.assertEqual(self.snapshot(), before)  # rien d'écrit, rien de supprimé
        found = self.failure(NOW + timedelta(days=1))  # l'accueil allemand est maintenant attendu, la page ancienne ne l'est toujours pas
        self.assertEqual(len(found), 1, found)
        self.assertIn("blog/ancienne.html", found[0])

    def test_idempotence_et_fins_de_ligne(self):
        for data in (fiche("valorant"), fiche("league-of-legends"), article("bo5", "2026-10-21"), solo("note-1", kind="release")):
            self.publish(data)
        self.write("blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": VIDEOS}}))
        changes = self.apply()
        self.assertEqual(len(changes), 5 + 20 + 10 + 1)
        for name, content in changes.items():
            self.assertIsNone(re.search(r"(?<!\r)\n", content), name)
        self.assertIn("Top plays right now", changes["blog/valorant.html"])
        self.assertNotIn("Top plays", changes["blog/league-of-legends.html"])
        for lang in an.LANGS:  # la CSP ne change que sur les pages qui affichent des top plays (la fiche du jeu valorant, dans les 5 langues)
            shown = changes[f"{blog.BLOG_DIRS[lang]}/valorant.html"]
            self.assertEqual(shown.count('class="video"'), 3, lang)
            self.assertEqual(shown.count(FRAME_SRC), 1, lang)
            self.assertIn(f"{FRAME_SRC}; object-src 'none'", shown)
            self.assertEqual(shown.count(blog.PLAYER_JS), 1, lang)
            for page_id in ("league-of-legends", "bo5", "note-1"):  # sans vidéo (fiche sans top plays, guide du jeu, note sans jeu) : CSP du modèle
                shown = changes[f"{blog.BLOG_DIRS[lang]}/{page_id}.html"]
                self.assertNotIn('class="video"', shown)
                self.assertNotIn(blog.PLAYER_JS, shown)
                self.assertNotIn("frame-src", shown)
                self.assertEqual(shown.count(MENU_CSP), 1, (lang, page_id))
            self.assertNotIn("frame-src", changes[blog.HUBS[lang]])  # l'accueil n'affiche jamais de vidéo
            self.assertEqual(changes[blog.HUBS[lang]].count(MENU_CSP), 1, lang)
            self.assertNotIn("frame-src", changes[f"{blog.GAME_DIRS[lang]}/valorant.html"])  # la page de jeu existante ne gagne que son lien de guide
        self.assertIn('<a href="bo5.html">', changes["blog/valorant.html"])  # « Articles about Valorant »
        self.assertNotIn('<a href="bo5.html">', changes["blog/bo5.html"])  # un article ne se liste pas lui-même
        ld = [json.loads(payload) for payload in LD_SCRIPT.findall(changes["fr/blog/valorant.html"])]
        self.assertEqual([(item["name"], item["item"]) for item in ld[1]["itemListElement"]],
                         [("Accueil", "https://esportly.eu/fr"), ("Blog", "https://esportly.eu/fr/blog"),
                          ("Valorant", "https://esportly.eu/fr/blog/valorant")])
        self.assertEqual(json.loads(LD_SCRIPT.findall(ld_source := changes["fr/blog/valorant.html"])[0])["mainEntityOfPage"],
                         "https://esportly.eu/fr/blog/valorant")
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/blog/valorant">', ld_source)
        self.assertEqual(json.loads(LD_SCRIPT.findall(changes["blog/bo5.html"])[1])["itemListElement"][0]["item"], "https://esportly.eu/")
        self.assertEqual(json.loads(LD_SCRIPT.findall(changes["blog/bo5.html"])[1])["itemListElement"][2]["name"], "Guide bo5 en")
        after = self.snapshot()
        self.assertEqual(blog.generate(self.root, NOW), {})
        self.assertEqual(self.snapshot(), after)

    def test_main(self):
        with tempfile.TemporaryDirectory() as tmp:  # --verifier : blog-src seul, sans modèles ni base des fuseaux
            bare = Path(tmp)
            write(bare, "blog-src/pages/note-1.json", json.dumps(guide(kind="release")))
            write(bare, "blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": VIDEOS}}))
            with mock.patch.object(an, "paris", side_effect=AssertionError("fuseau demandé")):
                self.assertEqual(self.run_main("--verifier", root=bare), (0, "blog-src : valide\n", ""))
            write(bare, "blog-src/channels.json", "[]")
            write(bare, "blog-src/topplays.json", "{")
            code, out, err = self.run_main("--verifier", root=bare)
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("Refus : 2 problème(s)\n  - channels.json : "), err)
            self.assertIn("\n  - topplays.json : illisible", err)
        self.publish(fiche("valorant"))
        before = self.snapshot()
        self.assertEqual(self.run_main("--essai"), (0, "16 fichier(s) à changer.\n", ""))
        self.assertEqual(self.snapshot(), before)
        expected = blog.generate(self.root, NOW)
        self.assertEqual(self.run_main(), (0, "16 fichier(s) changé(s).\n", ""))
        for name, content in expected.items():
            self.assertEqual(self.read(name), content)
        self.assertEqual(self.run_main(), (0, "0 fichier(s) changé(s).\n", ""))
        self.publish(solo("mauvaise", kind="article"))
        before = self.snapshot()
        code, out, err = self.run_main()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("  - mauvaise.json : kind : « article » invalide", err)
        self.assertEqual(self.snapshot(), before)


# --- Le menu du site sur les pages du Blog ----------------------------------------------------------------------
# Le menu des accueils (index.html, fr.html, es.html, de.html, pt.html) : barre du haut, bouton de la bêta, sélecteur de thème,
# menu burger. Les libellés sont recopiés des accueils (test_menu_identique_aux_accueils le vérifie sur l'arbre de travail) ;
# la barre finit par la page News puis « Blog », comme le panneau mobile.

REAL = Path(__file__).resolve().parents[2]
MENUS = {  # (aria-label de la barre, barre, panneau mobile, bouton de la bêta, sélecteur de thème)
    "en": ("Sections", ["eSportly+", "News", "Blog", "Live"],
           ["eSportly+", "News", "Blog", "Live"], "Join the beta",
           ["Theme", "System theme", "Light theme", "Dark theme"]),
    "fr": ("Sections de la page", ["eSportly+", "Actualités", "Blog", "Live"],
           ["eSportly+", "Actualités", "Blog", "Live"], "Rejoindre la bêta",
           ["Thème", "Thème du système", "Thème clair", "Thème sombre"]),
    "es": ("Secciones", ["eSportly+", "Noticias", "Blog", "Live"],
           ["eSportly+", "Noticias", "Blog", "Live"], "Únete a la beta",
           ["Tema", "Tema del sistema", "Tema claro", "Tema oscuro"]),
    "de": ("Abschnitte", ["eSportly+", "Nachrichten", "Blog", "Live"],
           ["eSportly+", "Nachrichten", "Blog", "Live"], "Zur Beta",
           ["Design", "Systemdesign", "Helles Design", "Dunkles Design"]),
    "pt-BR": ("Seções", ["eSportly+", "Notícias", "Blog", "Live"],
              ["eSportly+", "Notícias", "Blog", "Live"], "Entrar na beta",
              ["Tema", "Tema do sistema", "Tema claro", "Tema escuro"]),
}
BAR_ANCHORS = ["offres"]  # « Équipes » n'est plus une ancre mais un panneau
PANEL_ANCHORS = ["offres"]
# Empreinte du script du thème et du menu, telle que la CSP des pages la porte. Lue dans site_chrome plutôt qu'écrite ici :
# le script évolue (recherche d'équipe, panneaux), et une empreinte recopiée à la main serait fausse au premier changement.
HOME_SCRIPT_HASH = blog.MENU_HASH
MENU_TOKEN = f"'sha256-{HOME_SCRIPT_HASH}'"
MENU_CSP = CSP.replace("'sha256-THEME='", f"'sha256-THEME=' {MENU_TOKEN}")  # la CSP du modèle, plus l'empreinte du script du menu
TEMPLATE_HEADER_CLASSES = {"brand", "lang", "langs", "flag", "chev"}  # classes de l'en-tête que les pages modèles définissent déjà
# Un lien du menu peut porter une icône (« eSportly+ » en a une sur les accueils) : on compare les libellés, pas le balisage,
# sinon une image ajoutée d'un côté fait disparaître l'entrée de la comparaison au lieu de la signaler.
LINK = re.compile(r'<a (?:class="live" )?href="([^"]*)"( aria-current="page")?>(.*?)</a>', re.S)
TAGS = re.compile(r"<[^>]+>")
# Les panneaux (jeux, équipes) : leurs liens sont des logos et des raccourcis, pas des entrées de menu. Le panneau des équipes
# porte « mega team » dans la barre et « megam » dans le burger, comme celui des jeux.
MEGA = re.compile(r'<details class="mega(?: team)?">.*?</details>|<details class="megam(?: team)?">.*?</details>', re.S)


def home_link(lang: str, prefix: str) -> str:
    """Le lien de l'accueil de la langue, comme dans le fil d'Ariane des pages du site (« ../fr.html », « ../ », « fr.html », « ./ »)."""
    return (prefix or "./") if lang == "en" else prefix + an.HOMES[lang]


def menu_of(text: str) -> dict:
    """Les parties du menu d'une page (accueil ou page du Blog) : barre, panneau mobile, bouton de la bêta, thème, langues."""
    header = re.search(r"<header>.*?</header>", text, re.S).group(0)
    nav = re.search(r'<nav aria-label="([^"]*)">(.*?)<details class="lang langs">(.*?)</details>(.*?)</nav>', header, re.S)
    panel = re.search(r'<details class="menu"><summary aria-label="Menu">(.*?)</summary><div class="panel" role="navigation" '
                      r'aria-label="Menu">(.*?)<a class="soonm"[^>]*href="([^"]*)"[^>]*>(.*?)</a><div class="langsm">(.*?)</div></div></details>',
                      header, re.S)
    # Le bouton « Rejoindre la bêta » est devenu un badge App Store (une image dans le lien) : le motif accepte les deux
    # formes, sinon tout le test du menu tombe sur un détail de présentation.
    soon = re.search(r'<a class="soon"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', header, re.S)
    theme = re.search(r'<div class="theme" id="theme" role="group" aria-label="[^"]*" hidden>.*?</div>', text)  # flottant, après le pied de page
    def texts(found):
        return [(href, current, TAGS.sub("", label).strip()) for href, current, label in found]

    return {"label": nav.group(1), "bar": texts(LINK.findall(MEGA.sub("", nav.group(2)))), "langs": links(nav.group(3)), "theme": theme.group(0),
            "theme_labels": re.findall(r'aria-label="([^"]*)"', theme.group(0)), "soon": soon.groups(), "icons": panel.group(1),
            "panel": texts(LINK.findall(MEGA.sub("", panel.group(2)))), "soonm": (panel.group(3), panel.group(4)), "langsm": links(panel.group(5))}


class Menu(SiteCase):
    def pages(self) -> dict[str, str]:
        """Les pages du Blog d'un petit site : la fiche valorant (avec top plays) et un guide sans jeu, plus les 5 accueils."""
        self.publish(fiche("valorant"))
        self.publish(solo())
        self.write("blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": VIDEOS}}))
        changes = blog.generate(self.root, NOW)
        return {name: content for name, content in changes.items()
                if name in blog.HUBS.values() or name.rsplit("/", 1)[0] in blog.BLOG_DIRS.values()}

    def test_menu_complet_sur_chaque_page(self):
        pages = self.pages()
        self.assertEqual(len(pages), 15)
        for name, shown in pages.items():
            lang = next(lang for lang in an.LANGS if name in (blog.HUBS[lang], f"{blog.BLOG_DIRS[lang]}/valorant.html",
                                                              f"{blog.BLOG_DIRS[lang]}/comprendre-le-bo5.html"))
            hub = name == blog.HUBS[lang]
            prefix, path = site_chrome.prefix_for(name), name[:-5]  # « ../ » par dossier : « ../../ » pour fr/blog/valorant.html
            label, bar, panel, beta, theme = MENUS[lang]
            with self.subTest(page=name):
                menu = menu_of(shown)
                self.assertEqual(menu["label"], label)
                home = home_link(lang, prefix)
                news, blog_hub = prefix + an.PAGES[lang], prefix + blog.HUBS[lang]
                self.assertEqual(menu["bar"], [(f"{home}#{anchor}", "", text) for anchor, text in zip(BAR_ANCHORS, bar)]
                                 + [(news, "", bar[1]), (blog_hub, ' aria-current="page"', "Blog"), (prefix + blog.LIVE_PAGES[lang], "", "Live")])
                self.assertEqual(menu["panel"], [(f"{home}#{anchor}", "", text) for anchor, text in zip(PANEL_ANCHORS, panel)]
                                 + [(news, "", panel[1]), (blog_hub, ' aria-current="page"', "Blog"), (prefix + blog.LIVE_PAGES[lang], "", "Live")])
                visit = f"{blog.VISIT}?p=/{path}&amp;go=testflight"  # le chemin de la page, comme le compteur de visites
                self.assertEqual(menu["soon"], (visit, beta))
                self.assertEqual(menu["soonm"], (visit, beta))
                self.assertEqual(menu["theme_labels"], theme)  # le groupe, puis système, clair, sombre
                self.assertEqual(menu["theme"].count("data-theme-set="), 3)
                self.assertIn(" hidden>", menu["theme"])  # caché sans JavaScript : le script de l'accueil le montre
                equivalents = [blog.HUBS[other] if hub else f"../{blog.BLOG_DIRS[other]}/{name.rsplit('/', 1)[1]}" for other in an.LANGS]
                self.assertEqual(menu["langs"], equivalents)  # le menu de langue mène toujours à la page équivalente du Blog
                self.assertEqual(menu["langsm"], equivalents)
                self.assertEqual(shown.count('aria-current="page"'), 5)  # Blog (barre, panneau), la langue (menu, panneau) et celle du pied de page
                ids = re.findall(r'\sid="([^"]*)"', shown)
                self.assertEqual(len(ids), len(set(ids)), ids)  # aucun identifiant en double (drapeau anglais du panneau compris)
                self.assertEqual(shown.count('<details class="menu">'), 1)
                self.assertEqual(shown.count("<header>"), 1)
                self.assertNotIn("esportly.fr", shown)
                self.assertNotIn("protojo", shown.lower().replace("protojo digital", ""))

    def test_script_et_csp(self):
        """Le script de l'accueil (thème et menu) est ajouté une fois, sur sa ligne avant </body> ; la CSP gagne son empreinte à la fin
        de script-src et rien d'autre : aucun domaine de plus (youtube-nocookie.com reste réservé aux pages à top plays)."""
        self.assertEqual(blog.MENU_HASH, base64.b64encode(hashlib.sha256(blog.MENU_JS.encode("utf-8")).digest()).decode())
        self.assertEqual(blog.MENU_HASH, HOME_SCRIPT_HASH)
        # « fetch » est admis depuis la recherche d'équipe : elle demande un seul fichier du site (equipes/index-pages.json),
        # jamais une adresse extérieure — d'où « http » toujours interdit. Les suggestions se posent avec createElement, pas
        # avec innerHTML : un nom d'équipe ne peut pas injecter de balise.
        for forbidden in ("http", "XMLHttpRequest", "innerHTML", "eval", "document.cookie", "</"):
            self.assertNotIn(forbidden, blog.MENU_JS)
        self.assertEqual(blog.MENU_JS.count("fetch("), 1)
        meta = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">')
        template = meta.search(CSP).group(1)
        for name, shown in self.pages().items():
            with self.subTest(page=name):
                self.assertEqual(shown.count(f"<script>{blog.MENU_JS}</script>"), 1)
                self.assertRegex(shown, r"\r\n<script>" + re.escape(blog.MENU_JS) + r"</script>\r\n(<script>[^\r\n]*</script>\r\n)?</body>")
                policy = meta.search(shown).group(1)
                videos = name.endswith("/valorant.html")
                expected = template.replace("script-src 'sha256-THEME='", "script-src 'sha256-THEME=' " + MENU_TOKEN
                                            + (f" 'sha256-{blog.PLAYER_HASH}'" if videos else ""))
                if videos:
                    expected = expected.replace("object-src 'none'", f"{FRAME_SRC}; object-src 'none'")
                self.assertEqual(policy, expected)
                hosts = set(re.findall(r"https://([^\s;'/]+)", policy))
                self.assertEqual(hosts, {"lmavqchwevcvvneblqld.supabase.co"} | ({"www.youtube-nocookie.com"} if videos else set()))
                scripts = re.findall(r"<script>(.*?)</script>", shown, re.S)
                hashes = re.findall(r"'sha256-([^']*)'", policy)
                for script in scripts[1:]:  # le premier est celui du modèle (empreinte factice THEME dans ce site)
                    self.assertIn(base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode(), hashes)

    def test_sans_script_src_ni_en_tete(self):
        """Sans script-src, on n'invente pas la directive ; sans en-tête (marque et menu de langue), on ne devine pas où mettre le menu."""
        page = fiche("valorant")
        main_html = blog.render_guide_main(page, "fr", NAMES, HOME, [], [], [])
        for broken, word in ((game_page("fr", "valorant").replace("script-src 'sha256-THEME='; ", ""), "script-src"),
                             (re.sub(r"<header>.*?</header>", "", game_page("fr", "valorant")), "en-tête")):
            with self.subTest(word=word), self.assertRaises(blog.BlogError) as caught:
                blog.render_guide_page("fr", broken, page, main_html, "", HOME_PAGES["fr"])
            self.assertIn(word, caught.exception.problems[0])

    def test_toutes_les_classes_du_menu_ont_une_regle(self):
        shown = self.pages()["fr/blog/valorant.html"]
        header = re.search(r"<header>.*?</header>", shown, re.S).group(0)
        used = {name for _, attrs in Reader(header).tags for name in attrs.get("class", "").split()}
        selectors = re.sub(r"\{[^{}]*\}", "", re.sub(r"\{[^{}]*\}", "", blog.BLOG_STYLE))
        defined = set(re.findall(r"\.([A-Za-z][\w-]*)", selectors))
        self.assertEqual(used - defined - TEMPLATE_HEADER_CLASSES, set())
        for cls in ("soon", "menu", "panel", "soonm", "langsm"):
            self.assertIn(cls, used & defined)
        self.assertIn("theme", defined)  # le sélecteur de thème n'est plus dans l'en-tête : il flotte en bas à droite
        for line in ("@media (max-width:860px){header nav{display:none!important}.menu{display:block}}",
                     "[hidden]{display:none!important}"):
            self.assertIn(line, blog.BLOG_STYLE.split("\n"))

    def test_pied_de_page_complet_sur_chaque_page(self):
        """Chaque page du Blog a le pied de page de l'accueil de sa langue, avec News et Blog ; ses adresses se lisent depuis la page,
        ses drapeaux mènent à la page équivalente et son compteur de visites compte la page."""
        for name, shown in self.pages().items():
            lang = next(lang for lang in an.LANGS if name in (blog.HUBS[lang], f"{blog.BLOG_DIRS[lang]}/valorant.html",
                                                              f"{blog.BLOG_DIRS[lang]}/comprendre-le-bo5.html"))
            hub = name == blog.HUBS[lang]
            prefix, path = site_chrome.prefix_for(name), name[:-5]  # « ../ » par dossier : « ../../ » pour fr/blog/valorant.html
            with self.subTest(page=name):
                self.assertEqual(shown.count("<footer>"), 1)
                footer = re.search(r"<footer>.*?</footer>", shown, re.S).group(0)
                self.assertIn(f'<li><a href="{prefix}{an.PAGES[lang]}">News</a></li><li><a href="{prefix}{blog.HUBS[lang]}">Blog</a></li>', footer)
                self.assertIn(f'<a href="{home_link(lang, prefix)}#jeux">Jeux</a>', footer)  # l'ancre mène à l'accueil
                self.assertIn(f'<li><a href="{prefix}whats-new.html">Nouveautés</a></li>', footer)
                self.assertIn(f'<a class="brand" href="{home_link(lang, prefix)}"><img src="{prefix}embleme.svg"', footer)
                self.assertIn('<a href="mailto:contact@example.org">', footer)  # adresses absolues et mailto: inchangées
                self.assertIn('<a href="https://example.org">', footer)
                self.assertIn(f"{blog.VISIT}?p=/{path}&amp;go=testflight", footer)
                equivalents = [blog.HUBS[other] if hub else f"../{blog.BLOG_DIRS[other]}/{name.rsplit('/', 1)[1]}" for other in an.LANGS]
                flags = re.findall(r'<li class="fl"><a href="([^"]*)" hreflang="([^"]*)" lang="[^"]*"( aria-current="page")?>', footer)
                self.assertEqual([href for href, _, _ in flags], equivalents)
                self.assertEqual([code for _, code, current in flags if current], [lang])
                self.assertNotIn("Mentions</a>", shown)  # le pied de page léger du modèle a disparu
                self.assertIn(".fgrid{display:grid", shown)
                self.assertEqual(shown.count(".fgrid{display:grid"), 1)

    def test_sans_pied_de_page(self):
        """Un modèle sans <footer>, ou un accueil sans <footer> : on ne devine pas, l'erreur nomme le fichier en cause."""
        page = fiche("valorant")
        main_html = blog.render_guide_main(page, "fr", NAMES, HOME, [], [], [])
        with self.assertRaises(blog.BlogError) as caught:
            blog.render_guide_page("fr", re.sub(r"<footer>.*?</footer>", "", game_page("fr", "valorant")), page, main_html, "", HOME_PAGES["fr"])
        self.assertIn("pied de page", caught.exception.problems[0])
        with self.assertRaises(blog.BlogError) as caught:
            blog.render_guide_page("fr", game_page("fr", "valorant"), page, main_html, "", "<html></html>")
        self.assertIn("fr.html : pied de page", caught.exception.problems[0])
        self.publish(fiche("valorant"))
        self.write("fr.html", "<html></html>")
        before = self.snapshot()
        problems = self.failure()
        self.assertTrue(any("fr.html : pied de page" in problem for problem in problems), problems)
        self.assertEqual(self.snapshot(), before)  # rien n'est écrit

    @unittest.skipUnless((REAL / "blog.html").is_file(), "pages du Blog absentes")
    def test_selecteur_de_theme_flottant(self):
        """Dans l'arbre de travail, les accueils, les pages News et les pages du Blog ont un seul sélecteur de thème, hors de l'en-tête,
        juste après le pied de page, et leur style le fait flotter en bas à droite, peu visible."""
        for lang in an.LANGS:
            names = [an.HOMES[lang], an.PAGES[lang], blog.HUBS[lang]] + [path.relative_to(REAL).as_posix()
                                                                          for path in sorted((REAL / blog.BLOG_DIRS[lang]).glob("*.html"))]
            for name in names:
                with self.subTest(page=name):
                    page = (REAL / name).read_text(encoding="utf-8")
                    self.assertEqual(page.count('class="theme"'), 1)
                    self.assertNotIn('class="theme"', re.search(r"<header>.*?</header>", page, re.S).group(0))
                    self.assertRegex(page, r'</footer><div class="theme" id="theme" role="group"')
                    self.assertIn(".theme{position:fixed;right:12px;bottom:12px;", page)
                    self.assertNotIn("{.theme{display:none}}", page)

    @unittest.skipUnless((REAL / "fr.html").is_file(), "accueils absents")
    def test_pied_de_page_identique_aux_accueils(self):
        """Les règles du pied de page sont celles des accueils (sauf FOOTER_STYLE_OWN) ; les textes du pied de page d'un accueil du Blog
        sont ceux du pied de page de l'accueil de la langue, ses adresses seules changent."""
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                text = (REAL / an.HOMES[lang]).read_text(encoding="utf-8")
                home_css = "".join(re.findall(r"<style>(.*?)</style>", text, re.S))
                for line in site_chrome.FOOTER_STYLE:
                    if line not in site_chrome.FOOTER_STYLE_OWN:
                        self.assertIn(line, home_css, line)
                if not (REAL / blog.HUBS[lang]).is_file():
                    continue
                words = lambda page: re.sub(r"<[^>]*>", "|", re.search(r"<footer>.*?</footer>", page, re.S).group(0))
                self.assertEqual(words((REAL / blog.HUBS[lang]).read_text(encoding="utf-8")), words(text))

    @unittest.skipUnless((REAL / "blog.html").is_file(), "pages du Blog absentes")
    def test_news_et_blog_dans_les_menus_et_les_pieds_de_page(self):
        """Dans l'arbre de travail, les accueils, les pages News et toutes les pages du Blog ont News et Blog dans la barre du haut, le
        menu mobile et le pied de page, avec les adresses de la langue vues de la page."""
        for lang in an.LANGS:
            names = [an.HOMES[lang], an.PAGES[lang], blog.HUBS[lang]] + [path.relative_to(REAL).as_posix()
                                                                          for path in sorted((REAL / blog.BLOG_DIRS[lang]).glob("*.html"))]
            for name in names:
                with self.subTest(page=name):
                    page = (REAL / name).read_text(encoding="utf-8")
                    prefix = site_chrome.prefix_for(name)  # « ../ » par dossier
                    wanted = {f'<a href="{prefix}{an.PAGES[lang]}"', f'<a href="{prefix}{blog.HUBS[lang]}"'}
                    header = re.search(r"<header>.*?</header>", page, re.S).group(0)
                    parts = {"barre": re.search(r"<nav aria-label=[^>]*>.*?</nav>", header, re.S).group(0),
                             # le menu burger contient le panneau des jeux (un <details> dans un <details>) : on va jusqu'au dernier
                             "menu mobile": re.search(r'<details class="menu">.*</details>', header, re.S).group(0),
                             "pied de page": re.search(r"<footer>.*?</footer>", page, re.S).group(0)}
                    for where, part in parts.items():
                        for link in wanted:
                            self.assertIn(link, part, f"{where} : {link}")
                        self.assertIn("Blog</a>", part, where)

    @unittest.skipUnless((REAL / "fr.html").is_file(), "accueils absents")
    def test_menu_identique_aux_accueils(self):
        """Les libellés, le sélecteur de thème, les icônes du burger et le script sont ceux des accueils, à l'octet près ; seules
        les adresses changent (accueil + ancre, pages de la langue) et « Blog » s'ajoute à la barre."""
        home_css = "".join(re.findall(r"<style>(.*?)</style>", (REAL / "fr.html").read_text(encoding="utf-8"), re.S))
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                text = (REAL / an.HOMES[lang]).read_text(encoding="utf-8")
                home = menu_of(text)
                label, bar, panel, beta, theme = MENUS[lang]
                self.assertEqual(home["label"], label)
                self.assertEqual([text for _, _, text in home["bar"]], bar)  # la barre des accueils finit par News, Blog puis Live, comme celle du Blog
                self.assertEqual([href for href, _, _ in home["bar"]],
                                 [f"#{anchor}" for anchor in BAR_ANCHORS] + [an.PAGES[lang], blog.HUBS[lang], blog.LIVE_PAGES[lang]])
                self.assertEqual([text for _, _, text in home["panel"]], panel)
                self.assertEqual([href for href, _, _ in home["panel"]],
                                 [f"#{anchor}" for anchor in PANEL_ANCHORS] + [an.PAGES[lang], blog.HUBS[lang], blog.LIVE_PAGES[lang]])
                shown = bascule_appstore.switch(beta) if json.loads((REAL / "version.json").read_text())["storeURL"] else beta  # après la sortie : « Télécharger l'app »
                self.assertEqual(home["soon"][1], shown)
                self.assertEqual(home["soonm"][1], shown)
                self.assertEqual(home["theme_labels"], theme)
                self.assertEqual(blog.MENU[lang]["beta"], beta)
                generated = (REAL / blog.HUBS[lang]).read_text(encoding="utf-8")
                ours = menu_of(generated)
                self.assertEqual(ours["theme"], home["theme"])  # boutons, icônes et libellés identiques
                self.assertEqual(ours["icons"], home["icons"])
                scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
                self.assertEqual(scripts[0], blog.MENU_JS)  # le script du thème et du menu de l'accueil, tel quel
                self.assertIn(f"'sha256-{blog.MENU_HASH}'", re.search(r"script-src[^;]*", text).group(0))
        for line in blog.MENU_STYLE:  # chaque règle du menu est une règle de l'accueil, sauf celles qui n'ont pas d'équivalent
            if line not in blog.MENU_STYLE_OWN:
                self.assertIn(line, home_css, line)

    @unittest.skipUnless((REAL / "blog.html").is_file(), "pages du Blog absentes")
    def test_liens_du_menu_vers_des_fichiers_existants(self):
        """Dans l'arbre de travail, chaque page du Blog a le menu, et chacun de ses liens relatifs mène à un fichier existant ;
        une ancre (#jeux…) existe dans l'accueil visé."""
        names = list(blog.HUBS.values()) + [path.relative_to(REAL).as_posix() for folder in blog.BLOG_DIRS.values()
                                             for path in sorted((REAL / folder).glob("*.html"))]
        self.assertGreater(len(names), 5)
        for name in names:
            with self.subTest(page=name):
                text = (REAL / name).read_text(encoding="utf-8")
                header = re.search(r"<header>.*?</header>", text, re.S).group(0)
                self.assertIn('<details class="menu">', header)
                self.assertIn('aria-current="page">Blog</a>', header)
                for href in re.findall(r'href="([^"]*)"', header):
                    if href.startswith("https://"):
                        self.assertTrue(href.startswith(blog.VISIT + "?p=/") or href == bascule_appstore.STORE, href)  # la bêta, puis l'App Store
                        continue
                    target, _, anchor = href.partition("#")
                    path = (REAL / name).parent / target
                    if target in ("", "./", "../") or target.endswith("/"):
                        path = path / "index.html"
                    self.assertTrue(path.resolve().is_file(), href)
                    if anchor:
                        self.assertIn(f'id="{anchor}"', path.read_text(encoding="utf-8"), href)


# --- Contrôle des sources : faux réseau -------------------------------------------------------------------------

TODAY = date(2026, 10, 27)
URL1, URL2, URL3 = source(1)["url"], source(2)["url"], source(3)["url"]
PAGE_ONE = ("<html><head><title>Valorant</title><style>.cache{content:'cinq joueurs'}</style>"
            "<script>var note = 'mots secrets';</script></head>"
            "<body><h1>Valorant</h1><p>It’s a free-to-play tactical shooter by Riot Games.</p></body></html>")
THIRTEEN = "one two three four five six seven eight nine ten eleven twelve thirteen"
PAGE_TWO = f"<html><body><p>Each team has five players &amp; one goal.</p><p>{THIRTEEN}</p></body></html>"
GOOD = [("It is a free tactical shooter", "s1", "It's a free-to-play tactical shooter"),  # apostrophe droite contre « ’ » de la page
        ("Teams have five players", "s2", "five players & one goal")]  # « &amp; » décodé


def table(*rows: tuple[str, str, str]) -> str:
    """Un tableau des affirmations : en-tête, séparateur, une ligne par (affirmation, source, extrait)."""
    return "\n".join(["| Affirmation | Source | Extrait |", "|---|---|---|", *(f"| {claim} | {ref} | {excerpt} |" for claim, ref, excerpt in rows)]) + "\n"


class Web:
    """Faux réseau : sert {adresse: (code, corps)} et note chaque adresse demandée ; une adresse inconnue ne répond pas."""

    def __init__(self, pages: dict[str, tuple[int, str]]):
        self.pages, self.calls = pages, []

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        return self.pages.get(url, (0, ""))


class Sources(SiteCase):
    """Le site factice, avec la fiche valorant (sources s1 et s2, s2 citée dans la première section seulement) et un faux réseau."""

    def setUp(self):
        super().setUp()
        self.publish(fiche("valorant", sources=[source(1), source(2)], sections=[section(("s1", "s2")), section(("s1",)), section(("s2",))]))
        self.web = Web({URL1: (200, PAGE_ONE), URL2: (200, PAGE_TWO)})

    def claims(self, page_id: str, *rows: tuple[str, str, str]) -> None:
        self.write(f"blog-src/claims/{page_id}.md", table(*rows))

    def check(self, web=None, today=TODAY) -> tuple[list[str], list[str]]:
        return blog.check_sources(self.root, web or self.web, today)

    def test_parse_claims(self):
        text = ("Notes avant le tableau.\n\n"
                "| Affirmation | Source | Extrait |\n|---|---|---|\n"
                "| It is free to play | s1 | free-to-play tactical shooter |\n"
                "|  Five players per team  |s2|five players|\n"
                "| Pro matches are streamed | s2 | manuel : page rendue par JavaScript |\n"
                "| Ligne trop courte | s1 |\n"
                "| Autre | s1 | manuel: sans espace |\n"
                "| a \\| b | s1 | x \\| y |\n")
        self.assertEqual(blog.parse_claims(text), [
            {"claim": "It is free to play", "source": "s1", "excerpt": "free-to-play tactical shooter", "manual": False, "note": ""},
            {"claim": "Five players per team", "source": "s2", "excerpt": "five players", "manual": False, "note": ""},
            {"claim": "Pro matches are streamed", "source": "s2", "excerpt": "", "manual": True, "note": "page rendue par JavaScript"},
            {"claim": "Autre", "source": "s1", "excerpt": "", "manual": True, "note": "sans espace"},
            {"claim": "a | b", "source": "s1", "excerpt": "x | y", "manual": False, "note": ""}])
        self.assertEqual(blog.parse_claims("﻿" + table(GOOD[0]))[0]["claim"], GOOD[0][0])  # un éditeur peut poser une marque d'ordre des octets
        self.assertEqual(blog.parse_claims(""), [])

    def test_normalisation(self):
        self.assertEqual(blog.normalize("It’s “FIVE” players — each"), blog.normalize("it's \"five\" players - each"))
        self.assertEqual(blog.normalize("It’s “FIVE” players — each"), "it's \"five\" players - each")
        self.assertEqual(blog.normalize("´a‘ – b”"), "'a' - b\"")
        self.assertEqual(blog.normalize("  A\t\n B  C  "), "a b c")

    def test_texte_visible(self):
        text = blog.visible_text("<html><head><style>.a{color:red}</style><script>var x = 'secret';</script></head>"
                                 "<body><p>Fish &amp; chips</p><p>Next</p><a>five</a>, <a>players</a><script>alert(1)</script></body></html>")
        for hidden in ("secret", "color", "alert"):
            self.assertNotIn(hidden, text)
        self.assertIn("Fish & chips", text)
        self.assertNotIn("&amp;", text)
        self.assertEqual(blog.normalize(text), "fish & chips next five, players")  # deux paragraphes ne se collent pas, un lien et sa virgule oui

    def test_fetch_page(self):
        def reply(body: bytes = b"ok", status: int = 200):
            response = mock.MagicMock(status=status)
            response.__enter__.return_value = response
            response.read.return_value = body
            return response

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = reply("café".encode())
            self.assertEqual(blog.fetch_page(URL1), (200, "café"))
            request = urlopen.call_args.args[0]
            self.assertEqual((request.full_url, request.get_header("User-agent")), (URL1, "esportly-site/1.0 (+https://esportly.eu)"))
            self.assertEqual(urlopen.call_args.kwargs, {"timeout": 20})
            urlopen.return_value.read.assert_called_once_with(2_000_000)
            urlopen.return_value = reply(b"a\xffb")
            self.assertEqual(blog.fetch_page(URL1), (200, "a�b"))  # octets invalides remplacés
            urlopen.side_effect = urllib.error.HTTPError(URL1, 404, "Not Found", {}, None)  # code d'erreur HTTP : rendu tel quel, sans seconde tentative
            urlopen.reset_mock()
            self.assertEqual(blog.fetch_page(URL1), (404, ""))
            self.assertEqual(urlopen.call_count, 1)
            urlopen.side_effect = [urllib.error.URLError("refusé"), TimeoutError()]  # panne réseau : une seconde tentative, puis (0, "")
            urlopen.reset_mock()
            self.assertEqual(blog.fetch_page(URL1), (0, ""))
            self.assertEqual(urlopen.call_count, 2)
            urlopen.side_effect = [http.client.IncompleteRead(b"a"), reply(b"ok")]  # la seconde tentative peut réussir
            urlopen.reset_mock()
            self.assertEqual(blog.fetch_page(URL1), (200, "ok"))
            self.assertEqual(urlopen.call_count, 2)

    def test_tout_est_conforme(self):
        self.claims("valorant", *GOOD)
        self.assertEqual(self.check(), ([], []))
        self.assertEqual(self.web.calls, [URL1, URL2])

    def test_adresse_en_erreur(self):
        self.claims("valorant", *GOOD)
        problems, manual = self.check(Web({URL1: (404, "Not found"), URL2: (0, "")}))
        self.assertEqual(manual, [])
        self.assertEqual(len(problems), 2, problems)  # une page injoignable ne compte pas en plus ses extraits comme absents
        self.assertTrue(all(problem.startswith("valorant : ") for problem in problems), problems)
        for fragment in ("source s1", "404", URL1):
            self.assertIn(fragment, problems[0])
        for fragment in ("source s2", "ne répond pas", URL2):
            self.assertIn(fragment, problems[1])
        problems, _ = self.check(Web({URL1: (200, PAGE_ONE), URL2: (500, "")}))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("500", problems[0])

    def test_extrait_absent_ou_trop_long(self):
        self.claims("valorant", *GOOD,
                    ("Twelve words fit", "s2", "one two three four five six seven eight nine ten eleven twelve"),
                    ("Absent", "s1", "a sentence found nowhere"),
                    ("Thirteen words", "s2", THIRTEEN),  # présent dans la page, mais trop long : un seul problème
                    ("Empty", "s2", ""),
                    ("Ghost", "s9", "five players"))
        problems, manual = self.check()
        self.assertEqual(manual, [])
        self.assertEqual(len(problems), 4, problems)
        self.assertTrue(all(problem.startswith("valorant : ") for problem in problems), problems)
        for fragment, problem in zip(("a sentence found nowhere", "13 mots", "vide", "s9"), problems):
            self.assertIn(fragment, problem)
        self.assertIn("source s1", problems[0])
        self.assertIn("12 au plus", problems[1])

    def test_tableau_manquant_ou_source_inutile(self):
        self.publish(solo("bo5", sources=[source(1)]))  # un guide, qui partage l'adresse s1 de la fiche
        self.claims("valorant", *GOOD)
        problems, manual = self.check()  # pas de tableau pour le guide
        self.assertEqual((len(problems), manual), (1, []), problems)
        self.assertTrue(problems[0].startswith("bo5 : "), problems)
        self.assertIn("blog-src/claims/bo5.md", problems[0])
        self.assertEqual(self.web.calls, [URL1, URL2])  # le guide n'a rien téléchargé de plus : chaque adresse l'est une seule fois
        self.claims("bo5", GOOD[0])
        self.assertEqual(self.check(), ([], []))
        self.claims("valorant", GOOD[0])  # s2 est citée par la première section, sans aucune affirmation
        problems, _ = self.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("valorant : "), problems)
        self.assertIn("s2", problems[0])
        self.claims("valorant", GOOD[0], ("Manual", "s2", "manuel : pas de texte"))  # une ligne manuelle est une affirmation
        self.assertEqual(self.check()[0], [])
        (self.root / "blog-src" / "claims" / "valorant.md").write_bytes(b"\xff\xfe")  # tableau illisible
        problems, _ = self.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("illisible", problems[0])

    def test_lignes_manuelles(self):
        reason = "page rendue par JavaScript"
        manual_row = ("Pro matches are streamed", "s2", f"manuel : {reason}")
        self.claims("valorant", GOOD[0], manual_row)
        web = Web({URL1: (200, PAGE_ONE), URL2: (200, "<html><body></body></html>")})
        problems, manual = self.check(web)  # l'extrait n'est pas cherché dans la page
        self.assertEqual(problems, [])
        self.assertEqual(manual, [f"valorant : source s2 : {reason} (affirmation : Pro matches are streamed)"])
        self.assertIn(URL2, web.calls)  # mais l'adresse est téléchargée
        problems, manual = self.check(Web({URL1: (200, PAGE_ONE), URL2: (404, "")}))  # et doit répondre
        self.assertEqual((len(problems), len(manual)), (1, 1), problems)
        self.assertIn("404", problems[0])
        self.claims("valorant", GOOD[0], manual_row, ("Ghost", "s7", "manuel : ailleurs"))  # et sa source doit être déclarée
        problems, manual = self.check(web)
        self.assertEqual((len(problems), len(manual)), (1, 1), problems)
        self.assertIn("s7", problems[0])

    def test_seules_les_pages_visibles(self):
        self.publish(solo("futur", date="2026-10-28", updated="2026-10-28", sources=[source(1, url=URL3)]))
        self.claims("valorant", *GOOD)
        self.assertEqual(self.check(), ([], []))
        self.assertEqual(self.web.calls, [URL1, URL2])  # ni tableau demandé, ni adresse téléchargée pour la page du lendemain
        problems, _ = self.check(today=date(2026, 10, 28))
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(all(problem.startswith("futur : ") for problem in problems), problems)

    def test_jour_par_defaut_et_donnees(self):
        self.publish(fiche("valorant", date="2000-01-01", updated="2000-01-01", sources=[source(1)], sections=[section() for _ in range(3)]))
        self.publish(solo("lointain", date="2999-01-01", updated="2999-01-01", sources=[source(1, url=URL3)]))
        self.claims("valorant", GOOD[0])
        self.assertEqual(blog.check_sources(self.root, self.web), ([], []))  # sans `today` : le jour à Paris
        self.assertEqual(self.web.calls, [URL1])
        with tempfile.TemporaryDirectory() as tmp:  # sans blog-src : rien à contrôler, rien de téléchargé
            self.assertEqual(blog.check_sources(Path(tmp), self.web, TODAY), ([], []))
        self.assertEqual(self.web.calls, [URL1])
        self.publish(solo("mauvaise", kind="article"))  # des données invalides arrêtent le contrôle
        with self.assertRaises(blog.BlogError):
            self.check()

    def test_option_sources(self):
        manual_row = ("Pro matches are streamed", "s2", "manuel : page rendue par JavaScript")
        self.claims("valorant", *GOOD, manual_row)
        before = self.snapshot()
        code, out, err = self.run_main("--sources", fetch=self.web)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, "Vérification manuelle :\n  - valorant : source s2 : page rendue par JavaScript (affirmation : Pro matches are streamed)\n"
                              "Sources : 1 page(s) vérifiée(s).\n")
        self.claims("valorant", *GOOD, ("Absent", "s1", "a sentence found nowhere"), manual_row)
        code, out, err = self.run_main("--sources", fetch=self.web)
        self.assertEqual(code, 1)
        self.assertEqual(err, 'Refus : 1 problème(s)\n  - valorant : source s1 : extrait introuvable dans la page : « a sentence found nowhere »\n')
        self.assertTrue(out.startswith("Vérification manuelle :\n  - valorant : source s2"), out)
        self.assertNotIn("vérifiée", out)
        self.assertEqual(self.run_main("--sources", fetch=Web({}))[0], 1)  # rien ne répond
        self.assertEqual(self.snapshot(), before | {"blog-src/claims/valorant.md": table(*GOOD, ("Absent", "s1", "a sentence found nowhere"), manual_row).encode()})
        with mock.patch.object(blog, "fetch_page", self.web):  # sans `fetch` : le vrai téléchargement, ici remplacé
            self.claims("valorant", *GOOD)
            self.assertEqual(self.run_main("--sources"), (0, "Sources : 1 page(s) vérifiée(s).\n", ""))
        self.publish(solo("mauvaise", kind="article"))  # des données invalides : le refus habituel
        code, out, err = self.run_main("--sources", fetch=self.web)
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("Refus : 1 problème(s)\n  - mauvaise.json : kind : « article » invalide"), err)

    def test_option_sources_sans_blog_src(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(an, "paris", side_effect=AssertionError("fuseau demandé")):
            web = Web({})
            self.assertEqual(self.run_main("--sources", root=Path(tmp), fetch=web, now=None), (0, "Sources : 0 page(s) vérifiée(s).\n", ""))
            self.assertEqual(web.calls, [])


if __name__ == "__main__":
    unittest.main()
