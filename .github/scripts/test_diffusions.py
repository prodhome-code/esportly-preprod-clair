"""Tests de « où regarder » : le tableau des chaînes, le lecteur des pages de match, les deux colonnes de la page Live."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import diffusions
import live
import live_match

REAL = Path(__file__).resolve().parents[2]


class Tableau(unittest.TestCase):
    def test_une_competition_connue(self):
        found = diffusions.channel_for("League of Legends · Worlds · 2026")
        self.assertIsNotNone(found)
        self.assertEqual(found["platform"], "twitch")
        self.assertEqual(found["channel"], "riotgames")
        self.assertIn("parent=esportly.eu", found["player"])

    def test_une_competition_inconnue_n_a_pas_de_chaine(self):
        """Mieux vaut aucun lecteur qu'un lecteur qui diffuse autre chose."""
        for description in ("Dota 2 · Tournoi inconnu · 2026", "Jeu inconnu · Worlds · 2026", "", "·"):
            with self.subTest(description=description):
                self.assertIsNone(diffusions.channel_for(description))

    def test_les_plateformes_ont_toutes_un_lecteur_et_un_frame_src(self):
        self.assertEqual(set(diffusions.PLAYERS), set(diffusions.PAGES))
        self.assertEqual(set(diffusions.PLAYERS), set(diffusions.FRAMES))

    def test_le_meme_mot_cle_sur_deux_jeux(self):
        """« PGL » diffuse Counter-Strike et Dota 2 sur deux chaînes : le jeu départage."""
        cs = diffusions.channel_for("Counter-Strike 2 · PGL Major · Singapore 2026")
        dota = diffusions.channel_for("Dota 2 · PGL Wallachia · Season 5 2026")
        self.assertEqual(cs["channel"], "pgl")
        self.assertEqual(dota["channel"], "pgl_dota2")

    def test_un_mot_cle_large_ne_deborde_pas(self):
        """« league » est un mot-clé de Rainbow Six : il ne doit pas attraper les autres jeux."""
        self.assertIsNone(diffusions.channel_for("Counter-Strike 2 · Tesla Cup · 2026"))
        self.assertEqual(diffusions.channel_for("Rainbow Six Siege · North America League · Stage 2 2026")["channel"], "rainbow6")

    def test_une_description_qui_commence_par_une_date(self):
        found = diffusions.channel_for("samedi 31 octobre · Overwatch · OCS · EMEA Stage 3 2026")
        self.assertEqual(found["channel"], "owcs")

    def test_toutes_les_chaines_ont_une_plateforme_connue(self):
        for word, game, streams in diffusions.CHANNELS:
            self.assertTrue(word and streams)
            for platform, channel, label in streams:
                with self.subTest(channel=channel):
                    self.assertIn(platform, diffusions.PLAYERS)
                    self.assertIn(platform, diffusions.FRAMES)
                    self.assertIn(platform, diffusions.NAMES)
                    self.assertTrue(channel and label)

    def test_youtube_veut_un_identifiant_de_chaine(self):
        """Le lecteur de direct de YouTube ne connaît pas les noms en @ : seulement les identifiants « UC… »."""
        for word, game, streams in diffusions.CHANNELS:
            for platform, channel, label in streams:
                if platform == "youtube":
                    with self.subTest(channel=channel):
                        self.assertRegex(channel, "^UC[A-Za-z0-9_-]{20,24}$")

    def test_plusieurs_chaines_pour_une_competition(self):
        """Twitch porte le lecteur, YouTube est proposé à côté."""
        found = diffusions.channels_for("League of Legends · Worlds · 2026")
        self.assertEqual([stream["site"] for stream in found], ["Twitch", "YouTube"])

    def test_la_chaine_qui_diffuse_passe_devant(self):
        """EPL a deux chaînes Kick en parallèle : celle qui diffuse porte le lecteur, sinon la moitié des matchs serait éteinte."""
        streams = [diffusions._stream("kick", "a", "A"), diffusions._stream("kick", "b", "B")]
        diffusions._LIVE.update({"a": False, "b": True})
        try:
            self.assertEqual([s["channel"] for s in diffusions.live_first(streams)], ["b", "a"])
            diffusions._LIVE.update({"a": False, "b": False})
            self.assertEqual([s["channel"] for s in diffusions.live_first(streams)], ["a", "b"])  # aucune : ordre du tableau
        finally:
            diffusions._LIVE.pop("a", None), diffusions._LIVE.pop("b", None)

    def test_aucune_question_posee_pour_une_seule_chaine(self):
        """Pas de requête réseau quand il n'y a rien à départager."""
        before = dict(diffusions._LIVE)
        diffusions.live_first([diffusions._stream("kick", "seule", "Seule")])
        self.assertEqual(diffusions._LIVE, before)


