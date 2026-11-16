"""Tests de actualites.py (partie News du site).

    PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONTZPATH=C:\\Users\\horny\\anaconda3\\Lib\\site-packages\\pytz\\zoneinfo \\
        py -3.13 -m unittest discover -s .github/scripts -p "test_actualites.py" -v
"""
import ast
import base64
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import actualites as an
import site_chrome


def text(title: str = "Titre", body: str = "Texte.") -> dict:
    return {"title": title, "text": body}


def item(item_id: str = "a-1", **changes) -> dict:
    """Une entrée valide dans les 5 langues, modifiée par `changes`."""
    entry = {"id": item_id, "date": "2026-11-02", **{lang: text() for lang in an.LANGS}}
    entry.update(changes)
    return entry


def news(items=None, events=None) -> dict:
    return {"events": {"worlds-2026": {"knockout_from": "2026-11-03"}} if events is None else events,
            "items": [item()] if items is None else items}


class ValidationEtVisibilite(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.site = Path(tmp.name)
        (self.site / "worlds-2026-en.html").write_text("<html></html>", encoding="utf-8")  # la page anglaise de l'événement
        (self.site / "news").mkdir()
        self.path = self.site / "news" / "news.json"

    def write(self, data) -> Path:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return self.path

    def problems(self, data) -> list[str]:
        with self.assertRaises(an.NewsError) as caught:
            an.load_news(self.write(data), self.site)
        return caught.exception.problems

    def test_fichier_valide(self):
        data = news(items=[item(until="2026-11-30", pin=True, link={"page": "worlds-2026"})])
        self.assertEqual(an.load_news(self.write(data), self.site), data)

    def test_lien_vers_un_article_du_blog(self):
        """{"blog": <id>} : l'article existe dans blog-src/pages ; sinon, ou avec un identifiant invalide, refus."""
        pages = self.site / "blog-src" / "pages"
        pages.mkdir(parents=True)
        (pages / "pgl-2026.json").write_text("{}", encoding="utf-8")
        data = news(items=[item(link={"blog": "pgl-2026"})])
        self.assertEqual(an.load_news(self.write(data), self.site), data)
        found = " | ".join(self.problems(news(items=[item("a", link={"blog": "absent"}), item("b", link={"blog": 3}),
                                                     item("c", link={"blog": "pgl-2026", "url": "https://x.org"})])))
        for expected in ["article « absent » introuvable (blog-src/pages/absent.json)", "« 3 » invalide", '{"blog": …}']:
            self.assertIn(expected, found)

    def test_cle_inconnue_refusee(self):
        found = self.problems({"events": {}, "itmes": []})
        self.assertTrue(any("itmes" in p for p in found), found)
        bad = item()
        bad["fr"] = {"titel": "x", "text": "y"}
        found = self.problems(news(items=[bad]))
        self.assertTrue(any("titel" in p for p in found), found)

    def test_chaque_regle_de_validation(self):
        no_de = item("sans-de")
        del no_de["de"]
        items = [no_de,
                 item("long", fr=text(title="x" * 81)),
                 item("balise", en=text(body="un <b>texte</b>")),
                 item("double"), item("double"),
                 item("Mauvais ID"),
                 item("mauvaise-date", date="2026-13-40"),
                 item("until-avant", date="2026-11-10", until="2026-11-09"),
                 item("page-inconnue", link={"page": "inconnue"}),
                 item("lien-http", link={"url": "http://x.org"}),
                 item("lien-espace", link={"url": "https://a b"})]
        events = {"worlds-2026": {"knockout_from": "demain"}, "inconnu-2026": {"knockout_from": None}}
        found = " | ".join(self.problems(news(items=items, events=events)))
        for expected in ["langue « de » manquante", "81 caractères", "contient « < »", "« double » en double", "« Mauvais ID » invalide",
                         "« 2026-13-40 » n'est pas une date", "avant date", "page « inconnue » inconnue", "https://",
                         "inconnu-2026", "introuvable", "knockout_from"]:
            self.assertIn(expected, found)

    def test_page_for(self):
        self.assertEqual(an.page_for("worlds-2026", "pt-BR"), "pt/worlds-2026.html")
        self.assertEqual(an.page_for("worlds-2026", "fr"), "fr/worlds-2026.html")
        self.assertEqual(an.page_for("worlds-2026", "en"), "worlds-2026-en.html")
        self.assertEqual(an.page_for("weekly", "de"), "de/spiele-der-woche.html")
        self.assertEqual(an.page_for("whats-new", "fr"), "fr/nouveautes.html")

    def test_infos_visibles(self):
        items = [item("futur", date="2026-11-12"),
                 item("jusqua-aujourdhui", date="2026-11-01", until="2026-11-10"),
                 item("expiree", date="2026-11-01", until="2026-11-09"),
                 item("epinglee", date="2026-11-05", pin=True),
                 item("b-id", date="2026-11-08"), item("a-id", date="2026-11-08")]
        shown = [i["id"] for i in an.visible_items(items, date(2026, 11, 10))]
        self.assertEqual(shown, ["epinglee", "a-id", "b-id", "jusqua-aujourdhui"])


UTC = timezone.utc
ICS = ("BEGIN:VCALENDAR\r\n"
       "BEGIN:VEVENT\r\nUID:match-1@x\r\nDTSTART:20261103T190000Z\r\nSUMMARY:Quarterfinal 1: TBD vs\r\n  TBD\r\n"
       "DESCRIPTION:League of Legends · Worlds\\, 2026\r\nURL:https://esportly.eu/match.html?id=1\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\n"
       "BEGIN:VEVENT\r\nUID:match-2@x\r\nDTSTART:20261104T190000Z\r\nSUMMARY:Équipe A – Équipe B\r\n"
       "DESCRIPTION:League of Legends · Worlds · 2026\r\nURL:https://esportly.eu/match.html?id=2\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\n"
       "END:VCALENDAR\r\n")


def match(summary: str, start: datetime, status: str = "CONFIRMED") -> dict:
    return {"summary": summary, "description": "League of Legends · Worlds · 2026", "url": "https://esportly.eu/match.html?id=1",
            "status": status, "start": start}


class SelectionDesMatchs(unittest.TestCase):
    NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    def test_lecture_ics(self):
        found = an.read_events("worlds-2026", fetch=lambda url: ICS)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["summary"], "Quarterfinal 1: TBD vs TBD")
        self.assertEqual(found[0]["description"], "League of Legends · Worlds, 2026")
        self.assertEqual(found[0]["start"], datetime(2026, 11, 3, 19, 0, tzinfo=UTC))
        self.assertEqual(found[0]["url"], "https://esportly.eu/match.html?id=1")
        self.assertEqual((found[0]["status"], found[1]["status"]), ("CONFIRMED", "CANCELLED"))

    def test_calendrier_en_echec(self):
        calls = []

        def broken(url):
            calls.append(url)
            raise OSError("serveur indisponible")

        with contextlib.redirect_stdout(io.StringIO()) as printed:  # les échecs sont signalés sur la sortie, comme matchs.py
            self.assertIsNone(an.read_events("worlds-2026", fetch=broken))
        self.assertIn("serveur indisponible", printed.getvalue())
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("/evenement/worlds-2026.ics"))
        flaky = iter([OSError("une fois"), ICS])

        def second_time(url):
            answer = next(flaky)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(len(an.read_events("worlds-2026", fetch=second_time)), 2)

    def test_titres_de_phase(self):
        start = self.NOW
        for title in ["Grand Final: TBD vs TBD", "Semifinal 2: TBD vs TBD", "Quarterfinal 4: TBD vs TBD", "Upper Final: A vs B",
                      "LOWER BRACKET FINALS", "Semi-final 1"]:
            self.assertTrue(an.is_important(match(title, start), None), title)
        for title in ["Round 1: TBD vs TBD", "Group Stage: A vs B", "FaZe – Finalist Esports", "Équipe A – Équipe B"]:
            self.assertFalse(an.is_important(match(title, start), None), title)

    def test_knockout_from_en_heure_de_paris(self):
        knockout = date(2026, 11, 3)
        self.assertTrue(an.is_important(match("A – B", datetime(2026, 11, 2, 23, 0, tzinfo=UTC)), knockout))
        self.assertFalse(an.is_important(match("A – B", datetime(2026, 11, 2, 22, 0, tzinfo=UTC)), knockout))

    def test_sans_date_ni_phase(self):
        self.assertFalse(an.is_important(match("A – B", self.NOW), None))
        self.assertTrue(an.is_important(match("A – B", self.NOW), date(2026, 10, 1)))

    def test_fenetre(self):
        config = {"worlds-2026": {"knockout_from": None}}

        def kept(start):
            return an.select_matches({"worlds-2026": [match("Grand Final: A vs B", start)]}, config, self.NOW)

        self.assertEqual(len(kept(self.NOW - timedelta(hours=3))), 1)
        self.assertEqual(len(kept(self.NOW - timedelta(hours=3, seconds=1))), 0)
        self.assertEqual(len(kept(self.NOW + timedelta(days=14))), 1)
        self.assertEqual(len(kept(self.NOW + timedelta(days=14, seconds=1))), 0)

    def test_selection_triee_et_annulee(self):
        config = {"worlds-2026": {"knockout_from": "2026-11-03"}, "vct-champions-2026": {"knockout_from": "2026-11-01"}}
        calendars = {"worlds-2026": [match("B – C", datetime(2026, 11, 5, 19, 0, tzinfo=UTC)),
                                     match("Grand Final: X vs Y", datetime(2026, 11, 4, 19, 0, tzinfo=UTC), status="CANCELLED"),
                                     match("D – E", datetime(2026, 11, 3, 19, 0, tzinfo=UTC))],
                     "vct-champions-2026": [match("F – G", datetime(2026, 11, 4, 19, 0, tzinfo=UTC))]}
        found = an.select_matches(calendars, config, self.NOW)
        self.assertEqual([(m["slug"], m["summary"]) for m in found],
                         [("worlds-2026", "D – E"), ("vct-champions-2026", "F – G"), ("worlds-2026", "B – C")])


