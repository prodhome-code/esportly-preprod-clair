"""Tests de anglais_par_defaut.py (jetables avec lui, à supprimer après la fusion).

    PYTHONDONTWRITEBYTECODE=1 py -3.13 -m unittest discover -s .github/scripts -p "test_anglais_par_defaut.py" -v
"""
import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

import anglais_par_defaut as ap

HREFLANGS = {"fr": ap.SITE + "fr.html", "en": ap.SITE, "es": ap.SITE + "es.html", "de": ap.SITE + "de.html",
             "pt-BR": ap.SITE + "pt.html", "x-default": ap.SITE}


def home(lang: str, canonical: str) -> str:
    links = "".join(f'<link rel="alternate" hreflang="{code}" href="{href}">\n' for code, href in HREFLANGS.items())
    return f'<!doctype html>\n<html lang="{lang}">\n<head>\n<link rel="canonical" href="{canonical}">\n{links}<script type="application/ld+json">{{"url": "{canonical}"}}</script>\n</head>\n<body></body>\n</html>\n'


def sitemap(*paths: str, lastmod: str = "2026-10-13") -> str:
    entries = "".join(f"  <url>\r\n    <loc>{ap.SITE}{p}</loc>\r\n    <lastmod>{lastmod}</lastmod>\r\n  </url>\r\n" for p in paths)
    return '<?xml version="1.0" encoding="UTF-8"?>\r\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\r\n' + entries + "</urlset>\r\n"


def tree() -> dict[str, str]:
    """Les 5 accueils et le sitemap tels qu'ils doivent être après la migration (§5 de la spec)."""
    return {"index.html": home("en", ap.SITE), "fr.html": home("fr", ap.SITE + "fr.html"),
            "es.html": home("es", ap.SITE + "es.html"), "de.html": home("de", ap.SITE + "de.html"),
            "pt.html": home("pt-BR", ap.SITE + "pt.html"),
            "sitemap.xml": sitemap("fr.html", "", "es.html", "de.html", "pt.html", "equipes/x.html")}


class EchangeDesLiens(unittest.TestCase):
    def test_cibles_relatives(self):
        for avant, apres, depth in [("./", "fr.html", 0), ("en.html", "./", 0), ("../", "../fr.html", 1),
                                    ("../en.html#jeux", "../#jeux", 1), ("/", "/fr.html", 0), ("/en.html", "/", 1)]:
            self.assertEqual(ap.swap_links(f'<a href="{avant}">', depth), (f'<a href="{apres}">', 1), avant)

    def test_cibles_absolues(self):
        self.assertEqual(ap.swap_links('<link rel="canonical" href="https://esportly.eu/">', 0)[0],
                         '<link rel="canonical" href="https://esportly.eu/fr.html">')
        self.assertEqual(ap.swap_links('"item": "https://esportly.eu/en.html"', 1)[0], '"item": "https://esportly.eu/"')
        self.assertEqual(ap.swap_links("<loc>https://esportly.eu/en.html</loc>", 0)[0], "<loc>https://esportly.eu/</loc>")

    def test_substitution_simultanee(self):
        self.assertEqual(ap.swap_links('<a href="./">a</a><a href="en.html">b</a>', 0),
                         ('<a href="fr.html">a</a><a href="./">b</a>', 2))

    def test_faux_amis_intacts(self):
        for t in ['href="neuigkeiten.html"', 'href="../equipes/x.html"', 'href="https://esportly.eu/equipes/x.html"',
                  'href="#jeux"', "Voir https://esportly.eu/ pour plus"]:
            self.assertEqual(ap.swap_links(t, 1), (t, 0), t)

    def test_octets_conserves(self):
        t = '<p>Cette page n’existe pas · →</p>\r\n<a href="../">x</a>'
        self.assertEqual(ap.swap_links(t, 1)[0], t.replace('href="../"', 'href="../fr.html"'))
        self.assertEqual(ap.swap_links("é\r\nsans retour final", 0), ("é\r\nsans retour final", 0))

    def test_inverse_redonne_l_original(self):
        for depth, t in [(0, '<a href="./">a</a><a href="en.html#x">b</a><a href="/">c</a>https://esportly.eu/'),
                         (1, '<a href="../">a</a><a href="../en.html">b</a>')]:
            self.assertEqual(ap.unswap_links(ap.swap_links(t, depth)[0], depth), t)

    def test_formes_implicites_inconnues(self):
        for t, depth in [('<a href=".././">', 1), ('<a href=".././#jeux">', 1), ('<a href="./en.html">', 0), ('<a href="..">', 1),
                         ('<a href=".">', 0), ('<a href="./?x=1">', 0)]:
            self.assertTrue(ap.unknown_variants(t, depth), t)
        self.assertEqual(ap.unknown_variants('<a href=".">x</a>', 1), [])

    def test_lien_vers_fr_html_inconnu(self):
        for t, depth in [('<a href="fr.html">', 0), ('<a href="../fr.html">', 1), ('<a href="/fr.html">', 0),
                         ('<link href="https://esportly.eu/fr.html">', 0)]:
            self.assertTrue(ap.unknown_variants(t, depth), t)

    def test_variantes_inconnues(self):
        for t, depth in [('href="index.html"', 0), ("href='./'", 0), ('href="/./"', 0), ('href="../../"', 1),
                         ('<a href="../">', 0), ('<a href="./">', 1), ('<a href="en.html">', 1),
                         ('<link href="https://esportly.eu/?x=1">', 0), ("Voir https://esportly.eu/ pour plus", 0)]:
            self.assertTrue(ap.unknown_variants(t, depth), t)
        self.assertEqual(ap.unknown_variants('<a href="./">x</a><link href="https://esportly.eu/">', 0), [])
        self.assertEqual(ap.unknown_variants('<a href="../equipes/x.html"><link href="https://esportly.eu/equipes/x.html">', 1), [])


