"""Tests de resultats.py : la carte de News du soir d'un grand événement, sans score ni nom d'équipe."""
from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import actualites as an
import resultats

REAL = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc)  # 23 h 30 à Paris, le samedi 7 novembre
KNOCKOUT = date(2026, 11, 3)


def match(summary: str, when: datetime, status: str = "CONFIRMED") -> dict:
    return {"summary": summary, "description": "", "url": "", "status": status, "start": when}


def at(day: int, hour: int = 20) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


class Etape(unittest.TestCase):
    """stage_of : l'étape d'un titre de match à venir, et rien d'autre."""

    def test_les_trois_etapes(self):
        self.assertEqual(resultats.stage_of("Quarterfinal 3: TBD vs TBD"), "quarter")
        self.assertEqual(resultats.stage_of("Semifinal 2: IG vs TBD"), "semi")
        self.assertEqual(resultats.stage_of("Grand Final: TBD vs TBD"), "final")
        self.assertEqual(resultats.stage_of("Final"), "final")

    def test_grand_final_n_est_pas_une_demie(self):
        self.assertEqual(resultats.stage_of("Grand Final"), "final")
        self.assertEqual(resultats.stage_of("Semifinals"), "semi")

    def test_sans_etape(self):
        self.assertIsNone(resultats.stage_of("Karmine Corp – T1"))
        self.assertIsNone(resultats.stage_of(""))


class Rapport(unittest.TestCase):
    """report : ce qu'il y a à dire d'un événement, à partir de son seul calendrier."""

    def setUp(self):
        self.calendar = [match("Gen.G – LYON", at(7, 18)), match("Dplus KIA – BLG", at(7, 21)),
                         match("Semifinal 1: TBD vs TBD", at(8, 22)), match("Grand Final: TBD vs TBD", at(14, 19))]

    def test_matchs_du_jour_et_etape_suivante(self):
        found = resultats.report(self.calendar, KNOCKOUT, date(2026, 11, 7), NOW)
        self.assertEqual(found, {"played": 2, "stage": "semi", "next_day": date(2026, 11, 8), "done": False})

    def test_rien_sans_match_joue_ce_jour(self):
        self.assertIsNone(resultats.report(self.calendar, KNOCKOUT, date(2026, 11, 6), NOW))

    def test_un_match_a_venir_le_jour_meme_ne_compte_pas(self):
        plus_tard = [*self.calendar, match("Top Esports – IG", at(7, 23, ))]
        found = resultats.report(plus_tard, KNOCKOUT, date(2026, 11, 7), NOW)
        self.assertEqual(found["played"], 2)  # 23 h UTC est après NOW : pas encore joué

    def test_matchs_avant_la_phase_finale_ecartes(self):
        poules = [match("A – B", at(1, 18)), *self.calendar]
        found = resultats.report(poules, KNOCKOUT, date(2026, 11, 1), NOW)
        self.assertIsNone(found)  # le 1er novembre est avant knockout_from : rien à dire

    def test_annules_ecartes(self):
        annule = [match("Gen.G – LYON", at(7, 18), status="CANCELLED"), match("Dplus KIA – BLG", at(7, 21))]
        found = resultats.report(annule, KNOCKOUT, date(2026, 11, 7), NOW)
        self.assertEqual(found["played"], 1)

    def test_tournoi_termine(self):
        fini = [match("Gen.G – LYON", at(7, 18))]
        found = resultats.report(fini, KNOCKOUT, date(2026, 11, 7), NOW)
        self.assertEqual(found, {"played": 1, "stage": None, "next_day": None, "done": True})

    def test_etape_suivante_sans_nom_d_etape(self):
        sans = [match("Gen.G – LYON", at(7, 18)), match("Karmine Corp – T1", at(9, 20))]
        found = resultats.report(sans, KNOCKOUT, date(2026, 11, 7), NOW)
        self.assertEqual((found["stage"], found["next_day"]), (None, date(2026, 11, 9)))