LABEL_KEYS = ["kicker", "title", "lead", "cta", "matches", "infos", "no_match", "no_info", "more", "tz", "next_match", "all_news", "read"]


class Fragments(unittest.TestCase):
    START = datetime(2026, 11, 14, 19, 0, tzinfo=UTC)  # samedi 14 novembre, 20:00 à Paris

    def test_libelles_complets(self):
        for lang in an.LANGS:
            for key in LABEL_KEYS:
                self.assertTrue(an.LABELS[lang][key], (lang, key))
        self.assertEqual([an.LABELS[lang]["kicker"] for lang in an.LANGS], ["Actualités", "News", "Noticias", "Nachrichten", "Notícias"])

    def test_echappement(self):
        evil = match('A & B <b>"x"</b>', self.START)
        shown = an.render_matches([evil], "en")
        self.assertIn("A &amp; B &lt;b&gt;", shown)
        self.assertNotIn('<b>"x"</b>', shown)
        info = item("evil", en=text(title="</script><img onerror=x>", body='un "texte" & <i>'))
        shown = an.render_infos([info], "en")
        self.assertNotIn("</script>", shown)
        self.assertNotIn("<img", shown)
        ld = an.render_jsonld([match("Final </script><script>alert(1)</script>", self.START)])
        self.assertNotIn("</", ld.replace("</script>", "", 1))
        payload = ld[len('<script type="application/ld+json">'):-len("</script>")]
        self.assertEqual(json.loads(payload)[0]["name"], "Final </script><script>alert(1)</script>")

    def test_etats_vides(self):
        self.assertIn("Aucun match important dans les 14 prochains jours.", an.render_matches([], "fr"))
        self.assertIn("Derzeit keine Meldungen.", an.render_infos([], "de"))
        self.assertEqual(an.render_jsonld([]), "")

    def test_liens_par_langue(self):
        shown = an.render_infos([item("a", link={"page": "worlds-2026"})], "es")
        self.assertIn('href="../es/worlds-2026.html"', shown)  # vu de es/noticias.html
        self.assertNotIn("noopener", shown)
        self.assertIn("Saber más", shown)
        shown = an.render_infos([item("b", link={"url": "https://x.org/a?b=1&c=2"})], "en")
        self.assertIn('href="https://x.org/a?b=1&amp;c=2" rel="noopener"', shown)
        for lang, href, label in (("fr", "../fr/blog/pgl-2026.html", "Lire l'article →"), ("en", "blog/pgl-2026.html", "Read the article →"),
                                  ("pt-BR", "../pt/blog/pgl-2026.html", "Ler o artigo →")):
            shown = an.render_infos([item("c", link={"blog": "pgl-2026"})], lang)
            self.assertIn(f'<p><a href="{href}">{label}</a></p>', shown)  # l'article de la news, une page du Blog
            self.assertNotIn("noopener", shown)

    def test_jours_et_mois(self):
        day = date(2026, 11, 14)
        self.assertEqual(an.day_label(day, "fr", True), "samedi 14 novembre")
        self.assertEqual(an.day_label(day, "en", False), "14 November 2026")
        self.assertEqual(an.day_label(day, "pt-BR", True), "sábado 14 novembro")
        self.assertEqual(an.day_label(day, "de", True), "Samstag 14 November")

    def test_heure_de_paris_dans_les_matchs(self):
        shown = an.render_matches([match("A – B", self.START)], "fr")
        self.assertIn(">samedi 14 novembre, 20:00<", shown)
        self.assertIn('<time datetime="2026-11-14T19:00:00+00:00">', shown)
        self.assertIn("heure de Paris", shown)

    def test_limites(self):
        many = [item(f"i-{n:02d}", date="2026-11-01") for n in range(25)]
        self.assertEqual(an.render_infos(many, "en").count("<li"), 20)
        self.assertEqual(an.render_home_block(many[:5], None, "en").count("<h3>"), 3)

    def test_bloc_accueil(self):
        self.assertEqual(an.render_home_block([], None, "en"), "")
        items = [item("p", en=text("Pinned one"), pin=True), item("n", en=text("Newest one")),
                 item("c", en=text("Third one")), item("d", en=text("Fourth one"))]
        block = an.render_home_block(items, None, "en")
        self.assertTrue(block.startswith('<section class="block news" id="news">'))
        self.assertLess(block.index("Pinned one"), block.index("Newest one"))
        self.assertIn("Third one", block)
        self.assertNotIn("Fourth one", block)
        self.assertIn('<a href="news.html">All news →</a>', block)
        self.assertIn("<!-- prochain-match --><!-- /prochain-match -->", block)
        with_match = an.render_home_block([], match("Semifinal 2: TBD vs TBD", self.START), "fr")
        self.assertIn('<li class="match">', with_match)
        self.assertIn("Prochain match important", with_match)
        self.assertIn('<a href="fr/actualites.html">Toutes les actualités →</a>', with_match)

    def test_fragments_sur_une_ligne(self):
        pieces = [an.render_matches([match("A – B", self.START)], "en"), an.render_matches([], "en"),
                  an.render_infos([item()], "en"), an.render_infos([], "en"), an.render_jsonld([match("A – B", self.START)]),
                  an.render_home_block([item()], match("A – B", self.START), "en")]
        for piece in pieces:
            self.assertNotIn("\n", piece)
            self.assertNotIn("\r", piece)

    def test_style(self):
        for selector in [".news", ".infos", ".infos li", ".more"]:
            self.assertIn(selector, an.INFOS_STYLE)
        self.assertNotIn("<", an.INFOS_STYLE)


