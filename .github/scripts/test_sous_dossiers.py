"""Tests de sous_dossiers.py (passage des langues fr/es/de/pt sous leur sous-dossier) :
`py -3.13 -m unittest discover -s .github/scripts -p "test_*.py"` depuis la racine du site."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import sous_dossiers as sd

CRLF = "\r\n"


def write(root: Path, rel: str, text: str, eol: str = CRLF) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", eol).encode("utf-8"))


def fake_site(root: Path) -> None:
    """Un petit site dans la forme du vrai : accueils, pages racine, dossiers, widget, 404, sitemap, flux, analytics, titres."""
    write(root, "index.html", '<html lang="en"><a href="games/valorant.html">V</a><a href="fr.html">FR</a><a href="live.html">Live</a>\n')
    write(root, "fr.html", '<html lang="fr"><a href="jeux/valorant.html">V</a><a href="./">EN</a><a href="live-fr.html">Live</a>'
                           '<a href="confidentialite.html">C</a><link rel="canonical" href="https://esportly.eu/fr">\n')
    write(root, "live-fr.html", '<html lang="fr"><link rel="canonical" href="https://esportly.eu/live-fr">'
                                '<link rel="alternate" hreflang="en" href="https://esportly.eu/live">'
                                '<a href="fr.html#jeux">J</a><a href="./">EN</a><a href="jeux/valorant.html">V</a>'
                                '<style>@font-face{src:url(fonts/Rajdhani-Bold.woff2)}</style>'
                                '<a href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/live-fr&amp;go=testflight">B</a>\n')
    write(root, "live.html", '<html lang="en"><link rel="canonical" href="https://esportly.eu/live"><a href="live-fr.html">FR</a>\n')
    write(root, "worlds-2026.html", '<html lang="fr"><link rel="canonical" href="https://esportly.eu/worlds-2026">\n')
    write(root, "worlds-2026-en.html", '<html lang="en"><link rel="canonical" href="https://esportly.eu/worlds-2026-en">\n')
    write(root, "confidentialite.html", '<html lang="fr">\n')
    write(root, "jeux/valorant.html", '<html lang="fr"><a href="../games/valorant.html">EN</a><a href="../blog-fr/valorant.html">B</a>'
                                      '<a href="counter-strike-2.html">CS</a><img src="../logos-jeux/valorant.png">'
                                      '<link rel="canonical" href="https://esportly.eu/jeux/valorant">\n')
    write(root, "jeux/counter-strike-2.html", '<html lang="fr">\n')
    write(root, "games/valorant.html", '<html lang="en"><a href="../jeux/valorant.html">FR</a><a href=".././">home</a>\n')
    write(root, "blog-fr/valorant.html", '<html lang="fr"><script type="application/ld+json">{"item": "https://esportly.eu/blog-fr/valorant"}</script>\n')
    write(root, "equipes/t1.html", '<html lang="fr"><a href="../teams/t1.html">EN</a>\n')
    write(root, "equipes/t1.json", '{"organisation": "T1"}\n', "\n")
    write(root, "teams/t1.html", '<html lang="en"><a href="../equipes/t1.html">FR</a>\n')
    write(root, "widget/fr/t1.html", '<html lang="fr"><a href="https://esportly.eu/equipes/t1.html">T1</a>\n')
    write(root, "404.html", '<html lang="en"><a href="/mentions-legales.html">L</a><a href="/privacy.html">P</a>\n')
    write(root, "mentions-legales.html", '<html lang="fr">\n')
    write(root, "privacy.html", '<html lang="en">\n')
    write(root, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n  <url>\n    <loc>https://esportly.eu/live-fr</loc>\n'
                               '    <lastmod>2026-10-27</lastmod>\n    <xhtml:link rel="alternate" hreflang="en" href="https://esportly.eu/live"/>\n'
                               '  </url>\n  <url>\n    <loc>https://esportly.eu/live</loc>\n    <lastmod>2026-10-27</lastmod>\n  </url>\n</urlset>\n', "\n")
    write(root, "nouveautes.xml", '<rss><link>https://esportly.eu/nouveautes.html</link><atom:link href="https://esportly.eu/nouveautes.xml"/></rss>\n', "\n")
    write(root, "nouveautes.html", '<html lang="fr"><link rel="alternate" type="application/rss+xml" href="nouveautes.xml">\n')
    write(root, "analytics.js", "var T = { fr: { page: '/confidentialite.html' }, en: { page: '/privacy.html' } };\n", "\n")
    write(root, "seo/titres.json", json.dumps({"/news": {"title": "N", "description": "n"}, "/jeux/valorant": {"title": "V", "description": "v"},
                                               "/live-fr": {"title": "L", "description": "l"}}, indent=1, ensure_ascii=False) + "\n", "\n")
    write(root, "docs/notes.html", '<a href="jeux/valorant.html">ignoré</a>\n')


class Carte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fake_site(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tables(self):
        self.assertEqual(len(sd.ROOT_MOVES), 50)
        by_lang = {prefix: sum(1 for v in sd.ROOT_MOVES.values() if v.startswith(prefix)) for prefix in ("fr/", "es/", "de/", "pt/")}
        self.assertEqual(by_lang, {"fr/": 14, "es/": 12, "de/": 12, "pt/": 12})
        self.assertEqual(sd.ROOT_MOVES["blog-fr.html"], "fr/blog.html")
        self.assertEqual(sd.ROOT_MOVES["esl-pro-league.html"], "fr/esl-pro-league.html")
        # Décisions refusées par Johan le 1/11 : les pages anglaises gardent -en (B), les confirmations françaises restent à la racine (E)
        for name in ("worlds-2026-en.html", "vct-champions-2026-en.html", "esl-pro-league-en.html", "merci.html", "verifie.html",
                     "desinscrit.html", "inscription-erreur.html"):
            self.assertNotIn(name, sd.ROOT_MOVES)
        self.assertEqual(sd.DIR_MOVES, {"jeux": "fr/jeux", "equipes": "fr/equipes", "blog-fr": "fr/blog", "juegos": "es/juegos",
                                        "blog-es": "es/blog", "spiele": "de/spiele", "blog-de": "de/blog", "jogos": "pt/jogos", "blog-pt": "pt/blog"})
        self.assertEqual(sd.XML_MOVES, {"nouveautes.xml": "fr/nouveautes.xml", "novedades.xml": "es/novedades.xml",
                                        "neuigkeiten.xml": "de/neuigkeiten.xml", "novidades.xml": "pt/novidades.xml"})
        for name in ("fr.html", "es.html", "de.html", "pt.html", "index.html", "en.html", "404.html", "match.html", "tv-equipes.html",
                     "whats-new.xml", "news.html", "live.html", "worlds-2026-en.html", "merci.html"):
            self.assertNotIn(name, sd.ROOT_MOVES)
            self.assertNotIn(name, sd.XML_MOVES)
        self.assertEqual(len(set(sd.ROOT_MOVES.values())), len(sd.ROOT_MOVES))  # deux pages ne vont jamais au même endroit

    def test_carte_du_site(self):
        m = sd.build_map(self.root)
        self.assertEqual(m["jeux/valorant.html"], "fr/jeux/valorant.html")
        self.assertEqual(m["jeux/counter-strike-2.html"], "fr/jeux/counter-strike-2.html")
        self.assertEqual(m["blog-fr/valorant.html"], "fr/blog/valorant.html")
        self.assertEqual(m["equipes/t1.html"], "fr/equipes/t1.html")
        self.assertEqual(m["live-fr.html"], "fr/live.html")
        self.assertEqual(m["worlds-2026.html"], "fr/worlds-2026.html")
        self.assertEqual(m["nouveautes.xml"], "fr/nouveautes.xml")
        for absent in ("fr.html", "index.html", "games/valorant.html", "teams/t1.html", "equipes/t1.json", "widget/fr/t1.html", "live.html",
                       "worlds-2026-en.html"):
            self.assertNotIn(absent, m)
        self.assertNotIn("blog-fr.html", m)  # absent du faux site : la carte ne contient que des fichiers qui existent

    def test_public(self):
        self.assertEqual(sd.public("fr/blog/valorant.html"), "/fr/blog/valorant")
        self.assertEqual(sd.public("index.html"), "/")
        self.assertEqual(sd.public("fr/nouveautes.xml"), "/fr/nouveautes.xml")


M = {"live-fr.html": "fr/live.html", "jeux/valorant.html": "fr/jeux/valorant.html", "jeux/counter-strike-2.html": "fr/jeux/counter-strike-2.html",
     "blog-fr/valorant.html": "fr/blog/valorant.html", "blog-fr/dota-2.html": "fr/blog/dota-2.html", "blog-fr.html": "fr/blog.html",
     "equipes/t1.html": "fr/equipes/t1.html",
     "mentions-legales.html": "fr/mentions-legales.html", "confidentialite.html": "fr/confidentialite.html",
     "worlds-2026.html": "fr/worlds-2026.html", "worlds-2026-en.html": "worlds-2026.html", "nouveautes.xml": "fr/nouveautes.xml",
     "nouveautes.html": "fr/nouveautes.html"}


def rw(text: str, old: str, new: str | None = None) -> str:
    return sd.rewrite(text, old, new or old, M)


class Reecriture(unittest.TestCase):
    def test_page_racine_deplacee_profondeur_plus_un(self):
        self.assertEqual(rw('<a href="jeux/valorant.html">', "live-fr.html", "fr/live.html"), '<a href="../fr/jeux/valorant.html">')
        self.assertEqual(rw('<a href="fr.html#jeux">', "live-fr.html", "fr/live.html"), '<a href="../fr.html#jeux">')
        self.assertEqual(rw('<a href="./">', "live-fr.html", "fr/live.html"), '<a href="../">')
        self.assertEqual(rw('<link rel="icon" href="embleme.svg">', "live-fr.html", "fr/live.html"), '<link rel="icon" href="../embleme.svg">')
        self.assertEqual(rw("url(fonts/Rajdhani-Bold.woff2)", "live-fr.html", "fr/live.html"), "url(../fonts/Rajdhani-Bold.woff2)")
        self.assertEqual(rw('<a href="live-de.html">', "live-fr.html", "fr/live.html"), '<a href="../live-de.html">')  # cible hors carte (test) : suit la page
        self.assertEqual(rw('<a href="news.html">', "live-fr.html", "fr/live.html"), '<a href="../news.html">')

    def test_ancres_requetes_et_autres_schemas_intacts(self):
        for text in ('<a href="#f-valorant">', '<a href="https://esportly.eu/match.html?id=1">', '<a href="mailto:a@b.c">',
                     '<a href="webcal://x/y.ics">', 'url("data:image/svg+xml,x")', '<a href="https://protojo.fr">',
                     '<meta name="viewport" content="width=device-width, initial-scale=1">', '<meta content="Valorant en direct.">'):
            self.assertEqual(rw(text, "live-fr.html", "fr/live.html"), text, text)

    def test_page_de_dossier_deplacee(self):
        self.assertEqual(rw('<a href="../games/valorant.html">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="../../games/valorant.html">')
        self.assertEqual(rw('<a href="../blog-fr/valorant.html">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="../../fr/blog/valorant.html">')
        # lien nu entre deux pages du même dossier déplacé : il reste nu (les générateurs écrivent « Autres jeux » ainsi)
        self.assertEqual(rw('<a href="counter-strike-2.html">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="counter-strike-2.html">')
        self.assertEqual(rw('<a href="dota-2.html">', "blog-fr/valorant.html", "fr/blog/valorant.html"), '<a href="dota-2.html">')
        self.assertEqual(rw('<a href="../jeux/valorant.html">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="../../fr/jeux/valorant.html">')  # lien vers soi : chemin entier, pour rename_page
        self.assertEqual(rw('<a href="../fr.html">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="../../fr.html">')
        self.assertEqual(rw('<a href="../">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<a href="../../">')
        self.assertEqual(rw('<img src="../logos-jeux/valorant.png">', "jeux/valorant.html", "fr/jeux/valorant.html"), '<img src="../../logos-jeux/valorant.png">')
        self.assertEqual(rw('<a href="../blog-fr.html">', "blog-fr/valorant.html", "fr/blog/valorant.html"), '<a href="../../fr/blog.html">')

    def test_page_immobile_vers_cible_deplacee(self):
        self.assertEqual(rw('<a href="jeux/valorant.html">', "index.html"), '<a href="fr/jeux/valorant.html">')
        self.assertEqual(rw('<a href="../jeux/valorant.html">', "games/valorant.html"), '<a href="../fr/jeux/valorant.html">')
        self.assertEqual(rw('<a href="/mentions-legales.html">', "404.html"), '<a href="/fr/mentions-legales.html">')
        self.assertEqual(rw('<a href="/privacy.html">', "404.html"), '<a href="/privacy.html">')
        self.assertEqual(rw('<a href="https://esportly.eu/equipes/t1.html">', "widget/fr/t1.html"), '<a href="https://esportly.eu/fr/equipes/t1.html">')
        self.assertEqual(rw("page: '/confidentialite.html'", "analytics.js"), "page: '/fr/confidentialite.html'")
        self.assertEqual(rw('href="nouveautes.xml"', "nouveautes.html", "fr/nouveautes.html"), 'href="../fr/nouveautes.xml"')
        self.assertEqual(rw('href="live-fr.html"', "live-fr.html", "fr/live.html"), 'href="../fr/live.html"')
        self.assertEqual(rw('href="live-de.html"', "live-fr.html", "fr/live.html"), 'href="../live-de.html"')  # cible hors carte (test)
        self.assertEqual(rw('<link>https://esportly.eu/nouveautes.html</link><atom:link href="https://esportly.eu/nouveautes.xml"/>', "nouveautes.xml", "fr/nouveautes.xml"),
                         '<link>https://esportly.eu/fr/nouveautes.html</link><atom:link href="https://esportly.eu/fr/nouveautes.xml"/>')

    def test_page_immobile_cible_immobile_octet_pour_octet(self):
        for text in ('<a href="../games/valorant.html">', '<a href=".././">', '<a href="../">', '<a href="/privacy.html">', 'url(../fonts/R.woff2)'):
            self.assertEqual(rw(text, "games/lol.html"), text, text)
        self.assertEqual(rw('<a href="live.html">', "index.html"), '<a href="live.html">')

    def test_adresses_publiees(self):
        self.assertEqual(rw('href="https://esportly.eu/jeux/valorant"', "jeux/valorant.html", "fr/jeux/valorant.html"), 'href="https://esportly.eu/fr/jeux/valorant"')
        self.assertEqual(rw('<loc>https://esportly.eu/blog-fr</loc>', "sitemap.xml"), '<loc>https://esportly.eu/fr/blog</loc>')
        self.assertEqual(rw('"item": "https://esportly.eu/blog-fr/valorant"', "sitemap.xml"), '"item": "https://esportly.eu/fr/blog/valorant"')
        self.assertEqual(rw('"item": "https://esportly.eu/blog-fr/valorant#s1"', "x.html"), '"item": "https://esportly.eu/fr/blog/valorant#s1"')
        self.assertEqual(rw("https://esportly.eu/worlds-2026", "live-fr.html", "fr/live.html"), "https://esportly.eu/fr/worlds-2026")
        self.assertEqual(rw("https://esportly.eu/worlds-2026-en", "live.html"), "https://esportly.eu/worlds-2026")
        self.assertEqual(rw("https://esportly.eu/worlds-2026.html", "live.html"), "https://esportly.eu/fr/worlds-2026.html")
        self.assertEqual(rw('"https://esportly.eu/"', "live.html"), '"https://esportly.eu/"')
        self.assertEqual(rw('"https://esportly.eu/news"', "live.html"), '"https://esportly.eu/news"')
        self.assertEqual(rw('"https://esportly.eu/partage/jeux/valorant.jpg"', "jeux/valorant.html", "fr/jeux/valorant.html"), '"https://esportly.eu/partage/jeux/valorant.jpg"')
        # liens de partage (WhatsApp, X, e-mail) : l'adresse de la page est encodée dans la requête, « : » devenant %3A
        self.assertEqual(rw("text=A%20https%3A//esportly.eu/equipes/t1.html%0A", "equipes/t1.html", "fr/equipes/t1.html"),
                         "text=A%20https%3A//esportly.eu/fr/equipes/t1.html%0A")
        self.assertEqual(rw("url=https%3A//esportly.eu/teams/t1.html", "teams/t1.html"), "url=https%3A//esportly.eu/teams/t1.html")

    def test_compteur_de_visites(self):
        self.assertEqual(rw("visite?p=/jeux/valorant&amp;go=testflight", "x.html"), "visite?p=/fr/jeux/valorant&amp;go=testflight")
        self.assertEqual(rw('visite?p=/live-fr"', "x.html"), 'visite?p=/fr/live"')
        self.assertEqual(rw('visite?p=/"', "x.html"), 'visite?p=/"')
        self.assertEqual(rw('visite?p=/news"', "x.html"), 'visite?p=/news"')
        self.assertEqual(rw('visite?p=/worlds-2026-en"', "x.html"), 'visite?p=/worlds-2026"')

    def test_fins_de_ligne_conservees(self):
        text = '<a href="jeux/valorant.html">\r\n<a href="fr.html">\r\n'
        self.assertEqual(rw(text, "live-fr.html", "fr/live.html"), '<a href="../fr/jeux/valorant.html">\r\n<a href="../fr.html">\r\n')


class Application(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fake_site(self.root)
        self.today = date(2026, 11, 1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_deplace_et_reecrit(self):
        files, removed = sd.plan(self.root, self.today)
        self.assertIn("fr/live.html", files)
        self.assertIn("live-fr.html", removed)
        self.assertIn("fr/jeux/valorant.html", files)
        self.assertIn("jeux/valorant.html", removed)
        self.assertIn("fr/nouveautes.xml", files)
        self.assertIn("nouveautes.xml", removed)
        self.assertNotIn("worlds-2026.html", files)  # la page anglaise garde worlds-2026-en.html (décision B refusée)
        self.assertIn("fr/worlds-2026.html", files)
        self.assertEqual(sorted(removed), sorted(sd.build_map(self.root)))
        for name in ("fr.html", "index.html", "equipes/t1.json", "games/valorant.html", "docs/notes.html", "privacy.html"):
            self.assertNotIn(name, removed)
        live = files["fr/live.html"]
        self.assertIn(b'href="../fr.html#jeux"', live)
        self.assertIn(b'href="../"', live)
        self.assertIn(b"url(../fonts/Rajdhani-Bold.woff2)", live)
        self.assertIn(b'href="https://esportly.eu/fr/live"', live)
        self.assertIn(b"visite?p=/fr/live&amp;", live)
        self.assertIn(b"\r\n", live)
        self.assertIn(b'href="fr/jeux/valorant.html"', files["fr.html"])  # accueil réécrit sans bouger
        self.assertIn(b'href="fr/live.html"', files["fr.html"])
        self.assertIn(b'href="fr/live.html"', files["live.html"])
        self.assertIn(b'href="../fr/jeux/valorant.html"', files["games/valorant.html"])
        self.assertIn(b'href=".././"', files["games/valorant.html"])  # cible immobile : forme d'origine gardée
        self.assertIn(b'href="/fr/mentions-legales.html"', files["404.html"])
        self.assertIn(b'href="https://esportly.eu/fr/equipes/t1.html"', files["widget/fr/t1.html"])
        self.assertIn(b"page: '/fr/confidentialite.html'", files["analytics.js"])
        self.assertIn(b"page: '/privacy.html'", files["analytics.js"])
        self.assertIn(b'href="../fr/nouveautes.xml"', files["fr/nouveautes.html"])
        self.assertIn(b"https://esportly.eu/fr/nouveautes.html", files["fr/nouveautes.xml"])
        self.assertNotIn("docs/notes.html", files)
        self.assertNotIn("privacy.html", files)  # rien à réécrire : pas dans le plan
        self.assertNotIn("index.html", files)  # ses liens (games, fr.html, live) ne bougent pas

    def test_sitemap(self):
        files, _ = sd.plan(self.root, self.today)
        sitemap = files["sitemap.xml"].decode("utf-8")
        self.assertIn("<loc>https://esportly.eu/fr/live</loc>\n    <lastmod>2026-11-01</lastmod>", sitemap)
        self.assertIn("<loc>https://esportly.eu/live</loc>\n    <lastmod>2026-10-27</lastmod>", sitemap)
        self.assertNotIn("\r\n", sitemap)

    def test_titres_json(self):
        files, _ = sd.plan(self.root, self.today)
        text = files["seo/titres.json"].decode("utf-8")
        self.assertEqual(list(json.loads(text)), ["/news", "/fr/jeux/valorant", "/fr/live"])
        self.assertEqual(json.loads(text)["/fr/live"], {"title": "L", "description": "l"})
        self.assertTrue(text.startswith('{\n "/news": {\n  "title"'))
        self.assertTrue(text.endswith("}\n"))

    def test_redirects(self):
        files, _ = sd.plan(self.root, self.today)
        lines = [line for line in files["_redirects"].decode("utf-8").split("\n") if line and not line.startswith("#")]
        for rule in ("/live-fr /fr/live 301", "/live-fr.html /fr/live 301", "/jeux/valorant /fr/jeux/valorant 301",
                     "/jeux/valorant.html /fr/jeux/valorant 301", "/equipes/t1 /fr/equipes/t1 301", "/worlds-2026 /fr/worlds-2026 301",
                     "/worlds-2026.html /fr/worlds-2026 301", "/nouveautes.xml /fr/nouveautes.xml 301",
                     "/fr/merci /merci 301", "/fr/merci.html /merci 301", "/fr/inscription-erreur /inscription-erreur 301",
                     "/jeux/* /fr/jeux/:splat 301", "/blog-fr/* /fr/blog/:splat 301", "/blog-pt/* /pt/blog/:splat 301"):
            self.assertIn(rule, lines, rule)
        self.assertNotIn("/equipes/* /fr/equipes/:splat 301", lines)  # les fiches JSON y restent
        sources = [line.split()[0] for line in lines]
        for source in ("/worlds-2026-en", "/worlds-2026-en.html", "/merci", "/merci.html", "/verifie", "/desinscrit", "/inscription-erreur"):
            self.assertNotIn(source, sources)  # décisions B et E refusées : ces adresses ne bougent pas
        # Aucune règle ne part d'une adresse qui est aussi une nouvelle adresse (une page qui en remplace une autre)
        self.assertNotIn("/b", [line.split()[0] for line in sd.redirects({"a.html": "b.html", "b.html": "fr/b.html"}).splitlines() if line.startswith("/")])
        self.assertFalse(any(line.split()[0] == line.split()[1] for line in lines))
        self.assertTrue(all("*" in line for line in lines[-8:]) and not any("*" in line for line in lines[:-8]))  # jokers en dernier
        self.assertNotIn("\r", files["_redirects"].decode("utf-8"))
        mapping = sd.build_map(self.root)
        pages = [old for old in mapping if old.endswith(".html") and sd.public(old) not in {sd.public(new) for new in mapping.values()}]
        self.assertEqual(len(lines), 2 * len(pages) + 1 + len(sd.EXTRA_RULES) + 8)
        self.assertEqual(len(sd.EXTRA_RULES), 8)  # /fr/merci (envoyée par erreur entre le 1er et le 2 novembre) et ses 3 sœurs, avec .html

    def test_refus_si_deja_fait(self):
        (self.root / "fr").mkdir()
        with self.assertRaises(sd.Refus):
            sd.plan(self.root, self.today)

    def test_essai_n_ecrit_rien(self):
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(sd.main(["--essai"], self.root), 0)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}, before)
        self.assertFalse((self.root / "fr").exists())

    def test_main_ecrit_et_supprime(self):
        self.assertEqual(sd.main([], self.root), 0)
        self.assertTrue((self.root / "fr/live.html").is_file())
        self.assertTrue((self.root / "fr/jeux/valorant.html").is_file())
        self.assertTrue((self.root / "_redirects").is_file())
        self.assertFalse((self.root / "live-fr.html").exists())
        self.assertFalse((self.root / "jeux").exists())  # dossier vidé, supprimé
        self.assertTrue((self.root / "equipes/t1.json").is_file())  # dossier gardé : les fiches y restent
        self.assertFalse((self.root / "equipes/t1.html").exists())
        self.assertEqual((self.root / "fr/live.html").read_bytes().count(b"\r\n"), 1)
        self.assertEqual(sd.main([], self.root), 1)  # rejouer : refus, rien ne change


if __name__ == "__main__":
    unittest.main()
