"""Suivi de la page Live : noter la fin d'un match quand le flux de résultats la confirme, et garder ce qu'il faut entre deux passages.

Le relais eSportly publie les résultats (`/calendrier/resultats/semaine.json` : `id` du match, deux équipes, `score`) mais pas l'état
« en cours » ni l'heure de fin : sa `date` est le coup d'envoi du match. Un score présent dit donc seulement « ce match est fini » ;
le robot note l'heure à laquelle il l'a constaté (`vu`), rien n'est déduit de l'horloge ni d'un autre site.

`suivi/live.json` (hors site, `.assetsignore`) garde les matchs du jour fabriqués le matin par matchs.py (`matchs`, de quoi refabriquer
les pages sans relire les calendriers) et les fins notées (`fins`, `{numéro du match: {vu, equipes, score}}`, `score` None quand le flux
n'en donne pas). Le robot du matin l'écrit, le robot de l'heure (`matchs.py --live`) le complète.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import live

PATH = Path(__file__).resolve().parents[2] / "suivi" / "live.json"
KEYS = ("UID", "SUMMARY", "DESCRIPTION", "URL")


def _score(raw) -> list[int] | None:
    """Le score à deux nombres entiers, sinon None (fini, mais sans score à montrer)."""
    ok = isinstance(raw, list) and len(raw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in raw)
    return list(raw) if ok else None


def new_finals(matchs: list[dict], results: list[dict], now: datetime, known: dict[str, dict] | None = None) -> dict[str, dict]:
    """Les fins à noter : un résultat du flux dont le numéro est celui d'un match de la page, que ce match a commencé (un résultat ne
    peut pas précéder le coup d'envoi), qui nomme deux équipes et porte un `score`, et que `known` (les fins déjà notées) n'a pas encore
    (ou n'a notée que sans score : le score est alors complété, l'heure du constat `vu` reste la première)."""
    by_id = {mid: event for event in matchs if (mid := live.match_id(event))}
    found: dict[str, dict] = {}
    for item in results:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool):
            continue
        mid, teams = str(item["id"]), item.get("teams")
        event = by_id.get(mid)
        if (event is None or event["start"] > now or "score" not in item or not isinstance(item["score"], list)
                or not isinstance(teams, list) or len(teams) != 2 or not all(isinstance(n, str) and n for n in teams)):
            continue
        old, score = (known or {}).get(mid), _score(item["score"])
        if old is not None and (old.get("score") is not None or score is None):
            continue  # déjà noté : une fin ne change plus, sauf pour recevoir un score qui manquait
        found[mid] = {"vu": old["vu"] if old else now.isoformat(), "equipes": list(teams), "score": score}
    return found


def keep_known(fins: dict[str, dict], matchs: list[dict]) -> dict[str, dict]:
    """Les fins déjà notées qui concernent encore un match de la page."""
    ids = {live.match_id(event) for event in matchs}
    return {mid: fin for mid, fin in fins.items() if mid in ids}


def day_of(path: Path) -> str | None:
    """Le jour (jour de Paris, AAAA-MM-JJ) que décrit le fichier, None s'il manque ou ne le dit pas. Le robot de l'heure s'en sert
    pour savoir qu'on a changé de jour : les « matchs du jour » gardés là sont alors ceux d'hier, et toute la journée est à refaire."""
    try:
        return json.loads(path.read_bytes().decode("utf-8")).get("jour")
    except (OSError, ValueError, AttributeError):
        return None


def save(path: Path, matchs: list[dict], fins: dict[str, dict], jour: str | None = None) -> None:
    """Écrit le jour décrit, les matchs et les fins ; une écriture stable (même contenu, mêmes octets) pour ne rien commiter quand rien n'a changé."""
    data = {"jour": jour,
            "matchs": [{**{key: event[key] for key in KEYS if key in event}, "start": event["start"].isoformat(), "end": event["end"].isoformat()}
                       for event in matchs],
            "fins": {mid: fins[mid] for mid in sorted(fins)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def load(path: Path) -> tuple[list[dict], dict[str, dict]]:
    """(matchs, fins) du fichier ; ([], {}) s'il manque, n'est pas du JSON ou n'a pas la forme attendue (le robot du matin le refait)."""
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
        matchs = [{**{key: raw[key] for key in KEYS if key in raw}, "start": datetime.fromisoformat(raw["start"]),
                   "end": datetime.fromisoformat(raw["end"])} for raw in data["matchs"]]
        fins = data["fins"]
        if not isinstance(fins, dict):
            raise ValueError("fins")
        return matchs, fins
    except (OSError, ValueError, KeyError, TypeError):
        return [], {}
