"""Tests de la page Live (live.py) : `py -3.13 -m unittest discover -s .github/scripts -p "test_*.py"` depuis la racine du site."""
from __future__ import annotations

import base64
import hashlib
import html
import re
import unittest
from datetime import datetime, timedelta, timezone

import actualites as an
import live
import site_chrome
from test_actualites import home_footer, template

NOW = datetime(2026, 11, 5, 5, 15, tzinfo=timezone.utc)  # 6 h 15 à Paris, l'heure de fabrication
T = {"fr": dict(days=["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
                months=["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
                tz="heure de Paris", updated="Mis à jour le"),
     "en": dict(days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                months=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
                tz="Paris time", updated="Updated on")}
NAMES = {"en": {"counter-strike-2": "Counter-Strike 2", "league-of-legends": "League of Legends", "valorant": "Valorant"},
         "fr": {"counter-strike-2": "Counter-Strike 2", "league-of-legends": "League of Legends", "valorant": "Valorant"}}


def match(summary: str, start: datetime, hours: float = 2, game: str = "Counter-Strike 2", uid: str | None = None) -> dict:
    return {"UID": uid or f"{summary}@test", "SUMMARY": summary, "DESCRIPTION": f"{game} · Grande finale · 2026",
            "URL": f"https://esportly.eu/match.html?id={abs(hash(summary)) % 1000}", "start": start, "end": start + timedelta(hours=hours)}


class Labels(unittest.TestCase):
    def test_complets_et_sans_balise(self):
        keys = set(live.LABELS["fr"])
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(set(live.LABELS[lang]), keys)
                for key, text in live.LABELS[lang].items():
                    self.assertFalse(re.search(r'[<>&"]', text), (key, text))
                self.assertLessEqual(len(live.LABELS[lang]["title"]), 63)  # <title> à défaut de seo/titres.json
                self.assertLessEqual(len(live.LABELS[lang]["meta"]), 155)  # description SEO
                for key in ("one", "many"):
                    self.assertIn("{n}", live.LABELS[lang][key])
                self.assertIn("{h}", live.LABELS[lang]["next"])
        self.assertEqual(set(live.PAGES), set(an.LANGS))
        self.assertEqual(live.PAGES, site_chrome.LIVE_PAGES)

    def test_script_et_empreinte(self):
        self.assertEqual(live.HASH, base64.b64encode(hashlib.sha256(live.JS.encode("utf-8")).digest()).decode())
        self.assertNotIn("</script", live.JS)
        for word in ("live-now", "data-start", "data-end", "data-state", "data-final", "data-grp", "l-live", "l-done", "Europe/Paris", "6e4"):
            self.assertIn(word, live.JS)
        for text in live.LABELS["fr"].values():  # le script ne porte aucun texte d'une langue : il les lit dans #live-now
            self.assertNotIn(text, live.JS)


class Rangement(unittest.TestCase):
    """L'ordre de la page : en direct tout en haut, à venir au milieu (par jour), terminés tout en bas, rangés par le script."""

    def render(self, finals=None) -> str:
        events = [match("Vitality – G2", NOW + timedelta(hours=4)), match("Falcons – Spirit", NOW + timedelta(hours=27))]
        return live.render_main("fr", events, NOW, T["fr"], NAMES, finals)

    def test_sections_cachees_au_depart(self):
        main = self.render()
        for lang in an.LANGS:
            self.assertTrue(live.LABELS[lang]["h_done"])
        up, down = main.index('id="l-live"'), main.index('id="l-done"')
        self.assertLess(up, main.index("<h2 class=\"jour\">Aujourd'hui</h2>"))  # les directs avant les jours à venir
        self.assertGreater(down, main.index('<h2 class="jour">Demain</h2>'))  # les terminés après
        self.assertIn('<h2 class="jour" hidden>En direct</h2><ul class="matchs" id="l-live" data-grp hidden></ul>', main)
        self.assertIn('<h2 class="jour" hidden>Matchs terminés</h2><ul class="matchs" id="l-done" data-grp hidden></ul>', main)
        self.assertEqual(main.count("data-grp"), 4)  # directs, deux jours, terminés
        self.assertNotIn("data-final", main)
        self.assertEqual(re.findall(r'<h2 class="jour">([^<]*)</h2>', main), ["Aujourd'hui", "Demain"])  # sans les titres cachés

    def test_fin_notee(self):
        events = [match("Vitality – G2", NOW + timedelta(hours=4))]
        mid = live.match_id(events[0])
        main = live.render_main("fr", events, NOW, T["fr"], NAMES, {mid: {"vu": "2026-11-05T09:00:00+00:00", "equipes": ["a", "b"], "score": [2, 1]}})
        self.assertIn('data-final="2026-11-05T09:00:00+00:00"', re.search(r"<li data-start[^>]*>", main).group(0))
        self.assertNotIn("2 – 1", main)  # la liste Live ne montre jamais le score (pas de spoiler)
        self.assertEqual(main.count("data-final"), 1)

    def test_libelle_termine_dans_les_5_langues(self):
        for lang, word in (("fr", "Terminé"), ("en", "Finished"), ("es", "Terminado"), ("de", "Beendet"), ("pt-BR", "Encerrada")):
            self.assertEqual(live.LABELS[lang]["done"], word)
            self.assertIn(f' data-done="{word}"', live.render_main(lang, [], NOW, {**T["fr"], "tz": "x"}, NAMES))

    def test_script_range_selon_l_etat(self):
        for word in ("insertBefore", "appendChild", "hasAttribute('data-final')", "hidden"):
            self.assertIn(word, live.JS)
        self.assertIn(".matchs[hidden]{display:none}", live.STYLE)

    def test_libelle_des_etats_lu_avant_le_compte(self):
        # data-live de #live-now est d'abord le libellé « En direct », puis le nombre de directs : le script copie les libellés au départ
        self.assertIn("S={live:T.live,done:T.done,soon:T.soon}", live.JS)
        self.assertIn("x.textContent=S[k]", live.JS)
        self.assertNotIn("T[k]", live.JS)


class Selection(unittest.TestCase):
    def test_fenetre_tri_et_doublons(self):
        early, late = match("A – B", NOW - timedelta(hours=7)), match("C – D", NOW + timedelta(hours=31))
        night, noon, tomorrow = match("E – F", NOW - timedelta(hours=5)), match("G – H", NOW + timedelta(hours=6)), match("I – J", NOW + timedelta(hours=29))
        twin = dict(noon, SUMMARY="G – H (bis)")  # même UID : le même match vu depuis deux calendriers
        chosen = live.select([late, tomorrow, noon, twin, night, early], NOW)
        self.assertEqual([e["SUMMARY"] for e in chosen], ["E – F", "G – H", "I – J"])

    def test_jeu(self):
        self.assertEqual(live.game_slug("Counter-Strike 2 · PGL Major · 2026", NAMES["en"]), "counter-strike-2")
        self.assertEqual(live.game_slug("valorant · VCT", NAMES["en"]), "valorant")
        self.assertEqual(live.game_slug("Overwatch · OCS", {**NAMES["en"], "overwatch-2": "Overwatch 2", "wild-rift": "League of Legends: Wild Rift"}), "overwatch-2")
        self.assertEqual(live.game_slug("League of Legends · Worlds", {**NAMES["en"], "wild-rift": "League of Legends: Wild Rift"}), "league-of-legends")
        self.assertIsNone(live.game_slug("Apex Legends · ALGS", NAMES["en"]))
        self.assertIsNone(live.game_slug("", NAMES["en"]))


class Main(unittest.TestCase):
    def events(self) -> list[dict]:
        return [match("Vitality – G2", NOW + timedelta(hours=4)), match("T1 – GEN", NOW + timedelta(hours=8), game="League of Legends"),
                match("Falcons – Spirit", NOW + timedelta(hours=27)), match("X <&> Y", NOW + timedelta(hours=1), game="Apex Legends")]

    def test_matchs_du_jour(self):
        main = live.render_main("fr", live.select(self.events(), NOW), NOW, T["fr"], NAMES)
        self.assertIn('<div class="kicker">En direct</div><h1>Matchs e-sport en direct aujourd\'hui</h1>', main)
        self.assertIn("visite?p=/fr/live&amp;go=testflight", main)
        status = re.search(r'<p class="live-now" id="live-now"([^>]*)>([^<]*)</p>', main)
        self.assertEqual(status.group(2), "Heure de Paris")  # sans JavaScript
        for key in ("live", "done", "soon", "one", "many", "none", "next"):
            self.assertIn(f' data-{key}="{html.escape(live.LABELS["fr"][key])}"', status.group(1))
        days = re.findall(r'<h2 class="jour">([^<]*)</h2>', main)
        self.assertEqual(days, ["Aujourd'hui", "Demain"])
        items = re.findall(r"<li([^>]*)><a href=\"([^\"]*)\">(.*?)</a></li>", main)
        self.assertEqual(len(items), 4)
        for _, href, _ in items:  # chaque match mène à sa page (live_match.py), pas à match.html, la page de renvoi vers l'app
            self.assertRegex(href, r"^\.\./fr/live/(?:\d{1,4}|[a-z0-9-]+-vs-[a-z0-9-]+-\d{4}-\d{2}-\d{2})\.html$")  # vu de fr/live.html : les équipes et la date
        self.assertEqual(live.match_href("fr", match("Z – Y", NOW)), f"../fr/live/{live.match_page(match('Z – Y', NOW))}.html")
        self.assertRegex(live.match_href("fr", match("Z – Y", NOW)), r"z-vs-y-\d{4}-\d{2}-\d{2}")  # les équipes et la date
        self.assertNotIn('href="https://esportly.eu/match.html', main)  # (les données structurées gardent l'adresse du calendrier)
        self.assertEqual([re.search(r"<b>(.*?)</b>", body).group(1) for _, _, body in items],
                         ["X &lt;&amp;&gt; Y", "Vitality – G2", "T1 – GEN", "Falcons – Spirit"])
        self.assertIn(f' data-start="{(NOW + timedelta(hours=4)).isoformat()}" data-end="{(NOW + timedelta(hours=6)).isoformat()}" data-game="counter-strike-2"', items[1][0])
        self.assertNotIn("data-game", items[0][0])  # Apex Legends : jeu inconnu du site, pas de filtre
        self.assertTrue(items[0][2].startswith('<span class="etat"></span><time datetime='))
        # Le jour est écrit en toutes lettres à côté de l'heure : un match joué à l'autre bout du monde tombe à 5 h du matin
        # chez nous, et l'heure seule, sous un titre « Aujourd'hui », a tout l'air d'une erreur de la veille.
        self.assertIn(">Jeudi 5 novembre · 07:15</time>", items[0][2])  # jour et heure de Paris
        self.assertIn('<nav class="chips" aria-label="Filtrer par jeu">', main)  # deux jeux connus : le filtre
        self.assertIn('href="#f-counter-strike-2">Counter-Strike 2</a>', main)
        self.assertNotIn("#f-valorant", main)
        self.assertIn('<p class="live-note">', main)
        self.assertIn('<p class="maj">Mis à jour le 5 novembre 2026 · heure de Paris</p>', main)
        self.assertEqual(main.count('"@type": "SportsEvent"'), 4)

    def test_sans_match(self):
        main = live.render_main("en", [], NOW, T["en"], NAMES)
        self.assertIn("<p>No match today.</p>", main)
        self.assertNotIn("<ul", main)
        self.assertNotIn('class="chips"', main)
        self.assertIn('id="live-now"', main)
        self.assertIn('<script type="application/ld+json">[]</script>', main)

    def test_un_seul_jeu_sans_filtre(self):
        main = live.render_main("en", [match("A – B", NOW + timedelta(hours=2))], NOW, T["en"], NAMES)
        self.assertNotIn('class="chips"', main)
        self.assertIn('data-game="counter-strike-2"', main)


class Page(unittest.TestCase):
    def test_page_complete(self):
        model = template("fr").replace('<meta property="og:title"', '<meta property="og:image" content="https://esportly.eu/partage/old.jpg"><meta property="og:title"')
        page = live.render_page("fr", model, [match("A – B", NOW + timedelta(hours=2))], NOW, T["fr"], home_footer("fr"), NAMES)
        self.assertIn("<title>Matchs e-sport en direct aujourd&#x27;hui</title>", page)  # sans marque en suffixe
        self.assertIn(f'<meta name="description" content="{html.escape(live.LABELS["fr"]["meta"])}">', page)
        self.assertIn('<link rel="canonical" href="https://esportly.eu/fr/live">', page)
        self.assertIn('<link rel="alternate" hreflang="en" href="https://esportly.eu/live">', page)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://esportly.eu/live">', page)
        self.assertIn('<meta property="og:image" content="https://esportly.eu/partage/semaine-fr.jpg">', page)
        self.assertNotIn("application/rss+xml", page)
        self.assertIn('<a href="../fr/actualites.html">Actualités</a><a href="../fr/blog.html">Blog</a><a class="live" href="../fr/live.html" aria-current="page">Live</a>', page)
        self.assertIn('href="live.html" hreflang="en"', page)  # le menu de langue mène aux pages Live
        self.assertIn(f"<script>{live.JS}</script>", page)
        self.assertIn(f"'sha256-{live.HASH}'", re.search(r"script-src[^;\"]*", page).group(0))
        self.assertIn(f"'sha256-{site_chrome.MENU_HASH}'", page)
        self.assertEqual(page.count(".live-now{"), 1)
        self.assertEqual(page.count(".matchs{"), 1)
        self.assertIn("visite?p=/fr/live&amp;go=testflight", page)
        again = live.render_page("fr", page, [match("A – B", NOW + timedelta(hours=2))], NOW, T["fr"], home_footer("fr"), NAMES)
        self.assertEqual(again, page)  # refabriquée depuis elle-même : identique

    def test_anglais(self):
        page = live.render_page("en", template("en"), [], NOW, T["en"], home_footer("en"), NAMES)
        self.assertIn("<title>Live esports matches today</title>", page)
        seo = {"/live": {"title": "Live esports matches today: who is playing now, Paris time", "description": "Today's matches."}}
        page = live.render_page("en", template("en"), [], NOW, T["en"], home_footer("en"), NAMES, seo)
        self.assertIn("<title>Live esports matches today: who is playing now, Paris time</title>", page)
        self.assertIn('<meta name="description" content="Today&#x27;s matches.">', page)
        self.assertIn('<meta property="og:title" content="Live esports matches today: who is playing now, Paris time">', page)
        self.assertIn("<h1>Live esports matches today</h1>", page)
        self.assertIn('<a class="live" href="live.html" aria-current="page">Live</a>', page)
        self.assertIn('<a href="./#jeux">Games</a>', page)

    def test_modele_sans_en_tete(self):
        with self.assertRaises(site_chrome.ChromeError):
            live.render_page("en", re.sub(r"<header>.*?</header>", "", template("en"), flags=re.S), [], NOW, T["en"], home_footer("en"), NAMES)


if __name__ == "__main__":
    unittest.main()
