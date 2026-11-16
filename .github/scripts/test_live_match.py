"""Tests de live_match.py : la page d'un match de la page Live, dans les 5 langues, fabriquée dans la page du jeu du site."""
from __future__ import annotations

import html
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import actualites as an
import blog
import live
import live_match
import site_chrome

REAL = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 5, 5, 15, tzinfo=timezone.utc)
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
T = {lang: dict(days=DAYS, months=MONTHS, tz="heure de Paris", updated="Mis à jour le") for lang in an.LANGS}
HAVE_SITE = (REAL / "fr.html").is_file() and (REAL / "fr" / "jeux" / "valorant.html").is_file()
UP = {lang: "../" if lang == "en" else "../../" for lang in an.LANGS}  # une page de match est dans live/ ou <langue>/live/


def event(summary: str = "Vitality – G2", description: str = "Valorant · VCT Champions · 2026", mid: str | None = "1713096", hours: int = 4) -> dict:
    url = f"https://esportly.eu/match.html?id={mid}" if mid else "https://esportly.eu/"
    return {"UID": f"{summary}@test", "SUMMARY": summary, "DESCRIPTION": description, "URL": url,
            "start": NOW + timedelta(hours=hours), "end": NOW + timedelta(hours=hours + 2)}


def names() -> dict[str, dict[str, str]]:
    return site_chrome.read_game_names(REAL)


def render(lang: str = "fr", ev: dict | None = None, links: dict | None = None, seo: dict | None = None, final: dict | None = None,
           video: dict | None = None) -> str:
    ev, game_names = ev or event(), names()
    model = (REAL / live_match.template_file(lang, ev, game_names["en"])).read_text(encoding="utf-8")
    home = (REAL / ("index.html" if lang == "en" else an.HOMES[lang])).read_text(encoding="utf-8")
    return live_match.render_page(lang, model, ev, T[lang], home, game_names, links, seo, final, video)


def main_of(page: str) -> str:
    return re.search(r"<main class=\"wrap\">(.*?)</main>", page, re.S).group(1)

def name_of(ev: dict | None = None) -> str:
    """L'adresse d'une page de match : les équipes et la date, le numéro seulement quand le titre ne se coupe pas en deux."""
    return live.match_page(ev or event())


VS, VS2 = name_of(), name_of(event("Falcons – Spirit", mid="1713097"))


class Textes(unittest.TestCase):
    def test_complets_et_sans_balise(self):
        keys = set(live_match.TEXTS["fr"])
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(set(live_match.TEXTS[lang]), keys)
                self.assertEqual(len(live_match.TEXTS[lang]["follow"]), 4)
                for key, value in live_match.TEXTS[lang].items():
                    for text in (value if key == "follow" else [value]):
                        for part in (text if isinstance(text, tuple) else [text]):
                            self.assertFalse(re.search(r'[<>&"]', part), (key, part))
                for key in ("title", "meta"):
                    self.assertIn("{match}", live_match.TEXTS[lang][key])
                for key in ("lead", "meta"):
                    self.assertIn("{day}", live_match.TEXTS[lang][key])
                    self.assertIn("{hour}", live_match.TEXTS[lang][key])
                for key in ("game", "guide"):
                    self.assertIn("{game}", live_match.TEXTS[lang][key])

    def test_dossiers_et_equipes(self):
        self.assertEqual(live_match.DIRS, {"en": "live", "fr": "fr/live", "es": "es/live", "de": "de/live", "pt-BR": "pt/live"})
        self.assertEqual(live_match.teams_of("Vitality – G2"), ["Vitality", "G2"])
        self.assertEqual(live_match.teams_of("Vitality - G2"), ["Vitality", "G2"])
        self.assertEqual(live_match.teams_of("Vitality"), [])
        self.assertEqual(live_match.teams_of("A – B – C"), [])
        self.assertEqual(live_match.teams_of("Karmine Corp – Movistar KOI"), ["Karmine Corp", "Movistar KOI"])


