"""News du soir : dire que la phase finale d'un grand événement a avancé, sans jamais publier un score ni un nom de vainqueur.

Le site savait annoncer le début d'une phase finale (« les quarts commencent le 3 novembre ») mais rien après : les News restaient
figées des jours entiers pendant qu'un tournoi se jouait. Ce robot écrit, le soir, une carte par événement dont des matchs de phase
finale ont été joués dans la journée : combien de matchs, et quelle est la prochaine étape.

**Rien de ce qu'il écrit ne peut spoiler.** Jamais de score, jamais un nom d'équipe : le calendrier du relais nomme pourtant les
qualifiés dans les titres des matchs à venir (« Semifinal 2: IG vs TBD »), et un seul de ces noms dirait qui a gagné son quart.
Le robot ne lit donc de ces titres que l'étape (quart, demie, finale), jamais les équipes. Les scores restent là où ils sont :
cachés derrière un clic sur la page de chaque match.

Il ne devine rien : il ne compte que des matchs dont le coup d'envoi est passé, lus dans le calendrier de l'événement, et il
n'écrit rien pour une journée sans match de phase finale. Une carte déjà écrite pour un événement et un jour est remplacée, jamais
dupliquée : le robot peut tourner plusieurs fois dans la soirée.

    py -3.13 .github/scripts/resultats.py           # écrit news/news.json (puis actualites.py refabrique les pages)
    py -3.13 .github/scripts/resultats.py --essai   # dit ce qu'il écrirait, sans rien écrire

Le réseau n'arrive que par `fetch` (actualites.read_events), que les tests remplacent : un événement dont le calendrier ne répond
pas est simplement sauté. Une requête par événement en phase finale, soit zéro à trois : c'est le même calendrier que celui que
« Matchs du jour » lit déjà chaque matin.
"""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import actualites as an

ROOT = Path(__file__).resolve().parents[2]
NEWS = "news/news.json"
KEEP = timedelta(days=3)  # une carte du soir reste affichée 3 jours

# Noms des grands événements, repris de EVENTS dans matchs.py (test_noms_comme_dans_matchs les compare).
NAMES = {"worlds-2026": "Worlds 2026", "vct-champions-2026": "VCT Champions 2026", "esl-pro-league": "ESL Pro League"}

# L'étape d'un match à venir, lue dans son titre. Seule l'étape est retenue : ce qui suit (« : IG vs TBD ») nommerait un qualifié,
# donc le vainqueur d'un match déjà joué. L'ordre compte : « Grand Final » ne doit pas être pris pour une demi-finale.
STAGES = (("final", re.compile(r"\b(?:grand\s+)?finals?\b", re.I)),
          ("semi", re.compile(r"\bsemi-?finals?\b", re.I)),
          ("quarter", re.compile(r"\bquarter-?finals?\b", re.I)))

