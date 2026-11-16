"""Tests des chemins des sous-dossiers de langue dans les générateurs (site_chrome, actualites, live, blog, menu_partout) :
`py -3.13 -m unittest discover -s .github/scripts -p "test_*.py"` depuis la racine du site."""
from __future__ import annotations

import re
import unittest
from datetime import timedelta

import actualites as an
import blog
import live
import menu_partout as mp
import site_chrome as sc
from test_actualites import home_footer, item, template
from test_blog import HOME_PAGES, NAMES, fiche, game_page
from test_live import NAMES as LIVE_NAMES, NOW, T, match
from test_menu_partout import BRAND, LANG_LINK, header_of, model


class Tables(unittest.TestCase):
    def test_tables_des_sous_dossiers(self):
        self.assertEqual(sc.HUBS, {"en": "blog.html", "fr": "fr/blog.html", "es": "es/blog.html", "de": "de/blog.html", "pt-BR": "pt/blog.html"})
        self.assertEqual(sc.LIVE_PAGES, {"en": "live.html", "fr": "fr/live.html", "es": "es/live.html", "de": "de/live.html", "pt-BR": "pt/live.html"})
        self.assertEqual(sc.BLOG_DIRS, {"en": "blog", "fr": "fr/blog", "es": "es/blog", "de": "de/blog", "pt-BR": "pt/blog"})
        self.assertEqual(sc.GAME_DIRS, {"en": "games", "fr": "fr/jeux", "es": "es/juegos", "de": "de/spiele", "pt-BR": "pt/jogos"})
        self.assertEqual(sc.LANG_DIRS, {"en": "", "fr": "fr/", "es": "es/", "de": "de/", "pt-BR": "pt/"})
        self.assertEqual(sc.HOMES, an.HOMES)
        self.assertEqual(an.PAGES, {"fr": "fr/actualites.html", "en": "news.html", "es": "es/noticias.html", "de": "de/nachrichten.html",
                                    "pt-BR": "pt/ultimas-noticias.html"})
        self.assertEqual(an.TEMPLATES, {"fr": "fr/nouveautes.html", "en": "whats-new.html", "es": "es/novedades.html", "de": "de/neuigkeiten.html",
                                        "pt-BR": "pt/novidades.html"})
        self.assertEqual(an.WEEKLY, {"fr": "fr/matchs-de-la-semaine.html", "en": "matches-this-week.html", "es": "es/partidos-de-la-semana.html",
                                     "de": "de/spiele-der-woche.html", "pt-BR": "pt/partidas-da-semana.html"})
        self.assertEqual(an.EVENT_SUFFIX, {"en": "-en"})  # seules les pages d'événements anglaises gardent un suffixe

    def test_prefixe_et_liens(self):
        self.assertEqual(sc.prefix_for("blog.html"), "")
        self.assertEqual(sc.prefix_for("fr/blog.html"), "../")
        self.assertEqual(sc.prefix_for("fr/blog/valorant.html"), "../../")
        self.assertEqual(sc.home_link("en", ""), "./")
        self.assertEqual(sc.home_link("en", "../"), "../")
        self.assertEqual(sc.home_link("fr", "../../"), "../../fr.html")
        self.assertEqual(sc.home_link("pt-BR", "/"), "/pt.html")


