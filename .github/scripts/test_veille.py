"""Tests de veille.py (agent de veille) : lecture des sources, liste blanche, dédoublonnage, contrôle des pull requests.

Aucun accès réseau : les flux, les pages et les robots.txt sont des fonctions de test, comme dans test_topplays.py.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -p "test_veille.py" -v
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import actualites as an
import veille

TODAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)  # 10 h à Paris
LANGS = an.LANGS

SOURCE_URL = "https://exemple.test/news/riot-2027"
SOURCE_HTML = """<html><body><h1>Riot announces the 2027 global tour</h1>
<p>The VCT 2027 season brings twenty four partner teams to three continents, with the first stage starting in January 2027.</p>
<p>Each region hosts a kickoff event before the international masters, and the championship closes the year in September 2027.</p>
</body></html>"""

# Textes de l'article : 3 paragraphes dans chaque langue, mêmes nombres (2027, 24, 4), formulation propre.
EN = [
    "Riot has confirmed the shape of its 2027 Valorant circuit. The season opens with a short regional kickoff, then moves to a "
    "single international stage where every qualified squad faces the others. A final weekend decides the champion.",
    "Twenty four partner organisations were named by the publisher. For viewers the change matters more than it looks: fewer "
    "events, longer runs, and a calendar that reads the same in every timezone. Teams that miss the kickoff must climb through "
    "an open qualifier, which Riot says will be played online.",
    "The publisher also promised that match schedules will be published at least 4 weeks ahead, so fans can plan around them. "
    "Nothing was said about prize money or the venue of the final. eSportly will follow each stage and warn fans before kickoff. "
    "The circuit replaces the previous split system, which many players criticised for its travel demands and for the short "
    "notice given on venues and start times.",
]
FR = [
    "Riot a confirmé la forme de son circuit Valorant 2027. La saison s'ouvre par un court lancement régional, puis une seule "
    "scène internationale où chaque équipe qualifiée affronte les autres. Un dernier week-end désigne le champion.",
    "Vingt-quatre organisations partenaires ont été nommées. Pour le public, le changement compte plus qu'il n'y paraît : moins "
    "d'événements, des formats plus longs, un calendrier identique dans chaque fuseau. Les équipes qui manquent le lancement "
    "passent par un qualifier ouvert, joué en ligne selon Riot.",
    "L'éditeur promet aussi un programme publié au moins 4 semaines à l'avance, pour que les fans s'organisent. Rien n'a été dit "
    "sur les gains ni sur la salle de la finale. eSportly suivra chaque étape et préviendra avant chaque match.",
]
ES = [
    "Riot ha confirmado la forma de su circuito de Valorant 2027. La temporada abre con un breve arranque regional y después una "
    "sola fase internacional donde cada equipo clasificado se enfrenta a los demás. Un último fin de semana decide al campeón.",
    "Se han nombrado veinticuatro organizaciones asociadas. Para el público el cambio importa más de lo que parece: menos "
    "eventos, formatos más largos y un calendario igual en cada zona horaria. Quien falle el arranque pasa por un clasificatorio "
    "abierto, en línea según Riot.",
    "El editor promete además un calendario publicado al menos 4 semanas antes, para que los aficionados se organicen. No se dijo "
    "nada sobre premios ni sobre el pabellón de la final. eSportly seguirá cada etapa y avisará antes de cada partido.",
]
DE = [
    "Riot hat die Form seiner Valorant-Saison 2027 bestätigt. Die Saison beginnt mit einem kurzen regionalen Auftakt, danach folgt "
    "eine einzige internationale Phase, in der jedes qualifizierte Team gegen die anderen spielt. Ein letztes Wochenende "
    "entscheidet den Titel.",
    "Vierundzwanzig Partnerorganisationen wurden benannt. Für das Publikum zählt mehr, als es aussieht: weniger Events, längere "
    "Formate und ein Kalender, der in jeder Zeitzone gleich aussieht. Wer den Auftakt verpasst, muss durch eine offene "
    "Qualifikation, die laut Riot online gespielt wird.",
    "Der Verlag verspricht außerdem einen Spielplan, der mindestens 4 Wochen vorher erscheint. Zu Preisgeld und Finalort wurde "
    "nichts gesagt. eSportly verfolgt jede Phase und erinnert vor jedem Spiel.",
]
PT = [
    "A Riot confirmou o formato do seu circuito de Valorant 2027. A temporada abre com um curto arranque regional e depois uma só "
    "fase internacional, em que cada equipa apurada defronta as outras. Um último fim de semana decide o campeão.",
    "Vinte e quatro organizações parceiras foram nomeadas. Para o público a mudança importa mais do que parece: menos eventos, "
    "formatos mais longos e um calendário igual em cada fuso horário. Quem falhar o arranque passa por um qualificador aberto, "
    "em linha segundo a Riot.",
    "A editora promete ainda um calendário publicado pelo menos 4 semanas antes. Nada foi dito sobre prémios nem sobre a sala da "
    "final. A eSportly acompanha cada fase e avisa antes de cada jogo.",
]
TEXTES = {"en": EN, "fr": FR, "es": ES, "de": DE, "pt-BR": PT}

CLAIMS = """# Riot 2027 : tableau des affirmations