# Textes des cartes, par langue (`title_one` : un seul match joué ; `title` : plusieurs). {event} : nom de l'événement ;
# {n} : nombre de matchs joués ; {day} : jour en toutes lettres ;
# {stage} : l'étape suivante (STAGE_NAMES). Jamais d'équipe, jamais de score : voir l'en-tête du fichier.
TEXTS = {
    "fr": dict(title_one="{event} : 1 match joué {day}", title="{event} : {n} matchs joués {day}", title_done="{event} : le tableau final est allé à son terme",
               next_stage="Le tableau final avance. Prochaine étape : {stage}, {day}.",
               next_plain="Le tableau final avance. Prochains matchs {day}.",
               done="Plus aucun match à venir dans le tableau final.",
               tail=" Sur eSportly, les scores restent cachés : tu les révèles quand tu veux."),
    "en": dict(title_one="{event}: 1 match played {day}", title="{event}: {n} matches played {day}", title_done="{event}: the knockout bracket has run its course",
               next_stage="The bracket moves on. Next up: {stage}, {day}.",
               next_plain="The bracket moves on. Next matches {day}.",
               done="No match left to play in the bracket.",
               tail=" On eSportly, scores stay hidden: you reveal them whenever you want."),
    "es": dict(title_one="{event}: 1 partido jugado {day}", title="{event}: {n} partidos jugados {day}", title_done="{event}: el cuadro final ha llegado a su fin",
               next_stage="El cuadro final avanza. Siguiente etapa: {stage}, {day}.",
               next_plain="El cuadro final avanza. Próximos partidos {day}.",
               done="No queda ningún partido por jugar en el cuadro final.",
               tail=" En eSportly los marcadores siguen ocultos: los revelas cuando quieras."),
    "de": dict(title_one="{event}: 1 Match gespielt {day}", title="{event}: {n} Matches gespielt {day}", title_done="{event}: die K.-o.-Runde ist zu Ende gegangen",
               next_stage="Die K.-o.-Runde geht weiter. Als Nächstes: {stage}, {day}.",
               next_plain="Die K.-o.-Runde geht weiter. Nächste Matches {day}.",
               done="Kein Match mehr in der K.-o.-Runde.",
               tail=" Bei eSportly bleiben die Ergebnisse verborgen: Du zeigst sie, wann du willst."),
    "pt-BR": dict(title_one="{event}: 1 partida disputada {day}", title="{event}: {n} partidas disputadas {day}", title_done="{event}: o mata-mata chegou ao fim",
                  next_stage="O mata-mata avança. Próxima etapa: {stage}, {day}.",
                  next_plain="O mata-mata avança. Próximas partidas {day}.",
                  done="Não resta nenhuma partida no mata-mata.",
                  tail=" No eSportly os placares ficam escondidos: você revela quando quiser."),
}

STAGE_NAMES = {
    "quarter": {"fr": "les quarts de finale", "en": "the quarterfinals", "es": "los cuartos de final", "de": "das Viertelfinale",
                "pt-BR": "as quartas de final"},
    "semi": {"fr": "les demi-finales", "en": "the semifinals", "es": "las semifinales", "de": "das Halbfinale",
             "pt-BR": "as semifinais"},
    "final": {"fr": "la finale", "en": "the final", "es": "la final", "de": "das Finale", "pt-BR": "a final"},
}


def stage_of(summary: str) -> str | None:
    """L'étape nommée par le titre d'un match (« Semifinal 2: IG vs TBD » → « semi »), sinon None. Seule l'étape sort d'ici :
    jamais ce qui suit, qui nommerait un qualifié, donc le vainqueur de son match précédent."""
    return next((name for name, pattern in STAGES if pattern.search(summary)), None)


def report(calendar: list[dict], knockout_from: date, day: date, now: datetime) -> dict | None:
    """Ce qu'il y a à dire d'un événement le soir du `day` (jour de Paris) : {played, stage, next_day, done}, ou None quand aucun
    match de phase finale n'a été joué ce jour-là (le robot n'écrit alors rien du tout).

    `played` : matchs de la phase finale (coup d'envoi à partir de `knockout_from`) commencés ce jour-là, annulés écartés.
    `stage` et `next_day` : l'étape et le jour du prochain match de la phase finale ; `done` : il n'y en a plus aucun."""
    tz = an.paris()
    finals = [event for event in calendar
              if event.get("status") != "CANCELLED" and event["start"].astimezone(tz).date() >= knockout_from]
    played = [event for event in finals if event["start"] <= now and event["start"].astimezone(tz).date() == day]
    if not played:
        return None
    later = sorted((event for event in finals if event["start"] > now), key=lambda event: event["start"])
    if not later:
        return {"played": len(played), "stage": None, "next_day": None, "done": True}
    following = later[0]
    return {"played": len(played), "stage": stage_of(following["summary"]),
            "next_day": following["start"].astimezone(tz).date(), "done": False}