class News(unittest.TestCase):
    def test_page_d_evenement(self):
        self.assertEqual(an.page_for("worlds-2026", "pt-BR"), "pt/worlds-2026.html")
        self.assertEqual(an.page_for("worlds-2026", "en"), "worlds-2026-en.html")  # l'anglais garde son suffixe (décision B refusée)
        self.assertEqual(an.page_for("worlds-2026", "fr"), "fr/worlds-2026.html")
        self.assertEqual(an.page_for("whats-new", "fr"), "fr/nouveautes.html")
        self.assertEqual(an.page_for("weekly", "es"), "es/partidos-de-la-semana.html")

    def test_liens_des_infos_vus_de_la_page_news_et_de_l_accueil(self):
        items = [item("a", link={"page": "worlds-2026"}), item("b", link={"blog": "pgl-2026"})]
        infos = an.render_infos(items, "es")  # vu de es/noticias.html
        self.assertIn('href="../es/worlds-2026.html"', infos)
        self.assertIn('href="../es/blog/pgl-2026.html"', infos)
        infos_en = an.render_infos(items, "en")  # vu de news.html, à la racine
        self.assertIn('href="worlds-2026-en.html"', infos_en)
        self.assertIn('href="blog/pgl-2026.html"', infos_en)
        home = an.render_home_block(items, None, "es")  # vu de es.html, à la racine
        self.assertIn('href="es/worlds-2026.html"', home)
        self.assertIn('href="es/blog/pgl-2026.html"', home)
        self.assertIn('<a href="es/noticias.html">', home)

    def test_page_news_francaise(self):
        page = an.render_page("fr", template("fr"), "", "", "", home_footer("fr"))
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/actualites">', page)
        self.assertIn('<link rel="alternate" hreflang="en" href="https://esportly.eu/news">', page)
        self.assertIn('<link rel="alternate" hreflang="pt-BR" href="https://esportly.eu/pt/ultimas-noticias">', page)
        header = re.search(r"<header>.*?</header>", page, re.S).group(0)
        self.assertIn('<a href="../fr/actualites.html" aria-current="page">Actualités</a><a href="../fr/blog.html">Blog</a>'
                      '<a class="live" href="../fr/live.html">Live</a>', header)
        self.assertIn('<details class="mega"><summary>Jeux', header)  # le panneau des jeux a remplacé l'ancre
        self.assertIn('<a href="../fr/jeux/valorant.html">', header)
        self.assertIn("visite?p=/fr/actualites&amp;go=testflight", header)
        footer = re.search(r"<footer>.*?</footer>", page, re.S).group(0)
        self.assertIn('<a href="../fr.html#jeux">Games</a>', footer)
        self.assertIn('href="../mailto:', footer) if False else self.assertIn('href="mailto:contact@example.org"', footer)
        self.assertIn("visite?p=/fr/actualites&amp;go=testflight", footer)
        self.assertEqual(re.findall(r'visite\?p=([^"&]*)', page).count("/fr/actualites"), page.count("visite?p="))

    def test_page_news_anglaise_inchangee(self):
        page = an.render_page("en", template("en"), "", "", "", home_footer("en"))
        header = re.search(r"<header>.*?</header>", page, re.S).group(0)
        self.assertIn('<a href="news.html" aria-current="page">News</a><a href="blog.html">Blog</a><a class="live" href="live.html">Live</a>', header)
        self.assertIn('<details class="mega"><summary>Games', header)
        self.assertIn('<a href="./#jeux">All games →</a>', header)  # le lien « tous les jeux » garde l'ancre de l'accueil


class Live(unittest.TestCase):
    def test_page_live_francaise(self):
        page = live.render_page("fr", template("fr"), [match("A – B", NOW + timedelta(hours=2))], NOW, T["fr"], home_footer("fr"), LIVE_NAMES)
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/live">', page)
        self.assertIn('<link rel="alternate" hreflang="en" href="https://esportly.eu/live">', page)
        self.assertIn('<link rel="alternate" hreflang="es" href="https://esportly.eu/es/live">', page)
        self.assertIn('<a href="../fr/actualites.html">Actualités</a><a href="../fr/blog.html">Blog</a>'
                      '<a class="live" href="../fr/live.html" aria-current="page">Live</a>', page)
        self.assertIn("visite?p=/fr/live&amp;go=testflight", page)
        self.assertIn('<details class="mega"><summary>Jeux', page)
        again = live.render_page("fr", page, [match("A – B", NOW + timedelta(hours=2))], NOW, T["fr"], home_footer("fr"), LIVE_NAMES)
        self.assertEqual(again, page)


