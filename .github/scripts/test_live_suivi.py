"""Tests de live_suivi.py : les fins de match notées d'après le flux de résultats, et le fichier suivi/live.json."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import live_suivi

NOW = datetime(2026, 11, 5, 15, 40, tzinfo=timezone.utc)


def event(mid: str | None = "1713105", hours: float = -2, summary: str = "T1 – Cheeseburger") -> dict:
    start = NOW + timedelta(hours=hours)
    url = f"https://esportly.eu/match.html?id={mid}" if mid else "https://esportly.eu/"
    return {"UID": f"match-{mid}@test", "SUMMARY": summary, "DESCRIPTION": "Overwatch · OCS · Korea Stage 3 2026", "URL": url,
            "start": start, "end": start + timedelta(hours=2)}


def result(mid: int = 1713105, score: list | None = None, teams: list | None = None) -> dict:
    return {"id": mid, "date": "2026-11-05T13:40:00Z", "game": "Overwatch", "league": "OCS", "serie": "x",
            "teams": ["T1", "Cheeseburger"] if teams is None else teams, "score": [3, 0] if score is None else score}


class NewFinals(unittest.TestCase):
    def test_un_resultat_confirme_la_fin(self):
        found = live_suivi.new_finals([event()], [result()], NOW)
        self.assertEqual(found, {"1713105": {"vu": "2026-11-05T15:40:00+00:00", "equipes": ["T1", "Cheeseburger"], "score": [3, 0]}})

    def test_seuls_les_matchs_de_la_page(self):
        self.assertEqual(live_suivi.new_finals([event()], [result(999)], NOW), {})

    def test_deja_note_ne_change_pas(self):
        known = {"1713105": {"vu": "2026-11-05T14:00:00+00:00", "equipes": ["T1", "Cheeseburger"], "score": [3, 0]}}
        self.assertEqual(live_suivi.new_finals([event()], [result()], NOW, known), {})

    def test_score_complete_apres_coup(self):
        known = {"1713105": {"vu": "2026-11-05T14:00:00+00:00", "equipes": ["T1", "Cheeseburger"], "score": None}}
        found = live_suivi.new_finals([event()], [result()], NOW, known)
        self.assertEqual(found, {"1713105": {"vu": "2026-11-05T14:00:00+00:00", "equipes": ["T1", "Cheeseburger"], "score": [3, 0]}})  # heure du constat gardée
        self.assertEqual(live_suivi.new_finals([event()], [result(score=[None, 1])], NOW, known), {})  # toujours sans score : rien à changer

    def test_match_pas_commence_ignore(self):
        self.assertEqual(live_suivi.new_finals([event(hours=3)], [result()], NOW), {})

    def test_score_incomplet(self):
        found = live_suivi.new_finals([event()], [result(score=[None, 2])], NOW)
        self.assertEqual(found["1713105"]["score"], None)  # fini, mais pas de score à montrer
        self.assertEqual(live_suivi.new_finals([event()], [result(score=[])], NOW)["1713105"]["score"], None)

    def test_sans_deux_equipes_ignore(self):
        self.assertEqual(live_suivi.new_finals([event()], [result(teams=["T1"])], NOW), {})
        self.assertEqual(live_suivi.new_finals([event()], [{"id": 1713105, "teams": ["A", "B"]}], NOW), {})  # pas de score du tout

    def test_resultat_mal_forme_ignore(self):
        for bad in ({}, {"id": "x", "teams": ["A", "B"], "score": [1, 0]}, {"id": 1713105, "teams": "AB", "score": [1, 0]}):
            self.assertEqual(live_suivi.new_finals([event()], [bad], NOW), {})

    def test_match_sans_numero(self):
        self.assertEqual(live_suivi.new_finals([event(None)], [result()], NOW), {})


class Store(unittest.TestCase):
    def test_ecrire_puis_lire(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suivi" / "live.json"
            fins = {"1713105": {"vu": "2026-11-05T15:40:00+00:00", "equipes": ["T1", "Cheeseburger"], "score": [3, 0]}}
            live_suivi.save(path, [event(), event("5", 1, "X <&> Y")], fins)
            matchs, back = live_suivi.load(path)
            self.assertEqual(back, fins)
            self.assertEqual(matchs, [event(), event("5", 1, "X <&> Y")])  # dates relues avec leur fuseau
            self.assertEqual(path.read_text(encoding="utf-8"), path.read_text(encoding="utf-8").rstrip("\n") + "\n")
            live_suivi.save(path, matchs, fins)
            again = path.read_text(encoding="utf-8")
            live_suivi.save(path, matchs, fins)
            self.assertEqual(path.read_text(encoding="utf-8"), again)  # écriture stable : pas de commit pour rien

    def test_fichier_absent_ou_abime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "live.json"
            self.assertEqual(live_suivi.load(path), ([], {}))
            path.write_text("pas du json", encoding="utf-8")
            self.assertEqual(live_suivi.load(path), ([], {}))
            path.write_text('{"matchs": [{"SUMMARY": "sans heure"}], "fins": []}', encoding="utf-8")
            self.assertEqual(live_suivi.load(path), ([], {}))

    def test_jour_decrit_par_le_fichier(self):
        """day_of : ce que le robot de l'heure lit pour savoir qu'on a changé de jour (et qu'il doit refaire la journée)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "live.json"
            self.assertIsNone(live_suivi.day_of(path))  # fichier absent
            live_suivi.save(path, [], {}, "2026-11-05")
            self.assertEqual(live_suivi.day_of(path), "2026-11-05")
            live_suivi.save(path, [], {})
            self.assertIsNone(live_suivi.day_of(path))  # sans jour : le robot refera la journée, jamais l'inverse
            path.write_text("pas du json", encoding="utf-8")
            self.assertIsNone(live_suivi.day_of(path))

    def test_fins_gardees_seulement_pour_les_matchs_du_jour(self):
        fins = {"1": {"vu": "x", "equipes": ["A", "B"], "score": [1, 0]}, "2": {"vu": "x", "equipes": ["C", "D"], "score": None}}
        self.assertEqual(live_suivi.keep_known(fins, [event("2")]), {"2": fins["2"]})


if __name__ == "__main__":
    unittest.main()