def language_links(lang: str) -> str:
    """Le menu de langue d'une page « What's new » : un lien par langue, la langue courante marquée."""
    return "".join(f'<li><a href="{an.TEMPLATES[other]}" hreflang="{other}" lang="{other}"'
                   f'{" aria-current=" + chr(34) + "page" + chr(34) if other == lang else ""}>{other}</a></li>' for other in an.LANGS)


def home_footer(lang: str) -> str:
    """Le pied de page d'un accueil : le bloc que les pages News reprennent (marque, liens de l'app dont News et Blog, une langue par ligne)."""
    flags = "".join(f'<li class="fl"><a href="{"./" if other == "en" else an.HOMES[other]}" hreflang="{other}" lang="{other}"'
                    f'{" aria-current=" + chr(34) + "page" + chr(34) if other == lang else ""}>{other}</a></li>' for other in an.LANGS)
    return (f'<footer><div class="wrap"><div class="fgrid"><div class="fbrand"><a class="brand" href="{"./" if lang == "en" else an.HOMES[lang]}">'
            f'<img src="embleme.svg" alt="" width="44" height="44"></a><a class="fbeta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{lang}&amp;go=testflight">Join</a></div>'
            f'<div><ul><li><a href="#jeux">Games</a></li><li><a href="{an.PAGES[lang]}">News</a></li><li><a href="{site_chrome.HUBS[lang]}">Blog</a></li></ul></div>'
            f'<div><ul><li><a href="mailto:contact@example.org">Contact</a></li>{flags}</ul></div></div></div></footer>')


def template(lang: str) -> str:
    """Un modèle minimal construit comme les pages « What's new » du site (canonical, hreflang, RSS, CSP, main)."""
    alternates = "".join(f'<link rel="alternate" hreflang="{other}" href="https://esportly.eu/{an.TEMPLATES[other]}">\r\n' for other in an.LANGS)
    return (f'<!doctype html>\r\n<html lang="{lang}">\r\n<head>\r\n'
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; script-src 'sha256-OLD='; style-src 'self' 'unsafe-inline'\">\r\n"
            f'<title>What&#x27;s new – eSportly</title>\r\n<meta name="description" content="Old description">\r\n'
            f'<link rel="canonical" href="https://esportly.eu/{an.TEMPLATES[lang]}">\r\n{alternates}'
            f'<link rel="alternate" hreflang="x-default" href="https://esportly.eu/{an.TEMPLATES["en"]}">\r\n'
            f'<link rel="alternate" type="application/rss+xml" title="RSS" href="{an.TEMPLATES[lang].replace(".html", ".xml")}">\r\n'
            f'<meta property="og:title" content="Old"><meta property="og:description" content="Old">\r\n'
            f'<style>\r\nbody{{margin:0}}\r\n</style>\r\n</head>\r\n<body>\r\n'
            f'<header><div class="wrap"><a class="brand" href="{an.HOMES[lang]}"><img src="embleme.svg" alt="" width="36" height="36"><span><i>e</i>Sportly</span></a>'
            f'<details class="lang langs"><summary aria-label="Langue"><span>{lang}</span></summary><ul>{language_links(lang)}</ul></details>'
            f'<a class="soon" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{an.TEMPLATES[lang][:-5]}&amp;go=testflight">Join</a></div></header>\r\n'
            f'<main class="wrap"><section class="hero">OLD HERO</section></main>\r\n<footer></footer>\r\n</body>\r\n</html>\r\n')


