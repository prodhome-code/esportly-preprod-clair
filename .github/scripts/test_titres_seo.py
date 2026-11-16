"""Tests de titres_seo.py et de site_chrome.seo : py -3.13 -m unittest discover -s .github/scripts -p "test_titres_seo.py"."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import site_chrome
import titres_seo

PAGE = ('<!doctype html>\r\n<html lang="fr">\r\n<head>\r\n<title>Suivre OG : alertes et score en direct – eSportly</title>\r\n'
        '<meta name="description" content="Toutes les équipes OG sur iPhone.">\r\n'
        '<meta property="og:title" content="Suivre OG : alertes et score en direct – eSportly">\r\n'
        '<meta property="og:description" content="Toutes les équipes OG sur iPhone.">\r\n'
        '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "WebPage", '
        '"name": "Suivre OG : alertes et score en direct – eSportly", "about": {"@type": "SportsOrganization", "name": "OG"}}</script>\r\n'
        '</head>\r\n<body><h1>Suis OG, sans rien rater</h1><p>Le titre d\'une FAQ : "name": "Gratuit ?"</p></body>\r\n</html>\r\n')
TEXTS = {"/equipes/og": {"title": "OG prochain match : alerte, score en direct, écran verrouillé",
                         "description": "OG sur iPhone : alerte avant chaque match, score en direct sur l'écran verrouillé."}}


class Seo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write_texts(self, texts) -> None:
        (self.root / "seo").mkdir(exist_ok=True)
        (self.root / site_chrome.SEO_FILE).write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")

    def test_sans_fichier(self):
        self.assertEqual(site_chrome.seo_texts(self.root), {})
        self.assertEqual(site_chrome.seo({}, "blog-fr/valorant.html", "Titre", "Desc."), ("Titre", "Desc."))

    def test_lecture_et_cles(self):
        self.write_texts(TEXTS)
        texts = site_chrome.seo_texts(self.root)
        self.assertEqual(texts, TEXTS)
        for path in ("equipes/og.html", "/equipes/og", "equipes/og"):
            self.assertEqual(site_chrome.seo(texts, path, "Titre", "Desc."), (TEXTS["/equipes/og"]["title"], TEXTS["/equipes/og"]["description"]))
        self.assertEqual(site_chrome.seo(texts, "teams/og.html", "Titre", "Desc."), ("Titre", "Desc."))

    def test_fichier_invalide(self):
        self.write_texts({"/x": {"title": "seul"}})
        with self.assertRaises(site_chrome.ChromeError) as caught:
            site_chrome.seo_texts(self.root)
        self.assertIn("seo/titres.json", caught.exception.problems[0])


class Script(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write_texts = Seo.write_texts.__get__(self)
        self.write_texts(TEXTS)
        (self.root / "equipes").mkdir()
        (self.root / "equipes" / "og.html").write_bytes(PAGE.encode("utf-8"))

    def page(self) -> str:
        return (self.root / "equipes" / "og.html").read_bytes().decode("utf-8")

    def test_retitle(self):
        page = titres_seo.retitle(PAGE, TEXTS["/equipes/og"]["title"], TEXTS["/equipes/og"]["description"])
        self.assertIn("<title>OG prochain match : alerte, score en direct, écran verrouillé</title>\r\n", page)
        self.assertIn('<meta name="description" content="OG sur iPhone : alerte avant chaque match, score en direct sur l&#x27;écran verrouillé.">', page)
        self.assertIn('<meta property="og:title" content="OG prochain match : alerte, score en direct, écran verrouillé">', page)
        self.assertIn('<meta property="og:description" content="OG sur iPhone : alerte avant chaque match, score en direct sur l&#x27;écran verrouillé.">', page)
        self.assertIn('"@type": "WebPage", "name": "OG prochain match : alerte, score en direct, écran verrouillé", "about"', page)
        self.assertIn("<h1>Suis OG, sans rien rater</h1>", page)  # le H1 et le reste ne bougent pas
        self.assertIn('"name": "Gratuit ?"', page)
        self.assertNotIn("eSportly</title>", page)
        self.assertEqual(page.count("\r\n"), PAGE.count("\r\n"))

    def test_guillemet_dans_le_title(self):
        page = titres_seo.retitle(PAGE, 'OG "Dream Team" : prochain match', "Desc.")
        self.assertIn("<title>OG &quot;Dream Team&quot; : prochain match</title>", page)
        self.assertIn('"@type": "WebPage", "name": "OG \\"Dream Team\\" : prochain match", "about"', page)

    def test_apply_puis_rejouable(self):
        self.assertEqual(titres_seo.apply(self.root), (["equipes/og.html"], []))
        self.assertIn("<title>OG prochain match : alerte, score en direct, écran verrouillé</title>", self.page())
        self.assertEqual(titres_seo.apply(self.root), ([], []))

    def test_check_et_introuvable(self):
        self.write_texts({**TEXTS, "/teams/og": {"title": "OG calendar", "description": "OG on iPhone."}})
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = titres_seo.main(["--check"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("à mettre à jour : equipes/og.html", out.getvalue())
        self.assertIn("introuvable : teams/og.html", err.getvalue())
        self.assertEqual(self.page(), PAGE)  # --check n'écrit rien
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(titres_seo.main([], self.root), 0)
        self.assertIn("1 page(s) mise(s) à jour, 1 introuvable(s)", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(titres_seo.main(["--check"], self.root), 0)


if __name__ == "__main__":
    unittest.main()
