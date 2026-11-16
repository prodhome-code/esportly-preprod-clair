"""Tests du contrôle des titles et métadescriptions : py -3.13 -m unittest discover -s .claude/skills/titres-seo/scripts"""
import csv
import io
import tempfile
import unittest
from pathlib import Path

import controle

BRAND = ""  # plus de marque en suffixe depuis le 31/10/2026


def row(**fields):
    base = {"URL": "https://esportly.eu/blog-fr/valorant", "Langue": "fr", "TITLE": "Ancien title",
            "DESCRIPTION": "Ancienne description.", "New TITLE": "", "nb car title": "", "New DESCRIPTION": "",
            "nb car description": "", "Mots-clés retenus": "", "_line": 2}
    base.update(fields)
    return base


def title(words):
    return words + BRAND


class Title(unittest.TestCase):
    def test_bon_title(self):
        t = title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier")
        self.assertTrue(55 <= len(t) <= 63, len(t))
        self.assertEqual(controle.check_title(row(**{"New TITLE": t, "nb car title": str(len(t))})), [])

    def test_longueur(self):
        self.assertIn("longueur 15 hors de 55-63", controle.check_title(row(**{"New TITLE": title("Esport Valorant")})))

    def test_marque_en_suffixe_interdite(self):
        t = "Esport Valorant : jeu, scène pro, VCT, Masters – eSportly"
        self.assertIn("finit par « – eSportly » (marque en suffixe interdite)", controle.check_title(row(**{"New TITLE": t})))

    def test_marque_dans_le_title(self):
        t = "Esport Valorant eSportly : jeu, scène pro, VCT et calendrier"
        self.assertIn("marque dans le title (réservée aux accueils)", controle.check_title(row(**{"New TITLE": t})))

    def test_mot_repete_sauf_mots_vides(self):
        t = title("Esport Valorant : le jeu, la scène esport, VCT et le calendrier")
        issues = controle.check_title(row(**{"New TITLE": t}))
        self.assertIn("mot répété : esport", issues)
        self.assertNotIn("mot répété : le", issues)

    def test_libelle_a_mot_double(self):
        t = title("Mobile Legends: Bang Bang score en direct et alertes")
        self.assertNotIn("mot répété : bang", controle.check_title(row(**{"New TITLE": t})))

    def test_mots_vides_par_langue(self):
        t = title("Valorant esports: the game, the pro scene and the schedule")
        self.assertNotIn("mot répété : the", controle.check_title(row(Langue="en", **{"New TITLE": t})))

    def test_mots_hors_page_et_mots_cles(self):
        r = row(**{"New TITLE": title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier"),
                   "Mots-clés retenus": "esport valorant (1900); vct (720)"})
        issues = controle.check_title(r)
        self.assertIn("absent de l'URL, de la page et des mots-clés : jeu", issues)
        self.assertNotIn("absent de l'URL, de la page et des mots-clés : vct", issues)

    def test_mots_de_l_ancien_title_et_description_admis(self):
        r = row(TITLE="Esport Valorant : le jeu et sa scène pro", DESCRIPTION="Le calendrier du VCT et des Masters.",
                **{"New TITLE": title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier"),
                   "Mots-clés retenus": "esport valorant (1900)"})
        self.assertEqual([i for i in controle.check_title(r) if "absent" in i], [])

    def test_interdits(self):
        issues = controle.check_title(row(**{"New TITLE": title("Découvrez Valorant : le meilleur guide esport, VCT, Masters !")}))
        self.assertIn("interdit : découvrez", issues)
        self.assertIn("interdit : meilleur", issues)
        self.assertIn("interdit : !", issues)
        self.assertIn("interdit : —", controle.check_title(row(**{"New TITLE": title("Valorant — scène pro et calendrier")})))

    def test_interdits_en(self):
        self.assertIn("interdit : discover", controle.check_title(row(Langue="en", **{"New TITLE": title("Discover Valorant esports")})))

    def test_compteur_faux(self):
        t = title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier")
        self.assertIn(f"nb car title indique 50, le title en fait {len(t)}",
                      controle.check_title(row(**{"New TITLE": t, "nb car title": "50"})))

    def test_vide(self):
        self.assertEqual(controle.check_title(row()), ["New TITLE vide"])


