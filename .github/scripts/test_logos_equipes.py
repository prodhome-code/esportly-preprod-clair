"""Tests des logos sur les listes d'équipes."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import logos_equipes as le

REAL = Path(__file__).resolve().parents[2]
KNOWN = {"karmine-corp", "g2-esports", "t1"}
LOGOS = {"karmine-corp": "134078.webp", "g2-esports": "115.webp"}  # t1 n'a pas de logo local : son nom reste seul

NAV = ('<h2>Les équipes à suivre</h2><nav class="others" aria-label="Équipes">'
       '<a href="../../fr/equipes/karmine-corp.html">Karmine Corp</a>'
       '<a href="../../fr/equipes/g2-esports.html">G2 Esports</a>'
       '<a href="../../fr/equipes/t1.html">T1</a></nav>')
JEUX = ('<nav class="others" aria-label="Les autres jeux">'
        '<a href="../../fr/jeux/valorant.html">Valorant</a>'
        '<a href="../../fr/jeux/dota-2.html">Dota 2</a></nav>')


class Render(unittest.TestCase):
    def rendu(self, page: str, rel: str = "fr/jeux/valorant.html") -> str:
        return le.render(page, rel, KNOWN, LOGOS)

    def test_une_liste_d_equipes_devient_des_vignettes(self):
        done = self.rendu(NAV)
        self.assertIn('<ul class="teams" aria-label="Équipes">', done)
        self.assertNotIn("<nav", done)
        self.assertIn('<i class="tl"><img src="../../logos-equipes/134078.webp"', done)
        self.assertIn("<span>Karmine Corp</span>", done)

    def test_les_liens_sont_gardes(self):
        done = self.rendu(NAV)
        self.assertIn('<a href="../../fr/equipes/karmine-corp.html">', done)
        self.assertEqual(len(re.findall(r"<li>", done)), 3)

    def test_une_equipe_sans_logo_garde_son_nom(self):
        done = self.rendu(NAV)
        self.assertIn('<a href="../../fr/equipes/t1.html"><span>T1</span></a>', done)

    def test_une_liste_de_jeux_n_est_pas_touchee(self):
        self.assertEqual(self.rendu(JEUX), JEUX)

    def test_une_liste_inconnue_n_est_pas_touchee(self):
        page = '<nav class="others" aria-label="Équipes"><a href="../../fr/equipes/inconnue.html">Inconnue</a><a href="../../fr/equipes/t1.html">T1</a></nav>'
        self.assertEqual(self.rendu(page), page)

    def test_la_profondeur_de_la_page(self):
        """Le chemin du logo dépend de l'endroit où est la page : une page d'équipe est deux dossiers plus bas."""
        voisines = '<nav class="others" aria-label="D\'autres équipes"><a href="g2-esports.html">G2 Esports</a><a href="t1.html">T1</a></nav>'
        done = le.render(voisines, "fr/equipes/karmine-corp.html", KNOWN, LOGOS)
        self.assertIn('src="../../logos-equipes/115.webp"', done)
        done_racine = le.render(NAV.replace("../../", ""), "teams.html", KNOWN, LOGOS)
        self.assertIn('src="logos-equipes/134078.webp"', done_racine)

    def test_rejouable(self):
        once = self.rendu(NAV)
        self.assertEqual(self.rendu(once), once)

    def test_une_seule_entree_reste_un_lien(self):
        page = '<nav class="others" aria-label="Équipes"><a href="../../fr/equipes/t1.html">T1</a></nav>'
        self.assertEqual(self.rendu(page), page)


@unittest.skipUnless((REAL / "fr/jeux/valorant.html").is_file(), "site absent")
class Site(unittest.TestCase):
    def test_les_logos_sont_dans_le_depot(self):
        for slug, name in le.logos(REAL).items():
            with self.subTest(slug=slug):
                self.assertTrue((REAL / "logos-equipes" / name).is_file())

    def test_les_pages_de_jeux_montrent_les_logos(self):
        page = (REAL / "fr/jeux/valorant.html").read_text(encoding="utf-8")
        found = re.search(r'<ul class="teams" aria-label="Équipes">(.*?)</ul>', page, re.S)
        self.assertIsNotNone(found, "la liste des équipes à suivre n'est pas en vignettes")
        self.assertIn("logos-equipes/", found.group(1))

    def test_plus_aucune_liste_d_equipes_en_texte(self):
        """Aucune page ne garde une liste d'équipes en simples liens : le site est cohérent d'un bout à l'autre."""
        known = {path.stem for path in (REAL / "equipes").glob("*.json")} - {"index-pages", "minces"}
        restants = []
        for path in le.pages(REAL):
            for _, inside in le.NAV.findall(path.read_text(encoding="utf-8")):
                links = le.LINK.findall(inside)
                slugs = [le.team_slug(href) for href, _ in links]
                if len(links) > 1 and all(slug in known for slug in slugs):
                    restants.append(path.relative_to(REAL).as_posix())
        self.assertEqual(restants, [])

    def test_le_style_est_vertical(self):
        page = (REAL / "fr/equipes.html").read_text(encoding="utf-8")
        self.assertIn("flex-direction:column;text-align:center", page, "le nom doit être sous le logo")


if __name__ == "__main__":
    unittest.main()