| Affirmation | Source | Extrait |
|---|---|---|
| Le circuit réunit vingt-quatre équipes partenaires | s1 | twenty four partner teams |
| La première phase commence en janvier 2027 | s1 | the first stage starting in January 2027 |
"""

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Riot opens the 2027 Valorant tour</title><link>{fresh}</link><pubDate>Sat, 08 Nov 2026 06:00:00 GMT</pubDate></item>
<item><title>Second topic of the day</title><link>{fresh2}</link><pubDate>Sat, 08 Nov 2026 05:00:00 GMT</pubDate></item>
<item><title>An old piece nobody needs</title><link>{old}</link><pubDate>Mon, 20 Oct 2026 05:00:00 GMT</pubDate></item>
</channel></rss>"""

PAGE = """<html><body>
<a href="https://exemple.test/news/">News</a>
<a href="https://exemple.test/news/a-real-article-about-cs2">A real article about the Counter-Strike scene</a>
<a href="https://exemple.test/schedule">Schedule</a>
<a href="https://exemple.test/teams">Teams of the league</a>
</body></html>"""

SOURCES = {"sources": [
    {"id": "exemple", "name": "Exemple officiel", "url": "https://exemple.test/news/", "feed": "https://exemple.test/feed.xml",
     "kind": "feed", "games": ["valorant"], "types": ["esport"], "lang": "en", "note": "source de test"},
    {"id": "exemple-page", "name": "Exemple page", "url": "https://exemple.test/news/", "feed": None, "kind": "page",
     "games": ["counter-strike-2"], "types": ["esport"], "lang": "en", "note": "source de test"},
]}


def page_json(page_id: str = "riot-2027", day: date = TODAY, textes: dict | None = None, kind: str = "news",
              source_url: str = SOURCE_URL) -> dict:
    """Un article conforme au format du Blog (1 section, 3 paragraphes par langue, 1 source)."""
    textes = textes or TEXTES
    titres = {"en": "Riot confirms the 2027 Valorant tour", "fr": "Riot confirme le circuit Valorant 2027",
              "es": "Riot confirma el circuito de Valorant 2027", "de": "Riot bestätigt die Valorant-Saison 2027",
              "pt-BR": "Riot confirma o circuito de Valorant 2027"}
    return {"kind": kind, "date": day.isoformat(), "updated": day.isoformat(),
            "sources": [{"id": "s1", "title": "Riot Games", "url": source_url}],
            "sections": [{"cite": ["s1"], **{lang: {"heading": "Ce qui change", "text": textes[lang]} for lang in LANGS}}],
            **{lang: {"title": titres[lang], "description": f"{titres[lang]} : le calendrier et les équipes."} for lang in LANGS}}