class Description(unittest.TestCase):
    GOOD = ("Comment fonctionne l'esport Valorant ? Le jeu, le VCT, les Masters et Champions, où regarder les matchs, "
            "avec alerte avant chaque match dans eSportly.")

    def test_bonne_description(self):
        self.assertTrue(120 <= len(self.GOOD) <= 155, len(self.GOOD))
        self.assertEqual(controle.check_description(row(**{"New DESCRIPTION": self.GOOD, "nb car description": str(len(self.GOOD))})), [])

    def test_longueur(self):
        self.assertIn("longueur 22 hors de 120-155", controle.check_description(row(**{"New DESCRIPTION": "Trop courte, vraiment."})))

    def test_fin_par_un_point(self):
        d = self.GOOD[:-1]
        self.assertIn("ne finit pas par un point", controle.check_description(row(**{"New DESCRIPTION": d})))

    def test_interdits(self):
        d = "Découvrez le meilleur guide esport Valorant — le jeu, le VCT, les Masters et Champions, et où regarder les matchs chaque semaine !"
        issues = controle.check_description(row(**{"New DESCRIPTION": d}))
        for bad in ("découvrez", "meilleur", "—", "!"):
            self.assertIn(f"interdit : {bad}", issues)

    def test_compteur_faux(self):
        self.assertIn(f"nb car description indique 10, la description en fait {len(self.GOOD)}",
                      controle.check_description(row(**{"New DESCRIPTION": self.GOOD, "nb car description": "10"})))

    def test_vide(self):
        self.assertEqual(controle.check_description(row()), ["New DESCRIPTION vide"])


class Fichier(unittest.TestCase):
    def write(self, rows):
        path = Path(tempfile.mkdtemp()) / "titres.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=controle.COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        return str(path)

    def test_doublons_et_tri(self):
        t = title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier")
        d = Description.GOOD
        rows = [dict.fromkeys(controle.COLUMNS, "") for _ in range(2)]
        rows[0].update({"URL": "https://esportly.eu/blog-fr/valorant", "Langue": "fr", "New TITLE": t, "New DESCRIPTION": d})
        rows[1].update({"URL": "https://esportly.eu/blog-fr/dota-2", "Langue": "fr", "New TITLE": t, "New DESCRIPTION": d})
        issues = controle.check_file(self.write(rows))
        self.assertEqual([(i.line, i.message) for i in issues],
                         [(2, "description identique à la ligne 3"), (2, "title identique à la ligne 3"),
                          (3, "description identique à la ligne 2"), (3, "title identique à la ligne 2")])

    def test_colonne_manquante(self):
        path = Path(tempfile.mkdtemp()) / "titres.csv"
        path.write_text("URL;TITLE\nhttps://esportly.eu/;x\n", encoding="utf-8")
        with self.assertRaises(controle.CsvError) as cm:
            controle.check_file(str(path))
        self.assertEqual(str(cm.exception), "colonne manquante : Langue, New TITLE, New DESCRIPTION")

    def test_langue_inconnue(self):
        rows = [dict.fromkeys(controle.COLUMNS, "")]
        rows[0].update({"URL": "https://esportly.eu/x", "Langue": "it", "New TITLE": title("Esport Valorant : jeu, scène pro, VCT, Masters et calendrier"),
                        "New DESCRIPTION": Description.GOOD})
        self.assertIn("langue inconnue : it (fr, en, es, de, pt-BR)", [i.message for i in controle.check_file(self.write(rows))])


if __name__ == "__main__":
    unittest.main()