class Lecteur(unittest.TestCase):
    EVENT = {"SUMMARY": "T1 – Gen.G", "DESCRIPTION": "League of Legends · Worlds · 2026"}

    def test_le_direct_est_visible_et_ne_demarre_pas_seul(self):
        """C'est ce qu'on vient chercher : le lecteur est là d'emblée, mais en pause et muet."""
        html = live_match.render_watch("fr", self.EVENT)
        self.assertIn('<section class="mwatch"', html)
        self.assertLess(html.index("wframe"), html.index("wlead"))  # le lecteur avant sa légende, pas l'inverse
        self.assertNotIn("<details", html)
        self.assertIn("autoplay=false", html)
        self.assertIn("muted=true", html)
        self.assertIn('loading="lazy"', html)

    def test_le_direct_nomme_le_match_et_la_chaine(self):
        html = live_match.render_watch("fr", self.EVENT)
        self.assertIn("T1 – Gen.G", html)
        self.assertIn("Riot Games", html)

    def test_le_direct_previent_du_score(self):
        """Un direct montre le score en cours : c'est le contraire de la promesse du site, il faut le dire."""
        self.assertIn("score en cours", live_match.render_watch("fr", self.EVENT))

    def test_sans_chaine_aucun_bloc(self):
        self.assertEqual(live_match.render_watch("fr", {"DESCRIPTION": "Dota 2 · Tournoi inconnu · 2026"}), "")

    def test_les_autres_chaines_sont_proposees(self):
        """Twitch porte le lecteur, YouTube est à côté : les deux sont à disposition."""
        html = live_match.render_watch("fr", self.EVENT)
        self.assertIn('class="walso"', html)
        self.assertIn("youtube.com/channel/UCSF_aFGIIIoWY30GVV19TKA/live", html)
        self.assertIn(">YouTube</a>", html)

    def test_les_cinq_langues(self):
        for lang in live.LABELS:
            with self.subTest(lang=lang):
                self.assertIn("<iframe", live_match.render_watch(lang, self.EVENT))


class CSP(unittest.TestCase):
    PAGE = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; object-src \'none\'; base-uri \'none\'">'

    def test_frame_src_est_cree(self):
        done = live_match._with_frames(self.PAGE, ("https://player.twitch.tv",))
        self.assertIn("frame-src https://player.twitch.tv; object-src 'none'", done)

    def test_frame_src_existant_est_complete(self):
        page = self.PAGE.replace("object-src", "frame-src https://www.youtube-nocookie.com; object-src")
        done = live_match._with_frames(page, ("https://player.twitch.tv",))
        self.assertEqual(done.count("frame-src"), 1)
        self.assertIn("frame-src https://www.youtube-nocookie.com https://player.twitch.tv;", done)

    def test_rejouable(self):
        once = live_match._with_frames(self.PAGE, ("https://player.twitch.tv",))
        self.assertEqual(live_match._with_frames(once, ("https://player.twitch.tv",)), once)


class PageLive(unittest.TestCase):
    def test_l_encart_dit_ce_qu_apporte_l_app(self):
        for lang in live.LABELS:
            with self.subTest(lang=lang):
                side = live.render_side(lang, "fr/live")
                self.assertIn('<aside class="liveside">', side)
                self.assertIn('class="cta"', side)
                self.assertIn(live.LABELS[lang]["side_title"], side)

    @unittest.skipUnless((REAL / "fr/live.html").is_file(), "site absent")
    def test_les_directs_sont_avant_le_filtre(self):
        """Ce qu'on vient chercher d'abord : la section des directs passe avant le filtre par jeu."""
        page = (REAL / "fr/live.html").read_text(encoding="utf-8")
        main = re.search(r"<main.*?</main>", page, re.S).group(0)
        self.assertLess(main.index('id="l-live"'), main.index('class="filter"'))

    @unittest.skipUnless((REAL / "fr/live.html").is_file(), "site absent")
    def test_les_deux_colonnes(self):
        page = (REAL / "fr/live.html").read_text(encoding="utf-8")
        self.assertIn('<div class="livew">', page)
        self.assertIn('<aside class="liveside">', page)
        self.assertIn("grid-template-columns:minmax(0,1fr) 304px", page)
        self.assertIn("position:sticky", page)

    @unittest.skipUnless((REAL / "fr/live").is_dir(), "site absent")
    def test_le_direct_est_avant_la_carte_du_match(self):
        """On ne doit pas avoir à faire défiler la page pour voir le direct."""
        for path in sorted((REAL / "fr/live").glob("*.html")):
            page = path.read_text(encoding="utf-8")
            main = re.search(r"<main.*?</main>", page, re.S)
            if main is None or 'class="mwatch"' not in main.group(0):
                continue
            with self.subTest(match=path.stem):
                self.assertLess(main.group(0).index('class="mwatch"'), main.group(0).index('class="mcard"'))

    @unittest.skipUnless((REAL / "fr/live").is_dir(), "site absent")
    def test_aucun_lecteur_sur_un_match_fini(self):
        """Après le match, la chaîne diffuse autre chose : le lecteur n'a plus de sens, et montrerait la suite."""
        for path in sorted((REAL / "fr/live").glob("*.html")):
            page = path.read_text(encoding="utf-8")
            if 'class="mres"' in page:
                with self.subTest(match=path.stem):
                    self.assertNotIn('class="wframe"', page)

    @unittest.skipUnless((REAL / "fr/live").is_dir(), "site absent")
    def test_chaque_lecteur_est_declare_dans_la_csp(self):
        for path in sorted((REAL / "fr/live").glob("*.html")):
            page = path.read_text(encoding="utf-8")
            if 'class="wframe"' not in page:
                continue
            with self.subTest(match=path.stem):
                found = re.search(r"frame-src ([^;]*)", page)
                self.assertIsNotNone(found, "lecteur sans frame-src dans la CSP")
                source = re.search(r'<div class="wframe"><iframe src="(https://[^/]+)', page).group(1)
                self.assertIn(source, found.group(1))


if __name__ == "__main__":
    unittest.main()
