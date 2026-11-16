"""Tests des logos sur les cartes de match."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import logos_matchs as lm

REAL = Path(__file__).resolve().parents[2]
LOGOS = {"karminecorp": "134078.webp", "kc": "134078.webp", "g2esports": "115.webp"}
CARD = ('<ul class="matchs"><li><a href="x" target="_top"><time datetime="2026-11-05T14:00:00+00:00">15:00</time>'
        '<b>Karmine Corp – Yellow Submarine</b><small>Dota 2 · EPL Masters</small></a></li></ul>')


class Decoupage(unittest.TestCase):
    def test_les_separateurs(self):
        for title in ("A – B", "A - B", "A vs B", "A VS B", "A vs. B", "A — B"):
            with self.subTest(title=title):
                self.assertEqual(lm.teams_of(title), ("", "A", "B"))

    def test_l_etape_est_gardee(self):
        self.assertEqual(lm.teams_of("Grand Final: Na`Vi vs TBD"), ("Grand Final:", "Na`Vi", "TBD"))

    def test_un_titre_inhabituel_est_laisse(self):
        for title in ("Journée 3", "A – B – C", "– B", "A – "):
            with self.subTest(title=title):
                self.assertIsNone(lm.teams_of(title))


class Pastilles(unittest.TestCase):
    def test_les_initiales(self):
        self.assertEqual(lm.monogram("Bilibili Gaming"), "BG")
        self.assertEqual(lm.monogram("B8"), "B8")
        self.assertEqual(lm.monogram("Na`Vi"), "NV")

    def test_un_adversaire_inconnu_ne_prend_pas_d_initiales(self):
        for name in ("TBD", "TBA", "À déterminer"):
            with self.subTest(name=name):
                self.assertEqual(lm.monogram(name), "?")

    def test_le_nom_reduit(self):
        self.assertEqual(lm.key("Na`Vi"), "navi")
        self.assertEqual(lm.key("Team Falcons"), "teamfalcons")


class Render(unittest.TestCase):
    def test_une_carte_prend_logo_et_pastille(self):
        done = lm.render(CARD, "fr/matchs-de-la-semaine.html", LOGOS)
        self.assertIn('<span class="tm"><i><img src="../logos-equipes/134078.webp"', done)
        self.assertIn("Karmine Corp</span>", done)
        self.assertIn('<i class="mono" aria-hidden="true">YS</i>Yellow Submarine', done)
        self.assertIn("<em>–</em>", done)

    def test_le_lien_et_l_heure_ne_bougent_pas(self):
        done = lm.render(CARD, "fr/matchs-de-la-semaine.html", LOGOS)
        self.assertIn('<a href="x" target="_top">', done)
        self.assertIn('<time datetime="2026-11-05T14:00:00+00:00">15:00</time>', done)
        self.assertIn("<small>Dota 2 · EPL Masters</small>", done)

    def test_la_profondeur_de_la_page(self):
        done = lm.render(CARD, "fr/jeux/dota-2.html", LOGOS)
        self.assertIn('src="../../logos-equipes/134078.webp"', done)

    def test_hors_liste_de_matchs_rien_ne_bouge(self):
        page = "<ul class=\"teams\"><li><a href=\"x\"><b>Karmine Corp – G2 Esports</b></a></li></ul>"
        self.assertEqual(lm.render(page, "fr.html", LOGOS), page)

    def test_rejouable(self):
        once = lm.render(CARD, "fr.html", LOGOS)
        self.assertEqual(lm.render(once, "fr.html", LOGOS), once)

    def test_un_titre_inhabituel_reste_intact(self):
        page = CARD.replace("Karmine Corp – Yellow Submarine", "Journée 3")
        self.assertEqual(lm.render(page, "fr.html", LOGOS), page)


@unittest.skipUnless((REAL / "fr/matchs-de-la-semaine.html").is_file(), "site absent")
class Site(unittest.TestCase):
    def test_les_cartes_du_site_ont_toutes_une_pastille(self):
        """Chaque carte montre deux camps avec leur pastille : aucune ne garde un côté nu."""
        nus = []
        for path in lm.pages(REAL):
            page = path.read_text(encoding="utf-8")
            for found in lm.LIST.findall(page):
                for card in re.findall(r"<b>(.*?)</b>", found, re.S):
                    if "<span class=\"tm\">" in card and card.count("<span class=\"tm\">") != 2:
                        nus.append(path.relative_to(REAL).as_posix())
        self.assertEqual(nus, [])

    def test_les_logos_montres_existent(self):
        for path in lm.pages(REAL):
            for src in re.findall(r'<span class="tm"><i><img src="((?:\.\./)*logos-equipes/[^"]+)"', path.read_text(encoding="utf-8")):
                with self.subTest(src=src):
                    self.assertTrue((REAL / src.replace("../", "")).is_file())

    def test_la_page_de_la_semaine_est_ornee(self):
        page = (REAL / "fr/matchs-de-la-semaine.html").read_text(encoding="utf-8")
        self.assertTrue(re.search(r'<span class="tm">', page), "aucune carte ornée")
        self.assertIn(".matchs .tm i.mono{", page)


if __name__ == "__main__":
    unittest.main()