class GardeFous(unittest.TestCase):
    FR, EN = '<html lang="fr">', '<html lang="en">'

    def run_check(self, files: dict[str, str]) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                (Path(tmp) / name).write_text(text, encoding="utf-8", newline="")
            ap.check_start_state(Path(tmp))

    def test_etat_de_depart_ok(self):
        self.run_check({"index.html": self.FR, "en.html": self.EN})

    def test_refus_fr_html_existe(self):
        with self.assertRaises(ap.Refus):
            self.run_check({"index.html": self.FR, "en.html": self.EN, "fr.html": self.FR})

    def test_refus_index_deja_en_anglais(self):
        with self.assertRaises(ap.Refus):
            self.run_check({"index.html": self.EN, "en.html": self.EN})

    def test_refus_fichier_manquant(self):
        with self.assertRaises(ap.Refus):
            self.run_check({"index.html": self.FR})


class RenvoiEtSitemap(unittest.TestCase):
    def test_renvoi(self):
        page = ap.renvoi_page()
        for expected in ['<html lang="en">', '<link rel="canonical" href="https://esportly.eu/">',
                         '<meta http-equiv="refresh" content="0; url=./">', 'href="./"']:
            self.assertIn(expected, page)
        for forbidden in ["noindex", "hreflang"]:
            self.assertNotIn(forbidden, page)

    def test_url_json_ld_propre_adresse(self):
        self.assertEqual(ap.own_url('{"url": "https://esportly.eu/fr.html", "x": "https://protojo.fr"}', ap.SITE),
                         '{"url": "https://esportly.eu/", "x": "https://protojo.fr"}')
        self.assertEqual(ap.own_url('{"url": "https://esportly.eu/"}', ap.SITE + "fr.html"), '{"url": "https://esportly.eu/fr.html"}')
        self.assertEqual(ap.own_url('{"url": "https://esportly.eu/es.html"}', ap.SITE), '{"url": "https://esportly.eu/es.html"}')

    def test_lastmod_des_accueils_seulement(self):
        before = sitemap("fr.html", "", "es.html", "de.html", "pt.html", "equipes/x.html")
        after = ap.set_homes_lastmod(before, "2026-10-27")
        self.assertEqual(after.count("2026-10-27"), 5)
        self.assertEqual(after.count("2026-10-13"), 1)
        self.assertEqual(after.count("\r\n"), before.count("\r\n"))
        self.assertNotIn("\n", after.replace("\r\n", ""))