class Carte(unittest.TestCase):
    """make_item : une carte de News valide, dans les cinq langues, qui ne peut rien spoiler."""

    FOUND = {"played": 2, "stage": "semi", "next_day": date(2026, 11, 8), "done": False}

    def test_identifiant_date_et_lien(self):
        item = resultats.make_item("worlds-2026", self.FOUND, date(2026, 11, 7))
        self.assertEqual(item["id"], "worlds-2026-2026-11-07")
        self.assertEqual(item["date"], "2026-11-07")
        self.assertEqual(item["until"], "2026-11-10")
        self.assertEqual(item["link"], {"page": "worlds-2026"})

    def test_les_cinq_langues_tiennent_dans_les_limites(self):
        for found in (self.FOUND, {"played": 1, "stage": "final", "next_day": date(2026, 11, 14), "done": False},
                      {"played": 1, "stage": None, "next_day": None, "done": True}):
            item = resultats.make_item("worlds-2026", found, date(2026, 11, 7))
            for lang in an.LANGS:
                with self.subTest(lang=lang, done=found["done"]):
                    self.assertIn(lang, item)
                    self.assertTrue(1 <= len(item[lang]["title"]) <= 80, item[lang]["title"])
                    self.assertTrue(1 <= len(item[lang]["text"]) <= 280, item[lang]["text"])
                    self.assertNotIn("<", item[lang]["title"] + item[lang]["text"])

    def test_singulier_et_pluriel(self):
        un = resultats.make_item("worlds-2026", {**self.FOUND, "played": 1}, date(2026, 11, 7))
        self.assertIn("1 match joué", un["fr"]["title"])
        self.assertNotIn("(s)", un["fr"]["title"])
        plusieurs = resultats.make_item("worlds-2026", self.FOUND, date(2026, 11, 7))
        self.assertIn("2 matchs joués", plusieurs["fr"]["title"])

    def test_jamais_d_equipe_ni_de_score(self):
        """Le cœur du robot : le calendrier nomme les qualifiés (« Semifinal 2: IG vs TBD »), la carte jamais."""
        item = resultats.make_item("worlds-2026", self.FOUND, date(2026, 11, 7))
        written = " ".join(item[lang]["title"] + " " + item[lang]["text"] for lang in an.LANGS)
        for name in ("IG", "Gen.G", "LYON", "T1", "Karmine", "TBD", "vs"):
            self.assertNotIn(name, written)
        self.assertIsNone(re.search(r"\b\d{1,2}\s*[–-]\s*\d{1,2}\b", written), "un score s'est glissé dans la carte")


class Fusion(unittest.TestCase):
    """merge : une carte déjà écrite ce soir est remplacée, jamais dupliquée."""

    def test_nouvelle_carte_en_tete(self):
        anciennes = [{"id": "vieux"}, {"id": "encore-plus-vieux"}]
        fusion = resultats.merge(anciennes, [{"id": "neuf"}])
        self.assertEqual([item["id"] for item in fusion], ["neuf", "vieux", "encore-plus-vieux"])

    def test_meme_identifiant_remplace_sur_place(self):
        anciennes = [{"id": "vieux"}, {"id": "worlds-2026-2026-11-07", "fr": "première version"}]
        fusion = resultats.merge(anciennes, [{"id": "worlds-2026-2026-11-07", "fr": "seconde version"}])
        self.assertEqual([item["id"] for item in fusion], ["vieux", "worlds-2026-2026-11-07"])
        self.assertEqual(fusion[1]["fr"], "seconde version")


class Noms(unittest.TestCase):
    def test_noms_comme_dans_matchs(self):
        """NAMES recopie EVENTS de matchs.py (qu'on ne peut pas importer : c'est un script) ; les deux doivent rester d'accord."""
        source = (Path(__file__).resolve().parent / "matchs.py").read_text(encoding="utf-8")
        found = re.search(r"^EVENTS = (\{.*?^\})", source, re.M | re.S)
        self.assertIsNotNone(found)
        events = ast.literal_eval(found.group(1))
        self.assertEqual(resultats.NAMES, {slug: name for slug, (name, _) in events.items()})