class Liens(unittest.TestCase):
    def test_numero_et_adresse_depuis_la_page_live(self):
        self.assertEqual(live.match_id(event(mid="1713096")), "1713096")
        self.assertIsNone(live.match_id(event(mid=None)))
        self.assertEqual(live.match_id({"URL": "https://esportly.eu/match.html?defi=1&id=42&ami=x"}), "42")
        self.assertIsNone(live.match_id({"URL": "https://esportly.eu/match.html?id=abc"}))
        self.assertEqual(live.match_href("fr", event()), f"../fr/live/{VS}.html")  # vu de fr/live.html
        self.assertEqual(live.match_href("en", event()), f"live/{VS}.html")
        self.assertEqual(live.match_href("pt-BR", event()), f"../pt/live/{VS}.html")
        self.assertEqual(live.match_href("fr", event(mid=None)), "https://esportly.eu/")  # sans numéro : l'adresse du calendrier

    def test_competition_et_evenement(self):
        events = [("Worlds 2026", "worlds-2026.html"), ("VCT Champions 2026", "vct-champions-2026.html"), ("ESL Pro League", "esl-pro-league.html")]
        self.assertEqual(live_match.event_link("League of Legends · Worlds · 2026", events), ("Worlds 2026", "worlds-2026.html"))
        self.assertEqual(live_match.event_link("Valorant · VCT Champions · 2026", events), ("VCT Champions 2026", "vct-champions-2026.html"))
        self.assertEqual(live_match.event_link("Counter-Strike 2 · ESL Pro League · Season 24", events), ("ESL Pro League", "esl-pro-league.html"))
        self.assertIsNone(live_match.event_link("Dota 2", events))
        self.assertIsNone(live_match.event_link("Overwatch · OCS · Korea Stage 3 2026", events))
        self.assertIsNone(live_match.event_link("Valorant · · 2026", events))

    @unittest.skipUnless(HAVE_SITE, "pages du site absentes")
    def test_fiches_d_equipes(self):
        fr, en, es = (live_match.team_pages(REAL, lang) for lang in ("fr", "en", "es"))
        self.assertEqual(fr["t1"], "../../fr/equipes/t1.html")
        self.assertEqual(en["t1"], "../teams/t1.html")
        self.assertEqual(es["t1"], "../../teams/t1.html")  # les autres langues n'ont que la fiche anglaise
        for href in fr.values():
            self.assertTrue((REAL / re.sub(r"^(\.\./)+", "", href)).is_file(), href)


