"""Tests du bloc « matchs et résultats » des pages de jeux.

matchs.py est un script (il fait tout son travail à l'import) : on ne peut pas appeler ses fonctions ici. Ces tests regardent donc
ce qu'il a écrit dans l'arbre de travail, comme les tests du menu du site le font pour les pages publiées.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import site_chrome as sc

REAL = Path(__file__).resolve().parents[2]
START, END = "<!-- jeu-matchs -->", "<!-- /jeu-matchs -->"
BLOCK = re.compile(re.escape(START) + "(.*?)" + re.escape(END), re.S)
# Les deux titres du bloc, dans chaque langue : ceux des pages d'événements (aucun texte nouveau à traduire).
HEADS = {"en": ("Upcoming matches", "Results from the last 7 days"), "fr": ("Prochains matchs", "Résultats des 7 derniers jours"),
         "es": ("Próximos partidos", "Resultados de los últimos 7 días"), "de": ("Nächste Matches", "Ergebnisse der letzten 7 Tage"),
         "pt-BR": ("Próximas partidas", "Resultados dos últimos 7 dias")}


def page(lang: str, game: str) -> str | None:
    path = REAL / f"{sc.GAME_DIRS[lang]}/{game}.html"
    return path.read_text(encoding="utf-8") if path.is_file() else None


@unittest.skipUnless((REAL / "fr/jeux/valorant.html").is_file(), "pages de jeux absentes")
class BlocDesJeux(unittest.TestCase):
    def test_les_14_jeux_l_ont_dans_les_5_langues(self):
        for game in sc.GAMES:
            for lang in sc.GAME_DIRS:
                with self.subTest(game=game, lang=lang):
                    text = page(lang, game)
                    self.assertIsNotNone(text, f"{game} ({lang}) : page absente")
                    found = BLOCK.search(text)
                    self.assertIsNotNone(found, f"{game} ({lang}) : bloc absent")
                    self.assertEqual(text.count(START), 1)  # un seul bloc, jamais empilé d'un passage à l'autre

    def test_les_deux_titres_dans_la_langue(self):
        for lang, (up, results) in HEADS.items():
            with self.subTest(lang=lang):
                inside = BLOCK.search(page(lang, "league-of-legends")).group(1)
                self.assertIn(f'<h2 class="jour">{up}</h2>', inside)
                self.assertIn(f'<h2 class="jour">{results}</h2>', inside)

    def test_le_bloc_precede_son_ancre(self):
        """Le bloc se glisse avant le calendrier du jeu (ou, à défaut, avant le lien du guide) : jamais à la fin de la page."""
        for game in sc.GAMES:
            with self.subTest(game=game):
                text = page("fr", game)
                anchor = next((found for found in ("<!-- calendrier-jeu -->", "<!-- blog-guide -->") if found in text), None)
                self.assertIsNotNone(anchor, f"{game} : aucune ancre connue")
                self.assertLess(text.index(START), text.index(anchor))

    def test_les_scores_restent_floutes(self):
        """Un résultat affiché ici l'est comme ailleurs : écrit en clair mais flouté par son style en ligne."""
        with_results = [game for game in sc.GAMES if "<li><details>" in (BLOCK.search(page("fr", game)).group(1))]
        self.assertTrue(with_results, "aucun jeu n'a de résultat : le flux de la semaine était-il vide ?")
        for game in with_results:
            with self.subTest(game=game):
                inside = BLOCK.search(page("fr", game)).group(1)
                self.assertIn('class="score" style="filter:blur(', inside)
                self.assertNotIn('<p class="score">', inside)  # jamais un score en clair

    def test_le_style_des_listes_est_sur_la_page(self):
        for game in ("league-of-legends", "starcraft-2"):
            with self.subTest(game=game):
                text = page("fr", game)
                self.assertIn(".matchs{", text)
                self.assertIn(".resultats{", text)
                self.assertEqual(text.count(".resultats{list-style:none"), 1)  # le style n'est ajouté qu'une fois

    def test_un_jeu_sans_match_le_dit(self):
        """Rien n'est inventé : sans match ni résultat, le bloc affiche les phrases prévues plutôt qu'une liste vide."""
        vides = [game for game in sc.GAMES if "<ul class=\"matchs\">" not in BLOCK.search(page("fr", game)).group(1)]
        for game in vides:
            with self.subTest(game=game):
                inside = BLOCK.search(page("fr", game)).group(1)
                self.assertIn("Aucun match", inside)


if __name__ == "__main__":
    unittest.main()