class Bout(unittest.TestCase):
    """build et main : du calendrier au fichier, sans réseau (fetch remplacé) et sans toucher au vrai dépôt."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "news").mkdir()
        for slug in ("worlds-2026", "esl-pro-league"):  # load_news vérifie que chaque événement a sa page anglaise
            (self.root / f"{slug}-en.html").write_text("<!doctype html>", encoding="utf-8")
        self.news = {"events": {"worlds-2026": {"knockout_from": "2026-11-03", "game": "league-of-legends"},
                                "esl-pro-league": {"knockout_from": None, "game": "counter-strike-2"}},
                     "items": [{"id": "ancienne", "date": "2026-10-29",
                                **{lang: {"title": "Ancienne", "text": "Carte déjà là."} for lang in an.LANGS}}]}
        self._write()
        self.addCleanup(self.dir.cleanup)

    def _write(self):
        (self.root / resultats.NEWS).write_text(json.dumps(self.news, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _fetch(self, calendar):
        return lambda slug: calendar if slug == "worlds-2026" else None

    def test_ecrit_une_carte_et_garde_les_anciennes(self):
        calendar = [match("Gen.G – LYON", at(7, 18)), match("Semifinal 1: TBD vs TBD", at(8, 22))]
        code = resultats.main([], self.root, NOW, self._fetch(calendar))
        self.assertEqual(code, 0)
        written = json.loads((self.root / resultats.NEWS).read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in written["items"]], ["worlds-2026-2026-11-07", "ancienne"])
        self.assertEqual(written["events"], self.news["events"])  # events n'est pas touché

    def test_essai_n_ecrit_rien(self):
        avant = (self.root / resultats.NEWS).read_text(encoding="utf-8")
        calendar = [match("Gen.G – LYON", at(7, 18))]
        self.assertEqual(resultats.main(["--essai"], self.root, NOW, self._fetch(calendar)), 0)
        self.assertEqual((self.root / resultats.NEWS).read_text(encoding="utf-8"), avant)

    def test_sans_match_joue_rien_n_est_ecrit(self):
        avant = (self.root / resultats.NEWS).read_text(encoding="utf-8")
        self.assertEqual(resultats.main([], self.root, NOW, self._fetch([match("A – B", at(9, 20))])), 0)
        self.assertEqual((self.root / resultats.NEWS).read_text(encoding="utf-8"), avant)

    def test_calendrier_indisponible_saute_l_evenement(self):
        avant = (self.root / resultats.NEWS).read_text(encoding="utf-8")
        self.assertEqual(resultats.main([], self.root, NOW, lambda slug: None), 0)
        self.assertEqual((self.root / resultats.NEWS).read_text(encoding="utf-8"), avant)

    def test_deux_passages_dans_la_soiree_ne_font_qu_une_carte(self):
        un = [match("Gen.G – LYON", at(7, 18)), match("Semifinal 1: TBD vs TBD", at(8, 22))]
        deux = [*un, match("Dplus KIA – BLG", at(7, 21))]
        resultats.main([], self.root, NOW, self._fetch(un))
        resultats.main([], self.root, NOW, self._fetch(deux))
        written = json.loads((self.root / resultats.NEWS).read_text(encoding="utf-8"))
        ids = [item["id"] for item in written["items"]]
        self.assertEqual(ids, ["worlds-2026-2026-11-07", "ancienne"])
        self.assertIn("2 matchs joués", written["items"][0]["fr"]["title"])  # la seconde version a remplacé la première


@unittest.skipUnless((REAL / resultats.NEWS).is_file(), "news/news.json absent")
class VraiFichier(unittest.TestCase):
    def test_les_vrais_evenements_sont_tous_nommes(self):
        news = json.loads((REAL / resultats.NEWS).read_bytes().decode("utf-8"))
        for slug in news.get("events", {}):
            self.assertIn(slug, resultats.NAMES, f"événement « {slug} » sans nom dans resultats.NAMES")


if __name__ == "__main__":
    unittest.main()