class ControlesInternes(unittest.TestCase):
    def problems(self, changes: dict[str, str]) -> list[str]:
        files = tree()
        files.update(changes)
        return ap.check_postconditions(files)

    def test_controles_ok(self):
        self.assertEqual(ap.check_postconditions(tree()), [])

    def test_controle_canonical(self):
        found = self.problems({"fr.html": home("fr", ap.SITE)})
        self.assertTrue(any(p.startswith("canonical") for p in found), found)

    def test_controle_hreflang(self):
        incomplete = home("es", ap.SITE + "es.html").replace('<link rel="alternate" hreflang="en" href="https://esportly.eu/">\n', "")
        wrong_self = home("pt-BR", ap.SITE + "pt.html").replace('hreflang="pt-BR" href="https://esportly.eu/pt.html"',
                                                                  'hreflang="pt-BR" href="https://esportly.eu/pt.htm"')
        for name, page in (("es.html", incomplete), ("pt.html", wrong_self)):
            found = self.problems({name: page})
            self.assertTrue(any(p.startswith("hreflang") for p in found), name)

    def test_controle_sitemap(self):
        found = self.problems({"sitemap.xml": sitemap("fr.html", "", "en.html", "es.html", "de.html", "pt.html")})
        self.assertTrue(any(p.startswith("sitemap") for p in found), found)

    def test_controle_url(self):
        wrong = home("en", ap.SITE).replace('{"url": "https://esportly.eu/"}', '{"url": "https://esportly.eu/fr.html"}')
        found = self.problems({"index.html": wrong})
        self.assertTrue(any(p.startswith("url") for p in found), found)

    def test_controle_lang(self):
        found = self.problems({"index.html": home("fr", ap.SITE)})
        self.assertTrue(any(p.startswith("lang") for p in found), found)


OLD_HREFLANGS = {"fr": ap.SITE, "en": ap.SITE + "en.html", "es": ap.SITE + "es.html", "de": ap.SITE + "de.html",
                 "pt-BR": ap.SITE + "pt.html", "x-default": ap.SITE + "en.html"}


def old_home(lang: str, canonical: str, brand: str, url: str = "") -> str:
    """Un accueil avant la migration (fins de ligne CRLF, comme dans l'arbre de travail)."""
    links = "".join(f'<link rel="alternate" hreflang="{code}" href="{href}">\n' for code, href in OLD_HREFLANGS.items())
    page = (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<link rel="canonical" href="{canonical}">\n{links}<script type="application/ld+json">{{"url": "{url or canonical}"}}</script>\n</head>\n'
            f'<body><a class="brand" href="{brand}">eSportly</a><a href="./" hreflang="fr">F</a><a href="en.html" hreflang="en">E</a></body>\n</html>\n')
    return page.replace("\n", "\r\n")


def old_sitemap() -> str:
    entries = ""
    for path in ("", "en.html", "es.html", "de.html", "pt.html", "equipes/a.html"):
        entries += f"  <url>\r\n    <loc>{ap.SITE}{path}</loc>\r\n    <lastmod>2026-10-13</lastmod>\r\n"
        if path == "":
            entries += f'    <xhtml:link rel="alternate" hreflang="en" href="{ap.SITE}en.html"/>\r\n'
        entries += "  </url>\r\n"
    return '<?xml version="1.0" encoding="UTF-8"?>\r\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\r\n' + entries + "</urlset>\r\n"