@unittest.skipUnless(HAVE_SITE, "pages du site absentes")
class Page(unittest.TestCase):
    def test_page_complete(self):
        links = {"teams": {"vitality": "../../fr/equipes/team-vitality.html"}, "event": ("VCT Champions 2026", "../../fr/vct-champions-2026.html"),
                 "week": "../../fr/matchs-de-la-semaine.html", "guide": "../../fr/blog/valorant.html"}
        page = render("fr", links=links)
        main = main_of(page)
        title = html.escape("Vitality – G2 : horaire et comment suivre le match")
        self.assertIn(f"<title>{title}</title>", page)
        self.assertIn('<meta name="robots" content="noindex, follow">', page)
        self.assertEqual(page.count('name="robots"'), 1)
        self.assertIn(f'<link rel="canonical" href="https://esportly.eu/fr/live/{VS}">', page)
        self.assertIn(f'<link rel="alternate" hreflang="en" href="https://esportly.eu/live/{VS}">', page)
        self.assertIn(f'<link rel="alternate" hreflang="pt-BR" href="https://esportly.eu/pt/live/{VS}">', page)
        self.assertIn(f'<link rel="alternate" hreflang="x-default" href="https://esportly.eu/live/{VS}">', page)
        self.assertNotIn("/jeux/valorant", " ".join(re.findall(r'<link rel="(?:canonical|alternate)"[^>]*>', page)))  # plus d'adresse de la page du jeu
        self.assertIn('<a class="live" href="../../fr/live.html" aria-current="page">Live</a>', page)
        self.assertIn(f'href="../../live/{VS}.html" hreflang="en"', page)  # le menu de langue mène aux pages du match
        self.assertIn(f"visite?p=/fr/live/{VS}&amp;go=testflight", main)
        self.assertIn('<div class="kicker">Valorant · VCT Champions · 2026</div><h1>Vitality – G2</h1>', main)
        self.assertIn('<p class="lead">Coup d&#x27;envoi jeudi 5 novembre à 10:15, heure de Paris.</p>', main)
        self.assertIn('<li data-start="2026-11-05T09:15:00+00:00" data-end="2026-11-05T11:15:00+00:00" data-game="valorant">', main)
        self.assertIn(">jeudi 5 novembre, 10:15</time>", main)  # heure de Paris (UTC+1 en novembre)
        self.assertIn('<span class="etat"></span>', main)
        self.assertIn('id="live-now" hidden data-live="En direct"', main)
        self.assertIn('<a href="../../fr/equipes/team-vitality.html">fiche et prochains matchs</a>', main)
        self.assertNotIn("G2</b> ·", main)  # G2 n'a pas de fiche dans `links` : pas de lien
        for href in ("../../fr/jeux/valorant.html", "../../fr/blog/valorant.html", "../../fr/vct-champions-2026.html",
                     "../../fr/matchs-de-la-semaine.html", "../../fr/live.html"):
            self.assertIn(f'<a href="{href}">', main)
        self.assertIn("Guide : Valorant", main)
        self.assertIn('<script type="application/ld+json">[{"@context": "https://schema.org", "@type": "SportsEvent", "name": "Vitality – G2"', page)
        self.assertEqual(page.count("application/ld+json"), 1)  # celui de la page du jeu est retiré
        self.assertIn(f'"url": "https://esportly.eu/fr/live/{VS}"', page)

    def test_l_application_reste_dans_l_encart(self):
        """La colonne du match est au match : l'application n'y a plus ni bouton ni lien, tout est dans l'encart de droite."""
        page = render("fr")
        main = main_of(page)
        self.assertEqual(main.count('href="../../match.html?id=1713096"'), 1)  # le seul lien vers la page de renvoi de l'app
        column = main[main.index('<div class="livec">'):main.index('<aside class="liveside">')]
        self.assertNotIn("match.html?id=", column)
        self.assertNotIn('class="cta"', column)
        self.assertIn('<a href="../../match.html?id=1713096">Ouvrir ce match dans l', main.replace("&#x27;", "'"))
        # « location.href » n'apparaît que dans la recherche d'équipe du menu, jamais pour renvoyer vers l'application.
        self.assertNotIn("location.href=", page.replace("location.href=ts.getAttribute('data-dir')", ""))
        self.assertNotIn("esportly://", page)

    def test_script_et_csp(self):
        page = render("en")
        self.assertIn(f"<script>{live.JS}</script>", page)
        policy = re.search(r"script-src[^;\"]*", page).group(0)
        self.assertIn(f"'sha256-{live.HASH}'", policy)
        self.assertIn(f"'sha256-{site_chrome.MENU_HASH}'", policy)
        self.assertEqual(page.count(".matchs{"), 1)
        self.assertEqual(page.count(".live-now{"), 1)
        self.assertEqual(page.count("\n.mcard{display:grid"), 1)
        self.assertEqual(page.count('<details class="menu">'), 1)

    def test_cinq_langues(self):
        game_names = names()
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                page = render(lang)
                x = live_match.TEXTS[lang]
                self.assertIn(f'<html lang="{lang}">', page)
                self.assertIn(f"<title>{html.escape(x['title'].format(match='Vitality – G2'))}</title>", page)
                main = main_of(page)
                for key in ("h_match", "h_follow", "h_more", "open_app", "live_all"):
                    self.assertIn(html.escape(x[key]), main.replace("'", "&#x27;") if "'" in x[key] else main)
                for head, _ in x["follow"]:
                    self.assertIn(f"<b>{head}</b>", main)
                self.assertIn(f'href="{UP[lang]}{live.PAGES[lang]}">', main)
                self.assertIn(f'<a href="{UP[lang]}{site_chrome.GAME_DIRS[lang]}/valorant.html">', main)
                self.assertIn(f'<a class="live" href="{UP[lang]}{live.PAGES[lang]}" aria-current="page">Live</a>', page)
                self.assertIn(f'<nav aria-label="{site_chrome.MENU[lang]["nav"]}">', page)
                self.assertEqual(page.count("</main>"), 1)
                self.assertIn(game_names[lang]["valorant"], main)

    def test_jeu_inconnu_et_match_sans_equipes(self):
        page = render("en", event("Team Falcons Apex", "Apex Legends · ALGS · 2026"))
        main = main_of(page)
        self.assertNotIn("data-game", main)  # jeu inconnu du site : pas de filtre
        self.assertNotIn("/games/", main)  # ni lien vers une page de jeu
        self.assertIn('<a href="../live.html">All of today&#x27;s matches</a>', main)
        self.assertNotIn("<h2>The teams</h2>", main)  # le titre ne nomme pas deux équipes
        # Le titre ne se coupe pas en deux équipes : l'adresse garde le numéro du match, faute de mieux.
        self.assertIn('<link rel="canonical" href="https://esportly.eu/live/1713096">', page)
        self.assertIn("--g:", page)  # couleur de la page modèle (league-of-legends)

    def test_texte_du_calendrier_echappe(self):
        page = render("en", event("A <b> – B & C", "Valorant · <x>"))
        self.assertNotIn("<b> – B", main_of(page))
        self.assertIn("A &lt;b&gt; – B &amp; C", main_of(page))
        self.assertNotIn("<x>", page)
        self.assertEqual(page.count("application/ld+json"), 1)

    def test_sans_numero(self):
        with self.assertRaises(ValueError):
            render("fr", event(mid=None))

    def test_seo_de_la_page_ecrase_le_titre(self):
        seo = {f"/fr/live/{VS}": {"title": "Un titre SEO", "description": "Une description SEO."}}
        page = render("fr", seo=seo)
        self.assertIn("<title>Un titre SEO</title>", page)
        self.assertIn('<meta name="description" content="Une description SEO.">', page)

    def test_fins_de_ligne_du_modele(self):
        ev, game_names = event(), names()
        model = (REAL / live_match.template_file("fr", ev, game_names["en"])).read_bytes().decode("utf-8")
        home = (REAL / "fr.html").read_bytes().decode("utf-8")
        page = live_match.render_page("fr", model, ev, T["fr"], home, game_names)
        self.assertEqual(page.count("\r\n"), page.count("\n") if "\r\n" in model else 0)