DECLARED = re.compile(r'<link rel="canonical" href="([^"]*)"|<link rel="alternate" hreflang="[^"]*" href="([^"]*)"'
                      r'|<meta property="og:url" content="([^"]*)"|<loc>([^<]*)</loc>|"(?:url|item|mainEntityOfPage|@id)":\s*"([^"]*)"')


def declared_urls(text: str) -> list[str]:
    """Adresses déclarées d'une page ou d'un sitemap : canonical, hreflang, og:url, <loc>, url/item/mainEntityOfPage/@id."""
    return [next(group for group in found if group) for found in DECLARED.findall(text)]


class AdressesPubliees(unittest.TestCase):
    """Le Worker renvoie (307) toute adresse en .html vers la même sans .html : les adresses déclarées sont sans extension."""

    def test_public_url(self):
        cases = {"privacy.html": "https://esportly.eu/privacy", "blog/valorant.html": "https://esportly.eu/blog/valorant",
                 "index.html": "https://esportly.eu/", "fr.html": "https://esportly.eu/fr", "blog-fr.html": "https://esportly.eu/blog-fr",
                 "dossier/index.html": "https://esportly.eu/dossier/", "fr.html#jeux": "https://esportly.eu/fr#jeux",
                 "https://esportly.eu/teams/t1.html": "https://esportly.eu/teams/t1", "https://esportly.eu/": "https://esportly.eu/",
                 "https://esportly.eu/#jeux": "https://esportly.eu/#jeux", "https://esportly.eu/blog": "https://esportly.eu/blog",
                 "https://esportly.eu/match.html?id=1": "https://esportly.eu/match.html?id=1",
                 "https://esportly.eu/partage/jeux/valorant.jpg": "https://esportly.eu/partage/jeux/valorant.jpg",
                 "https://example.org/a.html": "https://example.org/a.html"}
        for given, wanted in cases.items():
            with self.subTest(given=given):
                self.assertEqual(an.public_url(given), wanted)
                self.assertEqual(an.public_url(an.public_url(given)), wanted)

    def test_public_urls_ne_touche_que_les_adresses_declarees(self):
        page = ('<link rel="canonical" href="https://esportly.eu/games/valorant.html">\r\n'
                '<link rel="alternate" hreflang="fr" href="https://esportly.eu/jeux/valorant.html">\r\n'
                '<link rel="alternate" hreflang="en" href="https://esportly.eu/">\n'
                '<link rel="alternate" type="application/rss+xml" title="RSS" href="whats-new.xml">\r\n'
                '<meta property="og:url" content="https://esportly.eu/privacy.html">'
                '<meta property="og:image" content="https://esportly.eu/partage/jeux/valorant.jpg">\r\n'
                '<a href="../jeux/valorant.html" hreflang="fr">fr</a><a href="https://esportly.eu/teams/t1.html">T1</a>\r\n'
                '<script type="application/ld+json">{"item": "https://esportly.eu/fr.html#jeux", "url": "https://esportly.eu/match.html?id=7", '
                '"mainEntityOfPage": "https://esportly.eu/blog/valorant.html", "@id": "https://esportly.eu/teams.html"}</script>\r\n'
                '<url><loc>https://esportly.eu/fr.html</loc><xhtml:link rel="alternate" hreflang="es" href="https://esportly.eu/es.html"/></url>\n')
        wanted = (page.replace("eu/games/valorant.html", "eu/games/valorant").replace("eu/jeux/valorant.html", "eu/jeux/valorant")
                  .replace("eu/privacy.html", "eu/privacy").replace("eu/fr.html", "eu/fr").replace("eu/blog/valorant.html", "eu/blog/valorant")
                  .replace("eu/teams.html", "eu/teams").replace("eu/es.html", "eu/es"))
        self.assertEqual(an.public_urls(page), wanted)
        self.assertEqual(an.public_urls(wanted), wanted)
        self.assertIn('<a href="../jeux/valorant.html" hreflang="fr">', wanted)  # liens de navigation : inchangés
        self.assertIn('<a href="https://esportly.eu/teams/t1.html">', wanted)
        self.assertIn("match.html?id=7", wanted)

    def test_rename_page(self):
        page = ('<link rel="canonical" href="https://esportly.eu/nouveautes">'
                '<link rel="alternate" hreflang="fr" href="https://esportly.eu/nouveautes.html">'
                '<a href="nouveautes.html">fr</a><a href="nouveautes.xml">RSS</a>')
        self.assertEqual(an.rename_page(page, "nouveautes.html", "actualites.html"),
                         '<link rel="canonical" href="https://esportly.eu/actualites">'
                         '<link rel="alternate" hreflang="fr" href="https://esportly.eu/actualites.html">'
                         '<a href="actualites.html">fr</a><a href="nouveautes.xml">RSS</a>')

    def test_pages_news_depuis_un_modele_sans_extension(self):
        for source in (template("en"), an.public_urls(template("en"))):
            page = an.render_page("en", source, "", "", "", home_footer("en"))
            self.assertIn('<link rel="canonical" href="https://esportly.eu/news">', page)
            self.assertIn('hreflang="fr" href="https://esportly.eu/fr/actualites"', page)
            self.assertEqual([url for url in declared_urls(page) if url.endswith(".html")], [])