class Migration(unittest.TestCase):
    TODAY = "2026-10-27"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.files = {"index.html": old_home("fr", ap.SITE, "./"), "en.html": old_home("en", ap.SITE + "en.html", "en.html", ap.SITE),
                      "es.html": old_home("es", ap.SITE + "es.html", "es.html"), "de.html": old_home("de", ap.SITE + "de.html", "de.html"),
                      "pt.html": old_home("pt-BR", ap.SITE + "pt.html", "pt.html"),
                      "equipes/a.html": '<html lang="fr"><a class="brand" href="../">x</a></html>\r\n',
                      "teams/a.html": '<html lang="en"><a class="brand" href="../en.html">x</a></html>\r\n',
                      "404.html": '<html lang="fr"><a href="/">x</a><a href="/./">y</a></html>\r\n',
                      "sitemap.xml": old_sitemap()}
        for name, text in self.files.items():
            self.write(name, text)

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def read(self, name: str) -> str:
        return (self.root / name).read_bytes().decode("utf-8")

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    @staticmethod
    def mask_url(text: str) -> str:
        """Le "url" JSON-LD d'un accueil est la seule valeur que l'échange inverse ne redonne pas (§6)."""
        return re.sub(r'("url": ")[^"]*(")', r"\1X\2", text)

    def test_essai_n_ecrit_rien(self):
        before = self.snapshot()
        self.assertEqual(ap.migrate(self.root, self.TODAY, trial=True), (8, 36))
        self.assertEqual(self.snapshot(), before)

    def test_migration_complete(self):
        self.assertEqual(ap.migrate(self.root, self.TODAY, trial=False), (8, 36))
        french, english = self.read("fr.html"), self.read("index.html")
        self.assertIn('<html lang="fr">', french)
        self.assertIn('<html lang="en">', english)
        self.assertIn('href="fr.html" hreflang="fr"', french)
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr.html">', french)
        self.assertIn('<link rel="canonical" href="https://esportly.eu/">', english)
        self.assertEqual(self.read("en.html"), ap.renvoi_page())
        self.assertIn('href="../fr.html"', self.read("equipes/a.html"))
        self.assertIn('href="../"', self.read("teams/a.html"))
        self.assertEqual(self.read("404.html"), self.files["404.html"])
        sitemap = self.read("sitemap.xml")
        self.assertEqual(sitemap.count(self.TODAY), 5)
        self.assertNotIn("en.html", sitemap)
        self.assertNotIn("\n", sitemap.replace("\r\n", ""))

    def test_inverse_redonne_l_original(self):
        ap.migrate(self.root, self.TODAY, trial=False)
        for new, old, depth in [("fr.html", "index.html", 0), ("index.html", "en.html", 0), ("es.html", "es.html", 0),
                                ("de.html", "de.html", 0), ("pt.html", "pt.html", 0),
                                ("equipes/a.html", "equipes/a.html", 1), ("teams/a.html", "teams/a.html", 1)]:
            self.assertEqual(self.mask_url(ap.unswap_links(self.read(new), depth)), self.mask_url(self.files[old]), new)

    def test_deuxieme_execution_refusee(self):
        ap.migrate(self.root, self.TODAY, trial=False)
        after = self.snapshot()
        with self.assertRaises(ap.Refus):
            ap.migrate(self.root, self.TODAY, trial=False)
        self.assertEqual(self.snapshot(), after)

    def test_rien_ecrit_si_variante_inconnue(self):
        self.write("equipes/b.html", '<a href="index.html">x</a>')
        before = self.snapshot()
        with self.assertRaises(ap.Refus) as refused:
            ap.migrate(self.root, self.TODAY, trial=False)
        self.assertIn("equipes/b.html", str(refused.exception))
        self.assertEqual(self.snapshot(), before)

    def test_url_json_ld_des_accueils(self):
        ap.migrate(self.root, self.TODAY, trial=False)
        self.assertIn('{"url": "https://esportly.eu/"}', self.read("index.html"))
        self.assertIn('{"url": "https://esportly.eu/fr.html"}', self.read("fr.html"))

    def test_refus_forme_implicite(self):
        self.write("equipes/c.html", '<a href=".././">x</a>')
        before = self.snapshot()
        with self.assertRaises(ap.Refus) as refused:
            ap.migrate(self.root, self.TODAY, trial=False)
        self.assertIn("equipes/c.html", str(refused.exception))
        self.assertEqual(self.snapshot(), before)

    def test_refus_arbre_a_moitie_migre(self):
        self.write("equipes/b.html", '<a href="../fr.html">x</a>')
        before = self.snapshot()
        with self.assertRaises(ap.Refus):
            ap.migrate(self.root, self.TODAY, trial=False)
        self.assertEqual(self.snapshot(), before)

    def test_main(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ap.main(["--essai"], self.root), 0)
            self.assertEqual(ap.main([], self.root), 0)
        self.assertIn("8 fichier(s) à changer, 36 lien(s) d'accueil échangé(s).", out.getvalue())
        self.assertIn("8 fichier(s) changé(s), 36 lien(s) d'accueil échangé(s).", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(ap.main([], self.root), 1)
        self.assertTrue(err.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