def _text(lang: str, name: str, found: dict, day: date) -> dict[str, str]:
    """Le titre et le texte d'une carte dans une langue. `an.day_label` donne le jour en toutes lettres de cette langue."""
    x = TEXTS[lang]
    when = an.day_label(day, lang, True)
    if found["done"]:
        title, body = x["title_done"].format(event=name), x["done"]
    else:
        key = "title_one" if found["played"] == 1 else "title"  # « 1 match joué », pas « 1 match(s) joué(s) »
        title = x[key].format(event=name, n=found["played"], day=when)
        nxt = an.day_label(found["next_day"], lang, True)
        body = (x["next_stage"].format(stage=STAGE_NAMES[found["stage"]][lang], day=nxt) if found["stage"]
                else x["next_plain"].format(day=nxt))
    return {"title": title, "text": body + x["tail"]}


def make_item(slug: str, found: dict, day: date) -> dict:
    """La carte de News d'un événement pour un soir : son identifiant (événement + jour, donc remplaçable), sa date, sa durée
    d'affichage, le lien vers la page de l'événement, et les cinq langues."""
    name = NAMES.get(slug, slug)
    item = {"id": f"{slug}-{day.isoformat()}", "date": day.isoformat(), "until": (day + KEEP).isoformat(),
            "link": {"page": slug}}
    for lang in an.LANGS:
        item[lang] = _text(lang, name, found, day)
    return item


def merge(items: list[dict], fresh: list[dict]) -> list[dict]:
    """Les cartes du jour prennent la place de celles qui portent le même identifiant (le robot peut tourner plusieurs fois dans la
    soirée), les nouvelles passent en tête. L'ordre des autres cartes ne bouge pas."""
    by_id = {item["id"]: item for item in fresh}
    kept = [by_id.pop(item["id"], item) if item.get("id") in by_id else item for item in items]
    return [item for item in fresh if item["id"] in by_id] + kept


def build(root: Path, now: datetime, fetch: Callable[[str], list[dict] | None] = an.read_events) -> tuple[dict, list[str]]:
    """Lit news/news.json, interroge le calendrier de chaque événement dont la phase finale a commencé, et rend (les news à écrire,
    les lignes à afficher). Un événement sans date de phase finale, dont le calendrier ne répond pas, ou sans match joué dans la
    journée, est sauté sans bruit."""
    path = root / NEWS
    news = an.load_news(path, root)
    day, fresh, said = now.astimezone(an.paris()).date(), [], []
    for slug, config in news.get("events", {}).items():
        start = an._parse_date(config.get("knockout_from"))
        if start is None or day < start:
            continue
        calendar = fetch(slug)
        if calendar is None:
            said.append(f"{slug} : calendrier indisponible, carte non écrite")
            continue
        found = report(calendar, start, day, now)
        if found is None:
            continue
        item = make_item(slug, found, day)
        fresh.append(item)
        said.append(f"{slug} : {item['fr']['title']} — {item['fr']['text']}")
    return {**news, "items": merge(news.get("items", []), fresh)}, said


def main(argv: list[str], root: Path = ROOT, now: datetime | None = None,
         fetch: Callable[[str], list[dict] | None] = an.read_events) -> int:
    essai = "--essai" in argv
    now = now or datetime.now(timezone.utc)
    try:
        news, said = build(root, now, fetch)
    except an.NewsError as error:
        print("\n".join(str(error).splitlines()))
        return 1
    for line in said:
        print(line)
    if not said:
        print("Résultats : aucun match de phase finale joué aujourd'hui, rien à écrire")
        return 0
    if essai:
        print("Résultats : --essai, news/news.json inchangé")
        return 0
    path = root / NEWS
    end = "\r\n" if "\r\n" in path.read_text(encoding="utf-8") else "\n"
    path.write_text(json.dumps(news, ensure_ascii=False, indent=2).replace("\n", end) + end, encoding="utf-8")
    an.load_news(path, root)  # ce qu'on vient d'écrire doit passer les contrôles des News
    print(f"Résultats : {len(said)} carte(s) écrite(s) dans {NEWS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