VIDEO = {"channel": "LoL Esports", "id": "8ta__l8NOfE", "published": "2026-11-05",
         "title": "Quarterfinals Day 1 Highlights | Worlds 2026"}


class Clip(unittest.TestCase):
    """video_for : la vidéo de temps forts qui va avec le jour du match (jour même ou lendemain), la plus récente d'abord."""

    def test_fenetre_du_jour_et_du_lendemain(self):
        self.assertEqual(live_match.video_for([VIDEO], date(2026, 11, 5)), VIDEO)
        self.assertEqual(live_match.video_for([VIDEO], date(2026, 11, 4)), VIDEO)  # match de la veille, temps forts de la nuit
        self.assertIsNone(live_match.video_for([VIDEO], date(2026, 11, 3)))
        self.assertIsNone(live_match.video_for([VIDEO], date(2026, 11, 6)))

    def test_la_plus_recente_gagne(self):
        vieille = {**VIDEO, "id": "aaaaaaaaaaa", "published": "2026-11-05"}
        recente = {**VIDEO, "id": "bbbbbbbbbbb", "published": "2026-11-06"}
        self.assertEqual(live_match.video_for([vieille, recente], date(2026, 11, 5)), recente)

    def test_rien_sans_video_ni_identifiant(self):
        self.assertIsNone(live_match.video_for([], date(2026, 11, 5)))
        self.assertIsNone(live_match.video_for([{"published": "2026-11-05"}], date(2026, 11, 5)))


@unittest.skipUnless(HAVE_SITE, "pages du site absentes")
class TempsForts(unittest.TestCase):
    """Le bloc « temps forts » : seulement sur un match terminé, rangé derrière un « details », sans rien charger avant le clic."""

    def test_bloc_dans_les_5_langues(self):
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                x = live_match.TEXTS[lang]
                page = render(lang, final=FINAL, video=VIDEO)
                main = main_of(page)
                self.assertIn(f'<h2>{html.escape(x["h_video"])}</h2><details class="mvid">', main)
                self.assertIn(x["video_reveal"], main)
                self.assertIn('data-id="8ta__l8NOfE"', main)
                self.assertIn("https://www.youtube.com/watch?v=8ta__l8NOfE", main)  # secours sans JavaScript
                self.assertNotIn("youtube-nocookie.com/embed/8ta", main)  # rien n'est chargé avant le clic
                self.assertIn("frame-src https://www.youtube-nocookie.com", page)  # la CSP autorise le lecteur au clic
                self.assertIn(blog.PLAYER_HASH, page)  # et son script est permis par son empreinte

    def test_pas_de_bloc_sans_video_ni_sur_un_match_en_cours(self):
        self.assertNotIn("mvid", main_of(render("fr", final=FINAL)))
        en_cours = main_of(render("fr", video=VIDEO))
        self.assertNotIn("mvid", en_cours)  # les temps forts n'ont de sens qu'une fois le match fini
        self.assertNotIn("frame-src", render("fr", final=FINAL))

    def test_titre_et_identifiant_echappes(self):
        main = main_of(render("fr", final=FINAL, video={**VIDEO, "title": '<b>A & "B"', "id": 'x"y'}))
        self.assertNotIn('<b>A & "B"', main)
        self.assertIn("&lt;b&gt;A &amp;", main)
        self.assertIn('data-id="x&quot;y"', main)