class Pages(unittest.TestCase):
    def test_page_depuis_le_modele(self):
        page = an.render_page("en", template("en"), "<p>MATCHES</p>", "<p>INFOS</p>", "<script>LD</script>", home_footer("en"))
        self.assertIn('<link rel="canonical" href="https://esportly.eu/news">', page)
        for lang in an.LANGS:
            self.assertIn(f'hreflang="{lang}" href="{an.public_url(an.PAGES[lang])}"', page)
        self.assertIn('hreflang="x-default" href="https://esportly.eu/news"', page)
        self.assertNotIn("rss", page.lower())
        self.assertIn("<title>News and big matches</title>", page)  # sans marque en suffixe (règle du skill titres-seo)
        self.assertIn('content="The matches you can&#x27;t miss', page)
        self.assertIn('<meta property="og:title" content="News and big matches">', page)
        seo = {"/news": {"title": "Esports news: big matches you can't miss, as they happen", "description": "The news."}}
        with_seo = an.render_page("en", template("en"), "<p>MATCHES</p>", "<p>INFOS</p>", "<script>LD</script>", home_footer("en"), None, seo)
        self.assertIn("<title>Esports news: big matches you can&#x27;t miss, as they happen</title>", with_seo)
        self.assertIn('<meta name="description" content="The news.">', with_seo)
        self.assertIn('<meta property="og:title" content="Esports news: big matches you can&#x27;t miss, as they happen">', with_seo)
        self.assertIn("<h1>News and big matches</h1>", with_seo)  # le H1 reste LABELS
        self.assertIn("visite?p=/news&amp;go=testflight", page)
        self.assertNotIn("OLD HERO", page)
        self.assertIn('<div class="kicker">News</div><h1>News and big matches</h1>', page)
        self.assertIn("<!-- matchs-importants --><p>MATCHES</p><!-- /matchs-importants -->", page)
        self.assertIn('<h2 class="jour">Latest news</h2><p>INFOS</p><h2 class="jour">Important matches</h2><!-- matchs-importants -->', page)  # les infos en premier
        self.assertTrue(page.index("<p>INFOS</p>") < page.index("<p>MATCHES</p>"))
        self.assertIn("<!-- /matchs-importants --><script>LD</script></main>", page)  # les données structurées restent à la fin
        self.assertIn(".matchs{", page)
        self.assertIn(".infos{", page)
        fr = an.render_page("fr", template("fr"), "", "", "", home_footer("fr"))
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/actualites">', fr)
        self.assertIn("visite?p=/fr/actualites&amp;", fr)

    def test_filtre_par_jeu(self):
        """Les matchs d'un événement lié à un jeu et les infos d'un jeu portent data-game ; les boutons ne listent que les jeux présents,
        dans l'ordre du site, et rien ne s'affiche avec un seul jeu ; une info sans jeu reste hors du filtre."""
        matches = [{"summary": "Quart 1", "description": "LoL", "url": "https://esportly.eu/match.html?id=1", "slug": "worlds-2026",
                    "start": datetime(2026, 11, 3, 19, 0, tzinfo=UTC)}]
        shown = an.render_matches(matches, "en", {"worlds-2026": "league-of-legends"})
        self.assertIn('<li data-game="league-of-legends"><a href="https://esportly.eu/match.html?id=1"', shown)
        self.assertIn('<li><a href="https://esportly.eu/match.html?id=1"', an.render_matches(matches, "en"))
        general = item("sans-jeu", date="2026-10-30")
        cs = item("cs", date="2026-10-30", game="counter-strike-2")
        infos = an.render_infos([general, cs], "en")
        self.assertIn('<li id="cs" data-game="counter-strike-2">', infos)
        self.assertIn('<li id="sans-jeu"><time', infos)
        names = {"league-of-legends": "League of Legends", "counter-strike-2": "Counter-Strike 2"}
        page = an.render_page("en", template("en"), shown, infos, "", home_footer("en"), names)
        self.assertIn('<nav class="chips" aria-label="Filter by game"><a href="#f-all">All games</a>'
                      '<a href="#f-league-of-legends">League of Legends</a><a href="#f-counter-strike-2">Counter-Strike 2</a></nav>', page)
        self.assertIn('main:has(#f-counter-strike-2:target)', page)
        alone = an.render_page("en", template("en"), "", an.render_infos([cs], "en"), "", home_footer("en"), names)
        self.assertNotIn('class="chips"', alone)

    def test_menu_et_pied_de_page_du_site(self):
        """Une page News a le menu des accueils (la page News marquée, puis Blog) et leur pied de page, adresses lues depuis la racine."""
        page = an.render_page("fr", template("fr"), "", "", "", home_footer("fr"))
        header = re.search(r"<header>.*?</header>", page, re.S).group(0)
        self.assertEqual(header.count('<details class="menu">'), 1)
        self.assertIn('<a href="../fr/actualites.html" aria-current="page">Actualités</a><a href="../fr/blog.html">Blog</a>'
                      '<a class="live" href="../fr/live.html">Live</a>', header)  # la page est dans fr/ : chemins depuis la racine
        self.assertIn('<details class="mega"><summary>Jeux', header)  # le panneau des jeux a remplacé l'ancre
        self.assertIn('<a href="../fr/jeux/valorant.html">', header)
        self.assertIn("visite?p=/fr/actualites&amp;go=testflight", header)
        footer = re.search(r"<footer>.*?</footer>", page, re.S).group(0)
        self.assertIn('<li><a href="../fr/actualites.html">News</a></li><li><a href="../fr/blog.html">Blog</a></li>', footer)
        self.assertIn('<a href="../fr.html#jeux">Games</a>', footer)  # les ancres mènent à l'accueil
        self.assertIn('<li class="fl"><a href="fr/actualites.html" hreflang="fr" lang="fr" aria-current="page">', footer)  # la page équivalente (menu de langue du modèle)
        self.assertIn('<li class="fl"><a href="news.html" hreflang="en" lang="en">', footer)
        self.assertEqual(footer.count('aria-current="page"'), 1)
        self.assertIn("visite?p=/fr/actualites&amp;go=testflight", footer)  # le compteur de visites compte cette page, pas l'accueil
        self.assertIn('href="mailto:contact@example.org"', footer)
        self.assertEqual(page.count("<footer>"), 1)
        self.assertIn(".fgrid{", page)
        self.assertIn("header nav>a[aria-current]", page)
        self.assertEqual(page.count(".fgrid{display:grid"), 1)
        self.assertEqual(an.render_page("fr", page, "", "", "", home_footer("fr")).count(".fgrid{display:grid"), 1)  # refabriquée : rien ne s'ajoute
        english = an.render_page("en", template("en"), "", "", "", home_footer("en"))
        self.assertIn('<a href="./#jeux">Games</a>', english)
        self.assertIn('<a class="brand" href="./">', english)

    def test_modele_ou_accueil_sans_ce_qu_il_faut(self):
        footless = template("en").replace("<footer></footer>", "")
        for source, home, word in ((footless, home_footer("en"), "pied de page"), (template("en"), "<html></html>", "pied de page"),
                                   (re.sub(r"<header>.*?</header>", "", template("en"), flags=re.S), home_footer("en"), "en-tête")):
            with self.subTest(word=word, home=home[:12]), self.assertRaises(an.NewsError) as caught:
                an.render_page("en", source, "", "", "", home)
            self.assertIn(word, caught.exception.problems[0])
            self.assertIn("news.html", caught.exception.problems[0])

    def test_empreinte_csp(self):
        page = an.with_local_times(template("en"))
        digest = base64.b64encode(hashlib.sha256(an.LOCAL_JS.encode("utf-8")).digest()).decode()
        self.assertIn(f"'sha256-{digest}'", re.search(r"script-src ([^;\"]*)", page).group(1))
        self.assertEqual(an.with_local_times(page), page)

    def test_local_js_identique(self):
        with warnings.catch_warnings():  # matchs.py contient un "\;" préexistant qui lève un SyntaxWarning à l'analyse
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse((an.ROOT / ".github" / "scripts" / "matchs.py").read_text(encoding="utf-8"))
        wanted = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "LOCAL_JS"]
        self.assertEqual(wanted, [an.LOCAL_JS])

    def test_adresses_publiees_identiques_dans_matchs(self):
        """matchs.py (script autonome) recopie public_url, public_urls et rename_page : mêmes fonctions, à la virgule près."""
        def functions(name: str) -> dict[str, str]:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse((an.ROOT / ".github" / "scripts" / name).read_bytes().decode("utf-8"))
            return {node.name: ast.dump(node) for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in ("public_url", "public_urls", "rename_page")}
        mine = functions("actualites.py")
        self.assertEqual(len(mine), 3)
        self.assertEqual(functions("matchs.py"), mine)

    def test_update_between_idempotent(self):
        page = "A\r\n<!-- s -->old<!-- /e -->\r\nB\r\n"
        once = an.update_between(page, "<!-- s -->", "<!-- /e -->", "new", "page.html")
        self.assertEqual(once, "A\r\n<!-- s -->new<!-- /e -->\r\nB\r\n")
        self.assertEqual(an.update_between(once, "<!-- s -->", "<!-- /e -->", "new", "page.html"), once)

    def test_marqueurs_absents(self):
        with self.assertRaises(an.NewsError) as caught:
            an.update_between("<html></html>", "<!-- s -->", "<!-- /e -->", "x", "fr.html")
        self.assertIn("fr.html", caught.exception.problems[0])
        self.assertIn("<!-- s -->", caught.exception.problems[0])
        self.assertIsNone(an.extract_between("<html></html>", "<!-- s -->", "<!-- /e -->"))

    def test_extract_between(self):
        self.assertEqual(an.extract_between("a<!-- s -->contenu<!-- /e -->b", "<!-- s -->", "<!-- /e -->"), "contenu")
        self.assertEqual(an.extract_between("a<!-- s --><!-- /e -->b", "<!-- s -->", "<!-- /e -->"), "")

    def test_set_lastmod(self):
        sitemap = ("<urlset>\r\n"
                   "<url><loc>https://esportly.eu/news.html</loc><lastmod>2026-10-14</lastmod><changefreq>daily</changefreq></url>\r\n"
                   "<url><loc>https://esportly.eu/actualites.html</loc>\r\n  <lastmod>2026-10-14</lastmod></url>\r\n</urlset>\r\n")
        once = an.set_lastmod(sitemap, "https://esportly.eu/news.html", "2026-10-28")
        self.assertEqual(once, sitemap.replace("news.html</loc><lastmod>2026-10-14", "news.html</loc><lastmod>2026-10-28"))
        twice = an.set_lastmod(once, "https://esportly.eu/actualites.html", "2026-10-29")
        self.assertIn("<lastmod>2026-10-29</lastmod></url>\r\n</urlset>", twice)
        self.assertIn("news.html</loc><lastmod>2026-10-28", twice)
        with self.assertRaises(an.NewsError):
            an.set_lastmod(sitemap, "https://esportly.eu/noticias.html", "2026-10-28")