class Blog(unittest.TestCase):
    def test_article_francais(self):
        page = fiche("valorant")
        main_html = blog.render_guide_main(page, "fr", NAMES, ("../../fr.html", "Accueil"), [], [], [fiche("league-of-legends")])
        self.assertTrue(main_html.startswith('<nav class="crumbs" aria-label="Breadcrumb"><a href="../../fr.html">Accueil</a> › '
                                             '<a href="../../fr/blog.html">Blog</a> › <span>Valorant</span></nav>'))
        self.assertIn('<img class="glogo" src="../../logos-jeux/valorant.png"', main_html)
        self.assertIn('<p><a href="../../fr/jeux/valorant.html">Voir ce que fait eSportly pour Valorant</a></p>', main_html)
        self.assertIn("visite?p=/fr/blog/valorant&amp;go=testflight", main_html)
        self.assertIn('<a href="league-of-legends.html">', main_html)  # les autres fiches : même dossier
        shown = blog.render_guide_page("fr", game_page("fr", "valorant"), page, main_html, "", HOME_PAGES["fr"])
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/blog/valorant">', shown)
        self.assertIn('<link rel="alternate" hreflang="es" href="https://esportly.eu/es/blog/valorant">', shown)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://esportly.eu/blog/valorant">', shown)
        menu = re.search(r"<header>.*?</header>", shown).group(0)
        self.assertIn('<a href="../../fr/actualites.html">Actualités</a><a href="../../fr/blog.html" aria-current="page">Blog</a>'
                      '<a class="live" href="../../fr/live.html">Live</a>', menu)
        self.assertIn('<details class="mega"><summary>Jeux', menu)  # le panneau des jeux a remplacé l'ancre
        footer = re.search(r"<footer>.*?</footer>", shown, re.S).group(0)
        self.assertIn('<a href="../../fr/actualites.html">News</a>', footer)
        self.assertIn('<a href="../../privacy.html">', footer)

    def test_article_anglais_inchange(self):
        page = fiche("valorant")
        main_html = blog.render_guide_main(page, "en", NAMES, ("../", "Home"), [], [], [])
        self.assertIn('<a href="../blog.html">Blog</a>', main_html)
        self.assertIn('src="../logos-jeux/valorant.png"', main_html)
        self.assertIn('<a href="../games/valorant.html">', main_html)
        shown = blog.render_guide_page("en", game_page("en", "valorant"), page, main_html, "", HOME_PAGES["en"])
        self.assertIn('<a href="../news.html">News</a><a href="../blog.html" aria-current="page">Blog</a><a class="live" href="../live.html">Live</a>', shown)

    def test_accueil_du_blog_francais(self):
        shown = blog.render_hub_main("fr", [fiche("valorant")], NAMES)
        self.assertIn('<a class="card" data-game="valorant" href="../fr/blog/valorant.html"><img src="../logos-jeux/valorant.png"', shown)
        english = blog.render_hub_main("en", [fiche("valorant")], NAMES)
        self.assertIn('<a class="card" data-game="valorant" href="blog/valorant.html"><img src="logos-jeux/valorant.png"', english)

    def test_lien_de_guide_dans_la_page_de_jeu(self):
        self.assertIn('<a href="../../fr/blog/valorant.html">', blog.render_guide_link(fiche("valorant"), "fr", "Valorant"))
        self.assertIn('<a href="../blog/valorant.html">', blog.render_guide_link(fiche("valorant"), "en", "Valorant"))

    def test_couverture(self):
        page = fiche("valorant", image={"kind": "ia"})
        self.assertIn('src="../../couvertures/valorant.webp"', blog.render_cover(page, "fr"))
        self.assertIn('src="../couvertures/valorant.webp"', blog.render_cover(page, "en"))


class MenuPartout(unittest.TestCase):
    def test_page_d_equipe_francaise(self):
        brand = BRAND.replace("../fr.html", "../../fr.html").replace("../embleme.svg", "../../embleme.svg")
        after = mp.render(model("fr", header=brand + LANG_LINK, p="fr/equipes/t1"), "fr/equipes/t1.html")
        header = header_of(after)
        self.assertIn('<a href="../../fr/actualites.html">Actualités</a><a href="../../fr/blog.html">Blog</a>'
                      '<a class="live" href="../../fr/live.html">Live</a>', header)
        self.assertIn('<nav aria-label="Sections de la page"><details class="mega"><summary>Jeux', header)
        self.assertIn('<a href="../../fr/jeux/valorant.html">', header)
        self.assertIn("visite?p=/fr/equipes/t1&amp;go=testflight", header)

    def test_page_legale_francaise_sans_en_tete(self):
        from test_menu_partout import legal
        after = mp.render(legal("fr", p="fr/mentions-legales"), "fr/mentions-legales.html")
        header = header_of(after)
        self.assertIn('<a class="brand" href="../fr.html"><img src="../embleme.svg"', header)
        self.assertIn('<a href="../fr/actualites.html">Actualités</a>', header)
        self.assertIn("url(../fonts/Rajdhani-Bold.woff2)", after)


if __name__ == "__main__":
    unittest.main()