FINAL = {"vu": "2026-11-05T09:00:00+00:00", "equipes": ["Vitality", "G2"], "score": [2, 1]}


@unittest.skipUnless(HAVE_SITE, "pages du site absentes")
class Fin(unittest.TestCase):
    """Un match dont la fin est notée (live_suivi.py) : « terminé » quelle que soit l'horloge, score caché derrière un bouton."""

    def test_score_cache_dans_les_5_langues(self):
        for lang in an.LANGS:
            with self.subTest(lang=lang):
                x, main = live_match.TEXTS[lang], main_of(render(lang, final=FINAL)).replace("&#x27;", "'")
                self.assertIn(' data-final="2026-11-05T09:00:00+00:00"', main)
                self.assertIn(f'<h2>{x["h_result"]}</h2><p class="maj">{x["spoil"]}</p>', main)
                self.assertIn(f'<details class="mres"><summary><span class="score" style="{live_match.BLUR}">Vitality <b>2 – 1</b> G2</span>'
                              f'<span class="voir">{x["reveal"]}</span></summary></details>', main)
                self.assertEqual(main.count("2 – 1"), 1)  # le score n'est écrit qu'une fois, flouté derrière le bouton
                self.assertIn("blur(", main)  # flouté par son style en ligne : jamais lisible sans feuille de style
                self.assertLess(main.index('<details class="mres">'), main.index("2 – 1"))
                self.assertIn(x["score_final"], main)  # « comment suivre » ne dit plus que la page ne publie rien
                self.assertNotIn(x["follow"][3][1], main)

    def test_sans_fin_rien_ne_change(self):
        for page in (render("fr"), render("fr", final=None)):
            main = main_of(page)
            self.assertNotIn("data-final", main)
            self.assertNotIn("mres", main)
            self.assertIn("cette page ne publie ni score ni résultat", main)

    def test_fin_sans_score(self):
        main = main_of(render("fr", final={**FINAL, "score": None}))
        self.assertIn(' data-final="2026-11-05T09:00:00+00:00"', main)  # fini, mais rien à montrer
        self.assertNotIn("mres", main)
        self.assertNotIn('class="mres"', main)  # le bloc « Où regarder » peut avoir son propre details
        self.assertIn("cette page ne publie ni score ni résultat", main)

    def test_noms_echappes_et_style(self):
        page = render("fr", final={**FINAL, "equipes": ["<b>A", "B&C"]})
        self.assertIn(f'<span class="score" style="{live_match.BLUR}">&lt;b&gt;A <b>2 – 1</b> B&amp;C</span>', page)
        self.assertEqual(page.count("\n.mres{"), 1)
        self.assertIn(".mres[open] .voir{display:none}", page)
        self.assertIn(".mres[open] .score{filter:none!important;user-select:auto}", page)

    def test_build_donne_a_chaque_match_sa_fin(self):
        events = [event(), event("Falcons – Spirit", "Counter-Strike 2 · ESL Pro League · 2026", mid="1713097")]
        homes = {lang: (REAL / ("index.html" if lang == "en" else an.HOMES[lang])).read_text(encoding="utf-8") for lang in an.LANGS}
        event_pages = {lang: [] for lang in an.LANGS}
        weeks = {lang: an.WEEKLY[lang] for lang in an.LANGS}
        pages = live_match.build(REAL, events, T, homes, names(), event_pages, weeks, None, {"1713097": {**FINAL, "equipes": ["Falcons", "Spirit"]}})
        for folder in live_match.DIRS.values():
            self.assertIn("Falcons <b>2 – 1</b> Spirit", pages[f"{folder}/{VS2}.html"])
            self.assertNotIn("data-final", main_of(pages[f"{folder}/{VS}.html"]))


