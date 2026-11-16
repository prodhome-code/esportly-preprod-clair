"""Tests des pages de compétitions : l'index, une page par compétition, les liens, le sitemap.

matchs.py est un script (il fait tout son travail à l'import) : ces tests regardent ce qu'il a écrit dans l'arbre de travail.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import actualites as an
import site_chrome as sc

REAL = Path(__file__).resolve().parents[2]
COMP_DIRS = {"en": "competitions", "fr": "fr/competitions", "es": "es/competiciones", "de": "de/wettbewerbe", "pt-BR": "pt/competicoes"}
INDEX = {code: f"{folder}.html" for code, folder in COMP_DIRS.items()}
# Compétitions au nom d'un site de paris : le site ne leur fait jamais de page (règle « aucun pari »).
BETTING = re.compile(r"1win|stake|thunderpick|\bpari\b|parimatch|betboom|gg\.?bet|betway|bet365|rollbit|csgoempire|bc\.game", re.I)


def slugs(lang: str = "fr") -> list[str]:
    folder = REAL / COMP_DIRS[lang]
    return sorted(path.stem for path in folder.glob("*.html")) if folder.is_dir() else []


@unittest.skipUnless((REAL / "fr/competitions.html").is_file(), "pages de compétitions absentes")
class Index(unittest.TestCase):
    def test_un_index_par_langue(self):
        for code, name in INDEX.items():
            with self.subTest(lang=code):
                self.assertTrue((REAL / name).is_file(), name)

    def test_l_index_mene_a_chaque_competition(self):
        page = (REAL / INDEX["fr"]).read_text(encoding="utf-8")
        main = re.search(r"<main.*?</main>", page, re.S).group(0)
        linked = set(re.findall(r'href="competitions/([a-z0-9-]+)\.html"', main))
        self.assertEqual(linked, set(slugs()), "l'index et les pages de compétitions ne disent pas la même chose")
        self.assertTrue(linked, "aucune compétition dans l'index")

    def test_l_index_groupe_par_jeu(self):
        main = re.search(r"<main.*?</main>", (REAL / INDEX["fr"]).read_text(encoding="utf-8"), re.S).group(0)
        self.assertIn('<h2 class="jour">', main)
        self.assertRegex(main, r"<small>\d+ matchs suivis</small>")


@unittest.skipUnless((REAL / "fr/competitions.html").is_file(), "pages de compétitions absentes")
class Pages(unittest.TestCase):
    def test_chaque_competition_existe_dans_les_5_langues(self):
        reference = slugs()
        self.assertTrue(reference)
        for code in COMP_DIRS:
            with self.subTest(lang=code):
                self.assertEqual(slugs(code), reference)

    def test_le_contenu_d_une_page(self):
        for slug in slugs():
            with self.subTest(slug=slug):
                page = (REAL / COMP_DIRS["fr"] / f"{slug}.html").read_text(encoding="utf-8")
                main = re.search(r"<main.*?</main>", page, re.S).group(0)
                self.assertIn('<h2 class="jour">Prochains matchs</h2>', main)
                self.assertIn('<h2 class="jour" id="resultats">', main)
                self.assertIn("<h1>", main)

    def test_les_liens_vers_le_jeu_et_l_index(self):
        for slug in slugs():
            with self.subTest(slug=slug):
                page = (REAL / COMP_DIRS["fr"] / f"{slug}.html").read_text(encoding="utf-8")
                main = re.search(r"<main.*?</main>", page, re.S).group(0)
                self.assertIn('<a href="../../fr/competitions.html">Toutes les compétitions</a>', main)
                self.assertRegex(main, r'<a href="\.\./\.\./fr/jeux/[a-z0-9-]+\.html">')

    def test_pas_de_calendrier_a_s_abonner(self):
        """Une compétition découverte dans les matchs n'a pas d'adresse .ics : on ne propose pas un abonnement qui échouerait."""
        page = (REAL / COMP_DIRS["fr"] / f"{slugs()[0]}.html").read_text(encoding="utf-8")
        main = re.search(r"<main.*?</main>", page, re.S).group(0)
        self.assertNotIn("webcal://", main)

    def test_aucune_competition_de_paris(self):
        for slug in slugs():
            with self.subTest(slug=slug):
                self.assertIsNone(BETTING.search(slug), f"{slug} : nom d'un site de paris")

    def test_les_scores_restent_floutes(self):
        avec = [slug for slug in slugs() if "<li><details>" in (REAL / COMP_DIRS["fr"] / f"{slug}.html").read_text(encoding="utf-8")]
        self.assertTrue(avec, "aucune compétition n'a de résultat")
        for slug in avec:
            with self.subTest(slug=slug):
                page = (REAL / COMP_DIRS["fr"] / f"{slug}.html").read_text(encoding="utf-8")
                self.assertIn('class="score" style="filter:blur(', page)

    def test_les_trois_grands_evenements_gardent_leur_page(self):
        """Worlds, VCT Champions et ESL Pro League ont leur page à la racine : aucun doublon dans le dossier des compétitions."""
        for slug in ("worlds-2026", "vct-champions-2026", "esl-pro-league"):
            with self.subTest(slug=slug):
                self.assertTrue((REAL / f"fr/{slug}.html").is_file())
                self.assertNotIn(slug, slugs())


@unittest.skipUnless((REAL / "fr/competitions.html").is_file(), "pages de compétitions absentes")
class LiensDuSite(unittest.TestCase):
    def test_les_competitions_des_pages_de_jeux_sont_cliquables(self):
        """« Compétitions suivies » était du texte mort ; chaque entrée mène maintenant à sa page."""
        page = (REAL / "fr/jeux/counter-strike-2.html").read_text(encoding="utf-8")
        found = re.search(r'<ul class="comps">(.*?)</ul>', page, re.S)
        self.assertIsNotNone(found)
        self.assertTrue(re.findall(r'href="\.\./\.\./fr/competitions/[a-z0-9-]+\.html"', found.group(1)))

    def test_le_menu_mene_a_l_index(self):
        page = (REAL / "fr/blog.html").read_text(encoding="utf-8")
        header = re.search(r"<header>.*?</header>", page, re.S).group(0)
        self.assertIn("fr/competitions.html", header)

    def test_sitemap(self):
        sitemap = (REAL / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<!-- competitions -->", sitemap)
        for code in COMP_DIRS:
            self.assertIn(f"<loc>{an.public_url(INDEX[code])}</loc>", sitemap)
        for slug in slugs():
            with self.subTest(slug=slug):
                self.assertIn("<loc>" + an.public_url(COMP_DIRS["fr"] + "/" + slug + ".html") + "</loc>", sitemap)

    def test_les_jeux_du_site_sont_connus(self):
        """Une compétition est rangée sous un jeu du site : l'index ne peut pas inventer un jeu."""
        main = re.search(r"<main.*?</main>", (REAL / INDEX["fr"]).read_text(encoding="utf-8"), re.S).group(0)
        for game in re.findall(r'data-game="([a-z0-9-]+)"', main):
            self.assertIn(game, sc.GAMES)


if __name__ == "__main__":
    unittest.main()