def ics(*events) -> str:
    """Un calendrier d'événement à partir de (titre, début UTC)."""
    body = "".join(f"BEGIN:VEVENT\r\nDTSTART:{start:%Y%m%dT%H%M%SZ}\r\nSUMMARY:{summary}\r\nDESCRIPTION:League of Legends · Worlds · 2026\r\n"
                   f"URL:https://esportly.eu/match.html?id={n}\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\n" for n, (summary, start) in enumerate(events, 1))
    return f"BEGIN:VCALENDAR\r\n{body}END:VCALENDAR\r\n"


CALENDARS = {"worlds-2026": ics(("Quarterfinal 1: TBD vs TBD", datetime(2026, 11, 3, 19, 0, tzinfo=UTC)),
                                ("Équipe A – Équipe B", datetime(2026, 11, 5, 19, 0, tzinfo=UTC)),
                                ("Équipe C – Équipe D", datetime(2026, 10, 31, 19, 0, tzinfo=UTC))),
             "vct-champions-2026": ics(("Semifinal 1: TBD vs TBD", datetime(2026, 11, 7, 19, 0, tzinfo=UTC)),
                                       ("Équipe E – Équipe F", datetime(2026, 11, 6, 19, 0, tzinfo=UTC)))}
MARKERS = ("<!-- matchs-importants -->", "<!-- /matchs-importants -->")
HOME_MARKERS = ("<!-- news-accueil -->", "<!-- /news-accueil -->")
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def fake_fetch(failing=()):
    def fetch(url: str) -> str:
        slug = url.rsplit("/", 1)[1][:-4]
        if slug in failing:
            raise OSError("calendrier indisponible")
        return CALENDARS[slug]
    return fetch