@unittest.skipUnless(HAVE_SITE, "pages du site absentes")
class Construction(unittest.TestCase):
    def test_build_toutes_les_langues(self):
        events = [event(), event("Falcons – Spirit", "Counter-Strike 2 · ESL Pro League · 2026", mid="1713097"), event("Sans numéro", mid=None)]
        homes = {lang: (REAL / ("index.html" if lang == "en" else an.HOMES[lang])).read_text(encoding="utf-8") for lang in an.LANGS}
        event_pages = {lang: [("ESL Pro League", an.page_for("esl-pro-league", lang))] for lang in an.LANGS}
        weeks = {lang: an.WEEKLY[lang] for lang in an.LANGS}
        pages = live_match.build(REAL, events, T, homes, names(), event_pages, weeks)
        self.assertEqual(sorted(pages), sorted(f"{folder}/{mid}.html" for folder in live_match.DIRS.values() for mid in (f"{VS}", f"{VS2}")))
        fr = main_of(pages[f"fr/live/{VS2}.html"])
        self.assertIn('<a href="../../fr/esl-pro-league.html">ESL Pro League</a>', fr)
        self.assertIn('<a href="../../fr/blog/counter-strike-2.html">', fr)
        self.assertIn('<a href="../../fr/equipes/spirit.html">fiche et prochains matchs</a>', fr)
        self.assertIn('<a href="../../teams/spirit.html">', main_of(pages[f"es/live/{VS2}.html"]))
        self.assertIn('<a href="../../fr/matchs-de-la-semaine.html">', fr)
        self.assertIn('<a href="../esl-pro-league-en.html">ESL Pro League</a>', main_of(pages[f"live/{VS2}.html"]))
        again = live_match.build(REAL, events, T, homes, names(), event_pages, weeks)
        self.assertEqual(again, pages)  # mêmes entrées, mêmes pages

    def test_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def page(folder: str, name: str, start: datetime | None) -> Path:
                path = root / folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('<ul class="matchs"><li ' + (f'data-start="{start.isoformat()}" ' if start else "") + 'data-end="x"></li></ul>', encoding="utf-8")
                return path

            old, recent = NOW - live_match.KEEP - timedelta(hours=1), NOW - timedelta(days=1)
            for folder in live_match.DIRS.values():
                page(folder, "1.html", old)
                page(folder, "2.html", recent)
                page(folder, "3.html", None)
                page(folder, "4.html", old)
                page(folder, "vitality-vs-g2-2026-11-05.html", recent)  # nom lisible et match récent : gardée
            (root / "fr" / "live" / "notes.txt").write_text("x", encoding="utf-8")
            gone = live_match.prune(root, NOW, keep={"fr/live/4.html"})
            # 2.html est récente mais n'a qu'un numéro pour nom : c'est une page de l'ancienne façon de nommer, et plus rien ne
            # pointe vers elle depuis que les adresses disent les équipes et la date.
            expected = [f"{folder}/{name}" for folder in live_match.DIRS.values() for name in ("1.html", "2.html", "4.html")
                        if f"{folder}/{name}" != "fr/live/4.html"]
            self.assertEqual(sorted(gone), sorted(expected))
            self.assertFalse(any((root / folder / "1.html").exists() for folder in live_match.DIRS.values()))
            self.assertTrue((root / "fr" / "live" / "4.html").exists())  # fabriquée à l'instant : gardée
            self.assertFalse((root / "es" / "live" / "4.html").exists())
            for folder in live_match.DIRS.values():  # un nom lisible et un match récent : la page reste
                self.assertTrue((root / folder / "vitality-vs-g2-2026-11-05.html").exists())
            for folder in live_match.DIRS.values():
                self.assertFalse((root / folder / "2.html").exists())  # récente, mais nommée d'un numéro : ancienne façon
                self.assertTrue((root / folder / "3.html").exists())  # sans heure lisible : gardée
            self.assertTrue((root / "fr" / "live" / "notes.txt").exists())
            self.assertEqual(live_match.prune(root, NOW, keep=set()), ["fr/live/4.html"])

    def test_prune_sans_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(live_match.prune(Path(tmp), NOW), [])

if __name__ == "__main__":
    unittest.main()