class Base(unittest.TestCase):
    """Un dépôt de test : blog-src/veille, blog-src/pages, blog-src/claims."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("blog-src/veille", "blog-src/pages", "blog-src/claims"):
            (self.root / folder).mkdir(parents=True)
        self.write("blog-src/veille/sources.json", json.dumps(SOURCES))
        self.write("blog-src/veille/seen.json", json.dumps({"seen": {}, "topics": {}}))
        self.write("blog-src/veille/mode.json", json.dumps({"auto_from": None}))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def add_article(self, page_id: str = "riot-2027", **kwargs) -> str:
        self.write(f"blog-src/pages/{page_id}.json", json.dumps(page_json(page_id, **kwargs), ensure_ascii=False))
        self.write(f"blog-src/claims/{page_id}.md", CLAIMS)
        return page_id

    def fetch(self, answers: dict[str, tuple[int, str]] | None = None):
        """Une fausse lecture réseau : la page source répond, tout le reste aussi par défaut."""
        answers = answers or {}

        def get(url: str) -> tuple[int, str]:
            if url in answers:
                return answers[url]
            return 200, SOURCE_HTML

        return get


class TestDonnees(Base):
    def test_sources_du_depot_sont_valides(self):
        """Le vrai blog-src/veille/sources.json du dépôt passe la validation (aucun réseau)."""
        sources = veille.load_sources(veille.ROOT)
        self.assertGreaterEqual(len(sources), 10)
        for source in sources:
            self.assertTrue(source["note"])
        self.assertIn("esl.com", veille.whitelist(sources))

    def test_verifier_refuse_un_champ_inconnu(self):
        data = json.loads(json.dumps(SOURCES))
        data["sources"][0]["couleur"] = "bleu"
        self.write("blog-src/veille/sources.json", json.dumps(data))
        with self.assertRaises(veille.VeilleError) as caught:
            veille.load_sources(self.root)
        self.assertIn("champ inconnu", str(caught.exception.problems))

    def test_verifier_refuse_auto_from_illisible(self):
        self.write("blog-src/veille/mode.json", json.dumps({"auto_from": "demain"}))
        with self.assertRaises(veille.VeilleError):
            veille.verifier(self.root)

    def test_whitelist_ajoute_les_domaines_also(self):
        sources = [{"url": "https://exemple.test/a", "feed": None, "also": ["cdn.exemple.test"]}]
        self.assertEqual(veille.whitelist(sources), {"exemple.test", "cdn.exemple.test"})


class TestFluxEtPages(Base):
    def test_flux_rss(self):
        items = veille.parse_feed(FEED.format(fresh="https://exemple.test/news/un", fresh2="https://exemple.test/news/deux",
                                              old="https://exemple.test/news/vieux"),
                                  "https://exemple.test/feed.xml")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["published"], date(2026, 11, 8))
        self.assertEqual(items[2]["published"], date(2026, 10, 20))

    def test_flux_avec_dtd_refuse(self):
        with self.assertRaises(ValueError):
            veille.parse_feed('<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "b">]><rss></rss>', "https://exemple.test/feed")

    def test_page_ecarte_les_rubriques(self):
        items = veille.page_items(PAGE, "https://exemple.test/news/")
        self.assertEqual([item["url"] for item in items], ["https://exemple.test/news/a-real-article-about-cs2"])
        self.assertIsNone(items[0]["published"])  # aucune date n'est devinée

    def test_page_localisee_garde_sa_langue_dans_les_adresses(self):
        """Une page « /en-US/news » mène à des adresses sans langue : l'article garde « /en-US/ » (sinon le robot de
        contrôle lit la page dans sa propre langue et les extraits ne correspondent plus)."""
        page = '<a href="/news/vct-2027-the-global-tour">VCT 2027: the global tour begins</a>'
        items = veille.page_items(page, "https://exemple.test/en-US/news")
        self.assertEqual([item["url"] for item in items],
                         ["https://exemple.test/en-US/news/vct-2027-the-global-tour"])

    def test_pyc_et_pycache_ne_sont_pas_des_fichiers_de_la_pr(self):
        self.assertIsNone(veille._path_problem(".github/scripts/__pycache__/bascule_appstore.cpython-312.pyc"))
        self.assertIsNotNone(veille._path_problem(".github/scripts/blog.py"))

    def test_cle_de_sujet_stable(self):
        self.assertEqual(veille.topic_key("VCT 2027: the global tour", "valorant", "esport"),
                         veille.topic_key("VCT 2027 — The global tour", "valorant", "esport"))


class TestCollecte(Base):
    def test_garde_les_nouveaux_et_ecarte_les_vus_et_les_vieux(self):
        self.write("blog-src/veille/seen.json", json.dumps(
            {"seen": {"https://exemple.test/news/deux": "2026-11-07"}, "topics": {}}))
        answers = {"https://exemple.test/feed.xml": (200, FEED.format(
            fresh="https://exemple.test/news/un", fresh2="https://exemple.test/news/deux",
            old="https://exemple.test/news/vieux"))}
        payload = veille.collect(self.root, NOW, self.fetch(answers), robots=lambda url: True)
        urls = [candidate["url"] for candidate in payload["candidates"]]
        self.assertIn("https://exemple.test/news/un", urls)
        self.assertNotIn("https://exemple.test/news/deux", urls)  # déjà vue
        self.assertNotIn("https://exemple.test/news/vieux", urls)  # trop vieille
        self.assertTrue(payload["candidates"][0]["untrusted"])
        self.assertIn("partner", payload["candidates"][0]["text"])
        self.assertTrue((self.root / veille.CANDIDATES).is_file())

    def test_robots_refuse_une_source(self):
        payload = veille.collect(self.root, NOW, self.fetch({"https://exemple.test/feed.xml": (200, FEED.format(
            fresh="https://exemple.test/news/un", fresh2="https://exemple.test/news/deux", old="https://exemple.test/news/vieux"))}),
            robots=lambda url: "feed.xml" not in url and "news/" not in url)
        self.assertEqual(payload["candidates"], [])
        self.assertTrue(any("robots.txt" in note for note in payload["en_panne"]))

    def test_redirection_hors_liste_blanche(self):
        def get(url: str):
            raise veille.HorsListe("https://ailleurs.test/page")

        payload = veille.collect(self.root, NOW, get, robots=lambda url: True)
        self.assertEqual(payload["candidates"], [])
        self.assertTrue(any("hors liste blanche" in note for note in payload["en_panne"]))

    def test_doublon_de_sujet_ecarte(self):
        self.write("blog-src/veille/seen.json", json.dumps(
            {"seen": {}, "topics": {veille.topic_key("Riot opens the 2027 Valorant tour", "valorant", "esport"): "2026-11-01"}}))
        answers = {"https://exemple.test/feed.xml": (200, FEED.format(
            fresh="https://exemple.test/news/un", fresh2="https://exemple.test/news/deux",
            old="https://exemple.test/news/vieux"))}
        payload = veille.collect(self.root, NOW, self.fetch(answers), robots=lambda url: True)
        self.assertNotIn("https://exemple.test/news/un", [c["url"] for c in payload["candidates"]])


class TestPortee(unittest.TestCase):
    def test_plus_longue_suite(self):
        left = "le chat noir dort sur le tapis".split()
        right = "un chat noir dort sur le tapis rouge".split()
        self.assertEqual(veille.longest_run(left, right), 6)  # « chat noir dort sur le tapis »

    def test_recouvrement(self):
        words = "a b c d e f g h i j k l m n".split()
        self.assertEqual(veille.overlap(veille.shingles(words), veille.shingles(words), 5), 1.0)
        self.assertEqual(veille.overlap(veille.shingles("x y".split()), veille.shingles(words), 5), 0.0)


class TestControle(Base):
    def test_article_conforme(self):
        page_id = self.add_article()
        problems, _ = veille.gate(self.root, [f"blog-src/pages/{page_id}.json"], self.fetch(), TODAY)
        self.assertEqual(problems, [])

    def test_stop_present(self):
        self.add_article()
        self.write("blog-src/veille/STOP", "")
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"], self.fetch(), TODAY)
        self.assertTrue(any("arrêtée" in problem for problem in problems))

    def test_fichier_hors_contenu(self):
        self.add_article()
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json", ".github/scripts/blog.py"], self.fetch(), TODAY)
        self.assertTrue(any("hors contenu" in problem for problem in problems))

    def test_sources_json_modifiable_seulement_par_l_utilisateur(self):
        self.add_article()
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json", "blog-src/veille/sources.json"], self.fetch(), TODAY)
        self.assertTrue(any("réglage de la veille" in problem for problem in problems))

    def test_quatre_articles_refuses(self):
        files = []
        for index in range(4):
            files.append(f"blog-src/pages/{self.add_article(f'riot-2027-{index}')}.json")
        problems, _ = veille.gate(self.root, files, self.fetch(), TODAY)
        self.assertTrue(any("3 au plus par jour" in problem for problem in problems))

    def test_source_hors_liste_blanche(self):
        self.add_article(source_url="https://ailleurs.test/article")
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"], self.fetch(), TODAY)
        self.assertTrue(any("hors liste blanche" in problem for problem in problems))

    def test_source_injoignable(self):
        self.add_article()
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"],
                                  self.fetch({SOURCE_URL: (404, "")}), TODAY)
        self.assertTrue(any("ne répond pas" in problem for problem in problems))

    def test_recopie_refusee(self):
        copie = ["Riot has confirmed the shape of its 2027 Valorant circuit and the first stage starting in January 2027 "
                 "with twenty four partner teams from three continents across every region of the world today."] * 3
        textes = {lang: copie for lang in LANGS}
        self.add_article(textes=textes)
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"], self.fetch(), TODAY)
        self.assertTrue(any("mots identiques d'affilée" in problem for problem in problems))

    def test_langues_desalignees(self):
        textes = json.loads(json.dumps(TEXTES))
        textes["de"] = textes["de"][:2]
        self.add_article(textes=textes)
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"], self.fetch(), TODAY)
        self.assertTrue(any("paragraphes désalignés" in problem for problem in problems))

    def test_extrait_introuvable(self):
        self.add_article()
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"],
                                  self.fetch({SOURCE_URL: (200, "<html><body><p>Rien à voir.</p></body></html>")}), TODAY)
        self.assertTrue(any("extrait introuvable" in problem for problem in problems))

    def test_article_trop_court(self):
        textes = {lang: [TEXTES[lang][0]] for lang in LANGS}
        self.add_article(textes=textes)
        problems, _ = veille.gate(self.root, ["blog-src/pages/riot-2027.json"], self.fetch(), TODAY)
        self.assertTrue(any("mots en anglais" in problem for problem in problems))

    def test_aucun_article(self):
        problems, _ = veille.gate(self.root, [], self.fetch(), TODAY)
        self.assertTrue(any("aucun article" in problem for problem in problems))

    def test_commande_gate_rend_un_code(self):
        self.add_article()
        with mock.patch("sys.stdout"):
            code = veille.main(["gate", "--fichiers", "blog-src/pages/riot-2027.json"], self.root, NOW, self.fetch())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