class Generation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.news = {"events": {"worlds-2026": {"knockout_from": "2026-11-03"}, "vct-champions-2026": {"knockout_from": None}},
                     "items": [item("info-a", date="2026-10-30", fr=text("Titre A fr"), en=text("Title A en"))]}
        for slug in self.news["events"]:
            self.write(an.page_for(slug, "en"), "<html></html>\r\n")  # la page anglaise de l'événement (worlds-2026-en.html)
        for lang in an.LANGS:
            self.write(an.TEMPLATES[lang], template(lang))
            self.write(an.HOMES[lang], f'<html lang="{lang}">\r\n<body>\r\n{HOME_MARKERS[0]}{HOME_MARKERS[1]}\r\n<main></main>\r\n{home_footer(lang)}\r\n</body>\r\n</html>\r\n')
        entries = "".join(f"<url><loc>{an.public_url(name)}</loc><lastmod>2026-10-14</lastmod></url>\r\n" for name in an.PAGES.values())
        self.write("sitemap.xml", f"<urlset>\r\n{entries}</urlset>\r\n")
        self.save_news()

    def write(self, name: str, content: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")

    def read(self, name: str) -> str:
        return (self.root / name).read_bytes().decode("utf-8")

    def save_news(self) -> None:
        self.write("news/news.json", json.dumps(self.news, ensure_ascii=False))

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def run_main(self, *argv, fetch=None, now=NOW) -> tuple[int, str, str]:
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = an.main(list(argv), root=self.root, now=now, fetch=fetch or fake_fetch())
        return code, out.getvalue(), err.getvalue()

    def apply(self, now=NOW, fetch=None) -> dict[str, str]:
        with contextlib.redirect_stdout(io.StringIO()):
            changes = an.generate(self.root, now, fetch or fake_fetch())
        for name, content in changes.items():
            self.write(name, content)
        return changes

    def test_generation_complete(self):
        changes = self.apply()
        self.assertEqual(set(changes), set(an.PAGES.values()) | set(an.HOMES.values()) | {"sitemap.xml"})
        english, french = changes["news.html"], changes["fr/actualites.html"]
        for page in (english, french):
            self.assertIn("Quarterfinal 1: TBD vs TBD", page)   # titre de phase, avant knockout_from
            self.assertIn("Équipe A – Équipe B", page)           # après knockout_from
            self.assertIn("Semifinal 1: TBD vs TBD", page)       # autre événement, titre de phase
            self.assertNotIn("Équipe C – Équipe D", page)        # passé, hors fenêtre
            self.assertNotIn("Équipe E – Équipe F", page)        # événement sans knockout_from ni phase
        self.assertIn("Title A en", english)
        self.assertIn("Titre A fr", french)
        home = changes["index.html"]
        self.assertIn('<section class="block news" id="news">', home)
        self.assertIn("Title A en", home)
        self.assertIn("Quarterfinal 1: TBD vs TBD", home)        # le prochain match important

    def test_adresses_declarees_sans_extension(self):
        changes = self.apply()
        canonicals = set()
        for name in an.PAGES.values():
            # seule exception : les fiches de match (match.html?id=…), dont l'app iOS lit la forme
            self.assertEqual([url for url in declared_urls(changes[name]) if url.endswith(".html")], [], name)
            self.assertTrue(all(url.startswith("https://esportly.eu/match.html?id=") for url in declared_urls(changes[name]) if ".html" in url))
            canonicals.add(re.search(r'<link rel="canonical" href="([^"]*)"', changes[name]).group(1))
        self.assertEqual(set(re.findall(r"<loc>([^<]*)</loc>", changes["sitemap.xml"])), canonicals)

    def test_idempotence(self):
        self.apply()
        after_first = self.snapshot()
        self.assertEqual(self.apply(), {})
        self.assertEqual(self.snapshot(), after_first)

    def test_essai_n_ecrit_rien(self):
        before = self.snapshot()
        code, out, _ = self.run_main("--essai")
        self.assertEqual(code, 0)
        self.assertIn("11 fichier(s) à changer.", out)
        self.assertEqual(self.snapshot(), before)
        code, out, _ = self.run_main()
        self.assertIn("11 fichier(s) changé(s).", out)
        self.assertNotEqual(self.snapshot(), before)

    def test_verifier(self):
        before = self.snapshot()
        code, out, _ = self.run_main("--verifier")
        self.assertEqual((code, "news/news.json : valide" in out), (0, True))
        self.news["items"][0]["id"] = "Mauvais ID"
        self.save_news()
        before = self.snapshot()
        code, _, err = self.run_main("--verifier")
        self.assertEqual(code, 1)
        self.assertIn("Mauvais ID", err)
        self.assertEqual(self.snapshot(), before)

    def test_une_erreur_n_ecrit_rien(self):
        self.news["items"][0]["until"] = "2026-01-01"
        self.save_news()
        before = self.snapshot()
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("avant date", err)
        self.assertEqual(self.snapshot(), before)
        self.news["items"][0].pop("until")
        self.save_news()
        self.write("es.html", "<html><body>pas de marqueurs</body></html>\r\n")
        before = self.snapshot()
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("es.html", err)
        self.assertEqual(self.snapshot(), before)

    def test_un_calendrier_en_panne(self):
        self.apply()
        kept_page = an.extract_between(self.read("fr/actualites.html"), *MARKERS)
        kept_home = an.extract_between(self.read("fr.html"), "<!-- prochain-match -->", "<!-- /prochain-match -->")
        self.assertIn("Quarterfinal 1", kept_page)
        self.news["items"].append(item("info-b", date="2026-10-31", fr=text("Titre B fr"), en=text("Title B en")))
        self.save_news()
        changes = self.apply(fetch=fake_fetch(failing=("vct-champions-2026",)))
        self.assertIn("Titre B fr", changes["fr/actualites.html"])
        self.assertEqual(an.extract_between(changes["fr/actualites.html"], *MARKERS), kept_page)
        self.assertEqual(an.extract_between(changes["fr.html"], "<!-- prochain-match -->", "<!-- /prochain-match -->"), kept_home)

    def test_lastmod_du_jour_de_paris(self):
        late = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)  # 00 h 30 le 2 novembre à Paris
        changes = self.apply(now=late)
        for name in an.PAGES.values():
            self.assertIn(f"<loc>{an.public_url(name)}</loc><lastmod>2026-11-02</lastmod>", changes["sitemap.xml"])
        self.assertEqual(self.apply(now=datetime(2026, 11, 2, 23, 30, tzinfo=UTC)).get("sitemap.xml"), None)

    def test_fins_de_ligne(self):
        changes = self.apply()
        for name, content in changes.items():
            self.assertIsNone(re.search(r"(?<!\r)\n", content), name)


SCRIPT = Path(an.__file__).resolve()
WORKFLOW = SCRIPT.parents[2] / ".github" / "workflows" / "matchs.yml"
# Durée mesurée du reste du job (réveil des calendriers avec ses 240 s d'attente, checkout, matchs.py) : environ 6 à 6,5 minutes, arrondie à 7.
BASELINE_MINUTES = 7


class Environnement(unittest.TestCase):
    def test_verifier_sans_base_des_fuseaux(self):
        # `--verifier` ne lit que news/news.json : il doit marcher là où zoneinfo ne trouve pas Europe/Paris (Windows sans tzdata).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "scripts").mkdir(parents=True)
            (root / "news").mkdir()
            (root / "tz").mkdir()
            script = root / ".github" / "scripts" / SCRIPT.name
            shutil.copy(SCRIPT, script)
            shutil.copy(SCRIPT.with_name("site_chrome.py"), script.with_name("site_chrome.py"))  # le module commun, au même endroit que dans le dépôt
            (root / "news" / "news.json").write_text('{"events": {}, "items": []}', encoding="utf-8")
            env = {**os.environ, "PYTHONTZPATH": str(root / "tz"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
            done = subprocess.run([sys.executable, str(script), "--verifier"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("valide", done.stdout)

    def test_etape_du_job_bornee_dans_le_temps(self):
        # Une source qui ne répond pas (calendrier, vidéos, flux du blog) ne doit pas retenir l'envoi des pages de matchs : les trois étapes
        # facultatives sont bornées, ne bloquent pas, et passent entre les matchs et l'envoi, dans cet ordre. Mais si le job lui-même atteint sa
        # limite, GitHub l'annule en entier (`continue-on-error` n'y change rien) et l'envoi ne part pas : la limite du job doit donc laisser la
        # place du reste du job (BASELINE_MINUTES) plus celle des trois étapes, chacune pouvant aller jusqu'à son propre timeout.
        optional = ("Mise à jour des news", "Top plays du moment", "Mise à jour du blog")
        order = ("Mise à jour des pages",) + optional + ("Envoi si quelque chose a changé",)
        text = WORKFLOW.read_text(encoding="utf-8")
        limits = []
        for name in optional:
            with self.subTest(etape=name):
                step = re.search(r"^ *- name: " + re.escape(name) + r"[ \t]*\r?\n((?:        .*\r?\n)+)", text, re.MULTILINE)
                self.assertIsNotNone(step, f"étape « {name} » introuvable")
                self.assertIn("continue-on-error: true", step.group(1))
                limit = re.search(r"timeout-minutes: (\d+)", step.group(1))
                self.assertIsNotNone(limit, "l'étape n'a pas de timeout-minutes")
                self.assertLessEqual(int(limit.group(1)), 3)
                limits.append(int(limit.group(1)))
                self.assertNotIn("--sources", step.group(1), "blog.py --sources est une vérification manuelle, jamais dans le job")
        names = re.findall(r"^ *- name: (.*?)[ \t]*\r?$", text, re.MULTILINE)
        self.assertEqual([name for name in names if name in order], list(order), "ordre des étapes du job")
        job = re.search(r"^    timeout-minutes: (\d+)[ \t]*\r?$", text, re.MULTILINE)  # quatre espaces : celui du job, pas celui d'une étape
        self.assertIsNotNone(job, "le job n'a pas de timeout-minutes")
        self.assertGreaterEqual(int(job.group(1)), BASELINE_MINUTES + sum(limits),
                                f"timeout du job ({job.group(1)} min) < reste du job ({BASELINE_MINUTES}) + étapes facultatives ({limits})")

    def test_pas_d_api_posterieure_a_python_312(self):
        # Le job du matin tourne en Python 3.12 : `Path.read_text(newline=)` n'existe que depuis 3.13 (TypeError, masqué par
        # `continue-on-error`). Le même texte, mêmes fins de ligne : `path.read_bytes().decode("utf-8")`.
        found = []
        for path in sorted(SCRIPT.parent.glob("*.py")):
            with warnings.catch_warnings():  # matchs.py contient un "\;" préexistant : SyntaxWarning en 3.12, DeprecationWarning avant
                warnings.simplefilter("ignore")
                tree = ast.parse(path.read_bytes(), filename=str(path))
            lines = sorted(node.lineno for node in ast.walk(tree)
                           if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "read_text"
                           and any(keyword.arg == "newline" for keyword in node.keywords))
            found.extend(f"{path.name}:{line}" for line in lines)
        self.assertEqual(found, [], "read_text(newline=) exige Python 3.13 : " + ", ".join(found))


if __name__ == "__main__":
    unittest.main()
