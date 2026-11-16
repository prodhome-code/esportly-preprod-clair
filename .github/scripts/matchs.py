# Mise à jour quotidienne du site (GitHub Actions, voir .github/workflows/matchs.yml), sans aucun appel à
# PandaScore : les matchs viennent des calendriers publics du serveur d'eSportly (cache du relais).
# 1) « Prochains matchs » sur chaque page d'équipe (fr et en), avec les données « événement sportif » pour Google.
# 2) Les pages « Les matchs de la semaine » dans les 5 langues, fabriquées à partir des pages « Nouveautés ».
# 3) Les pages des grands événements (EVENTS), 4) les pages « Live » (live.py : les matchs du jour, toutes équipes confondues).
# Usage : python3 .github/scripts/matchs.py   (depuis la racine du site)
#         python3 .github/scripts/matchs.py --live   (robot de l'heure, workflow live.yml : saute 1 à 3, relit les matchs du jour dans
#         suivi/live.json au lieu des calendriers, note les fins confirmées par le flux de résultats (live_suivi.py) et ne refabrique
#         les pages Live et de match que s'il y en a une nouvelle)
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import blog
import diffusions
import live
import live_match
import live_suivi
import site_chrome

SITE = Path(__file__).resolve().parents[2]
URL = "https://esportly.eu/"
CAL = "https://lmavqchwevcvvneblqld.supabase.co/functions/v1/calendrier/equipe/"
PARIS = ZoneInfo("Europe/Paris")
NOW = datetime.now(timezone.utc)
LIVE_ONLY = "--live" in sys.argv[1:]  # robot de l'heure : seulement la partie Live (4)
# Les « matchs du jour » sont choisis une fois par jour et gardés dans suivi/live.json. Le job du matin est pourtant lancé par
# GitHub avec plusieurs heures de retard (cron à 4 h 15 UTC, passages constatés vers 12 h) : entre minuit et son passage, la page
# Live, les matchs de la semaine et les pages d'événements montraient la veille. Dès qu'il voit que le jour a changé, le robot de
# l'heure fait donc le travail du matin en entier, au lieu de seulement noter les fins. Aucun appel réseau pour s'en rendre compte.
TODAY = NOW.astimezone(PARIS).date().isoformat()
NEW_DAY = LIVE_ONLY and live_suivi.day_of(live_suivi.PATH) != TODAY
if NEW_DAY:
    print(f"Jour nouveau ({TODAY}) : le robot de l'heure refait la journée entière")
    LIVE_ONLY = False
SEO = site_chrome.seo_texts(SITE)  # <title> et description des pages de la semaine, des événements et Live (seo/titres.json)
START, END = "<!-- prochains-matchs -->", "<!-- /prochains-matchs -->"


# --- Adresses publiées ------------------------------------------------------------------------------------------
# Le Worker (assets sans html_handling : « auto-trailing-slash ») renvoie en 307 toute adresse en .html vers la même sans
# .html. Les adresses DÉCLARÉES (canonical, hreflang, og:url, <loc> et xhtml:link du sitemap, url / item / mainEntityOfPage /
# @id des données structurées) prennent donc la forme sans extension ; les liens de navigation (relatifs, en .html) ne
# changent pas. Recopie exacte de actualites.py (test_actualites le vérifie) : ce script reste autonome.

def public_url(path: str, site: str = "https://esportly.eu/") -> str:
    """Adresse publiée d'une page : « x.html » → site + « x », « index.html » → site, « dossier/index.html » → site + « dossier/ ».
    Accepte un chemin depuis la racine ou une adresse absolue du site ; garde le fragment. Une adresse avec « ? », d'un autre
    domaine ou d'un fichier non HTML est rendue telle quelle (un chemin devient absolu)."""
    address = path if "://" in path else site + path.lstrip("/")
    if not address.startswith(site) or "?" in address:
        return address
    address, hash_, fragment = address.partition("#")
    rest = address[len(site):]
    if rest == "index.html" or rest.endswith("/index.html"):
        rest = rest[:-len("index.html")]
    elif rest.endswith(".html"):
        rest = rest[:-len(".html")]
    return site + rest + hash_ + fragment


def public_urls(text: str, site: str = "https://esportly.eu/") -> str:
    """Les adresses déclarées d'une page ou d'un sitemap passent à leur forme publiée (public_url) ; rien d'autre ne change
    (ni les liens de navigation, ni les fins de ligne). Seules les adresses absolues du site sont touchées."""
    def convert(value: str) -> str:
        return public_url(value, site) if value.startswith(site) else value

    def tag(m: re.Match) -> str:
        found = m.group(0)
        if not ('rel="canonical"' in found or ('rel="alternate"' in found and "hreflang=" in found) or 'property="og:url"' in found):
            return found
        return re.sub(r'(?<=\s)(href|content)="([^"]*)"', lambda a: f'{a.group(1)}="{convert(a.group(2))}"', found)

    def json_ld(m: re.Match) -> str:
        return re.sub(r'("(?:url|item|mainEntityOfPage|@id)"\s*:\s*")([^"]*)(")',
                      lambda k: k.group(1) + convert(k.group(2)) + k.group(3), m.group(0))

    text = re.sub(r"<(?:link|xhtml:link|meta)\s[^>]*>", tag, text)
    text = re.sub(r"(?<=<loc>)[^<]*(?=</loc>)", lambda m: convert(m.group(0)), text)
    return re.sub(r'<script type="application/ld\+json">.*?</script>', json_ld, text, flags=re.S)


def rename_page(text: str, old: str, new: str, site: str = "https://esportly.eu/") -> str:
    """Une page d'un modèle devient une autre partout : liens (« old ») et adresse publiée (sans extension, suivie de " < ou #)."""
    text = text.replace(old, new)
    return re.sub(re.escape(public_url(old, site)) + r'(?=["<#])', lambda _: public_url(new, site), text)

LANGS = {
    "fr": dict(file="fr/matchs-de-la-semaine.html", news="fr/nouveautes.html", lang="fr",
               days=["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
               months=["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
               title="Les matchs de la semaine", kicker="Cette semaine",
               lead="Les matchs des grandes équipes d'e-sport pour les 7 prochains jours, mis à jour chaque matin. Heures de Paris.",
               meta="Le programme e-sport des 7 prochains jours : League of Legends, Valorant, Counter-Strike 2, Rocket League, Dota 2, Overwatch 2, Rainbow Six Siege. Mis à jour chaque jour.",
               none="Aucun match annoncé pour l'instant.", upcoming="Prochains matchs",
               upnone="Aucun match annoncé dans les 14 prochains jours.", tz="heure de Paris", updated="Mis à jour le",
               cta="Être prévenu avant chaque match", teams="fr/equipes"),
    "en": dict(file="matches-this-week.html", news="whats-new.html", lang="en",
               days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
               months=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
               title="This week's matches", kicker="This week",
               lead="Matches of the top esports teams for the next 7 days, updated every morning. Paris time.",
               meta="The esports schedule for the next 7 days: League of Legends, Valorant, Counter-Strike 2, Rocket League, Dota 2, Overwatch 2, Rainbow Six Siege. Updated daily.",
               none="No match announced yet.", upcoming="Upcoming matches",
               upnone="No match announced in the next 14 days.", tz="Paris time", updated="Updated on",
               cta="Get alerted before every match", teams="teams"),
    "es": dict(file="es/partidos-de-la-semana.html", news="es/novedades.html", lang="es",
               days=["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
               months=["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
               title="Los partidos de la semana", kicker="Esta semana",
               lead="Los partidos de los grandes equipos de esports en los próximos 7 días, actualizados cada mañana. Hora de París.",
               meta="El calendario de esports de los próximos 7 días: League of Legends, Valorant, Counter-Strike 2, Rocket League, Dota 2, Overwatch 2, Rainbow Six Siege. Actualizado cada día.",
               none="Todavía no hay partidos anunciados.", tz="hora de París", updated="Actualizado el",
               cta="Recibe un aviso antes de cada partido", teams="teams"),
    "de": dict(file="de/spiele-der-woche.html", news="de/neuigkeiten.html", lang="de",
               days=["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
               months=["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
               title="Die Matches der Woche", kicker="Diese Woche",
               lead="Die Matches der großen Esport-Teams in den nächsten 7 Tagen, jeden Morgen aktualisiert. Pariser Zeit.",
               meta="Der Esport-Spielplan der nächsten 7 Tage: League of Legends, Valorant, Counter-Strike 2, Rocket League, Dota 2, Overwatch 2, Rainbow Six Siege. Täglich aktualisiert.",
               none="Noch keine Matches angekündigt.", tz="Pariser Zeit", updated="Aktualisiert am",
               cta="Vor jedem Match benachrichtigt werden", teams="teams"),
    "pt-BR": dict(file="pt/partidas-da-semana.html", news="pt/novidades.html", lang="pt-BR",
                  days=["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"],
                  months=["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
                  title="As partidas da semana", kicker="Esta semana",
                  lead="As partidas dos grandes times de esports nos próximos 7 dias, atualizadas toda manhã. Horário de Paris.",
                  meta="A agenda de esports dos próximos 7 dias: League of Legends, Valorant, Counter-Strike 2, Rocket League, Dota 2, Overwatch 2, Rainbow Six Siege. Atualizada todo dia.",
                  none="Nenhuma partida anunciada ainda.", tz="horário de Paris", updated="Atualizado em",
                  cta="Seja avisado antes de cada partida", teams="teams"),
}
EXTRA = {
 "fr": {
  "results": "Résultats des 7 derniers jours",
  "reveal": "Voir le score",
  "res_none": "Aucun résultat cette semaine.",
  "spoil": "Les scores restent cachés : touche un match pour voir le sien.",
  "ev_title": "{e} : programme et résultats",
  "ev_lead": "Tous les matchs de {e} en heure de Paris, mis à jour chaque matin. Les scores restent cachés jusqu'à ce que tu les demandes.",
  "comp_title": "Les compétitions e-sport suivies par eSportly",
  "comp_lead": "Toutes les compétitions dont eSportly suit les matchs, jeu par jeu : programme, résultats et alertes avant chaque match.",
  "comp_all": "Toutes les compétitions",
  "comp_n": "{n} matchs suivis",
  "ev_up": "Prochains matchs",
  "ev_watch": "Comment regarder",
  "ev_watch_txt": "Les matchs sont diffusés en direct sur les chaînes officielles de l'organisateur, sur Twitch et YouTube. Dans eSportly, le direct s'affiche dans la fiche du match, seulement si tu le lances, et le score suit sur ton écran verrouillé.",
  "ev_cal": "Ajouter à mon calendrier",
  "ev_gcal": "Ajouter à Google Agenda",
  "events": "Grands événements"
 },
 "en": {
  "results": "Results from the last 7 days",
  "reveal": "Show the score",
  "res_none": "No results this week.",
  "spoil": "Scores stay hidden: tap a match to see its score.",
  "ev_title": "{e}: schedule and results",
  "ev_lead": "Every {e} match in Paris time, updated every morning. Scores stay hidden until you ask for them.",
  "comp_title": "The esports competitions eSportly follows",
  "comp_lead": "Every competition whose matches eSportly follows, game by game: schedule, results and an alert before each match.",
  "comp_all": "All competitions",
  "comp_n": "{n} matches followed",
  "ev_up": "Upcoming matches",
  "ev_watch": "How to watch",
  "ev_watch_txt": "Matches are streamed live on the organizer's official channels, on Twitch and YouTube. In eSportly, the stream shows on the match page, only if you start it, and the score follows on your Lock Screen.",
  "ev_cal": "Add to my calendar",
  "ev_gcal": "Add to Google Calendar",
  "events": "Big events"
 },
 "es": {
  "results": "Resultados de los últimos 7 días",
  "reveal": "Ver el marcador",
  "res_none": "Sin resultados esta semana.",
  "spoil": "Los marcadores quedan ocultos: toca un partido para ver el suyo.",
  "ev_title": "{e}: calendario y resultados",
  "ev_lead": "Todos los partidos de {e} en hora de París, actualizados cada mañana. Los marcadores quedan ocultos hasta que los pidas.",
  "comp_title": "Las competiciones de esports que sigue eSportly",
  "comp_lead": "Todas las competiciones cuyos partidos sigue eSportly, juego por juego: calendario, resultados y aviso antes de cada partido.",
  "comp_all": "Todas las competiciones",
  "comp_n": "{n} partidos seguidos",
  "ev_up": "Próximos partidos",
  "ev_watch": "Cómo verlo",
  "ev_watch_txt": "Los partidos se emiten en directo en los canales oficiales del organizador, en Twitch y YouTube. En eSportly, el directo aparece en la ficha del partido, solo si lo inicias, y el marcador sigue en tu pantalla bloqueada.",
  "ev_cal": "Añadir a mi calendario",
  "ev_gcal": "Añadir a Google Calendar",
  "events": "Grandes eventos"
 },
 "de": {
  "results": "Ergebnisse der letzten 7 Tage",
  "reveal": "Ergebnis zeigen",
  "res_none": "Diese Woche keine Ergebnisse.",
  "spoil": "Ergebnisse bleiben verborgen: Tippe auf ein Match, um sein Ergebnis zu sehen.",
  "ev_title": "{e}: Spielplan und Ergebnisse",
  "ev_lead": "Alle Matches von {e} in Pariser Zeit, jeden Morgen aktualisiert. Ergebnisse bleiben verborgen, bis du sie sehen willst.",
  "comp_title": "Die Esport-Wettbewerbe, denen eSportly folgt",
  "comp_lead": "Alle Wettbewerbe, deren Matches eSportly verfolgt, Spiel für Spiel: Spielplan, Ergebnisse und eine Meldung vor jedem Match.",
  "comp_all": "Alle Wettbewerbe",
  "comp_n": "{n} Matches verfolgt",
  "ev_up": "Nächste Matches",
  "ev_watch": "So schaust du zu",
  "ev_watch_txt": "Die Matches laufen live auf den offiziellen Kanälen des Veranstalters, auf Twitch und YouTube. In eSportly erscheint der Stream auf der Match-Seite, nur wenn du ihn startest, und das Ergebnis folgt auf deinem Sperrbildschirm.",
  "ev_cal": "Zu meinem Kalender hinzufügen",
  "ev_gcal": "Zu Google Kalender hinzufügen",
  "events": "Große Events"
 },
 "pt-BR": {
  "results": "Resultados dos últimos 7 dias",
  "reveal": "Ver o placar",
  "res_none": "Nenhum resultado nesta semana.",
  "spoil": "Os placares ficam escondidos: toque em uma partida para ver o dela.",
  "ev_title": "{e}: agenda e resultados",
  "ev_lead": "Todas as partidas de {e} no horário de Paris, atualizadas toda manhã. Os placares ficam escondidos até você pedir.",
  "comp_title": "As competições de esports que o eSportly acompanha",
  "comp_lead": "Todas as competições cujas partidas o eSportly acompanha, jogo a jogo: calendário, resultados e aviso antes de cada partida.",
  "comp_all": "Todas as competições",
  "comp_n": "{n} partidas acompanhadas",
  "ev_up": "Próximas partidas",
  "ev_watch": "Como assistir",
  "ev_watch_txt": "As partidas são transmitidas ao vivo nos canais oficiais do organizador, na Twitch e no YouTube. No eSportly, a transmissão aparece na página da partida, só se você iniciar, e o placar acompanha na tela bloqueada.",
  "ev_cal": "Adicionar ao meu calendário",
  "ev_gcal": "Adicionar ao Google Agenda",
  "events": "Grandes eventos"
 }
}
EVENTS = {  # page → (nom, jeu) ; les matchs viennent de /calendrier/evenement/<page>.ics et /resultats/<page>.json
    "worlds-2026": ("Worlds 2026", "League of Legends"),
    "vct-champions-2026": ("VCT Champions 2026", "Valorant"),
    "esl-pro-league": ("ESL Pro League", "Counter-Strike 2"),
}
API = "https://lmavqchwevcvvneblqld.supabase.co/functions/v1/calendrier/"


def read_results(scope: str) -> list[dict]:
    try:
        with urllib.request.urlopen(f"{API}resultats/{scope}.json", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"résultats {scope} : {error}")
        return []


RESULTS_START = "<!-- resultats -->"  # repères du bloc des résultats : le robot de l'heure le remplace sans refabriquer la page
RESULTS_END = "<!-- /resultats -->"
RESULTS_BLOCK = re.compile(re.escape(RESULTS_START) + ".*?" + re.escape(RESULTS_END), re.S)
# Secours pour les pages faites avant les repères : le bloc des résultats est ce qui sépare leur titre (seul h2 porteur de
# id="resultats") du titre suivant. La page gagne ses repères au passage, et n'a plus besoin de ce secours ensuite.
RESULTS_LEGACY = re.compile(r'(<h2 class="jour" id="resultats">.*?</h2>)(.*?)(?=<h2\b)', re.S)
BLUR = "filter:blur(12px)"  # style en ligne du score caché : il tient même sans feuille de style (jamais de spoiler par accident)
# La règle qui révèle un score flouté, telle qu'elle apparaît dans STYLE : refresh_results la pose sur une page qui ne l'a pas encore.
REVEAL_STYLE = ".resultats details[open] .score{filter:none!important;user-select:auto}"


def results_html(results: list[dict], t: dict, x: dict) -> str:
    """Résultats cachés (<details>, sans script) : le score est écrit en clair mais flouté par son style en ligne, et toucher un
    match le révèle (même geste et même rendu que la page d'un match, live_match.py). Le bloc porte ses repères."""
    if not results:
        return RESULTS_START + f'<p>{x["res_none"]}</p>' + RESULTS_END
    items = []
    for r in results[:30]:
        moment = datetime.fromisoformat(r["date"].replace("Z", "+00:00")).astimezone(PARIS)
        day = f'{t["days"][moment.weekday()]} {moment.day} {t["months"][moment.month - 1]}'
        context = clean(" · ".join(v for v in (r.get("game"), r.get("league"), r.get("serie")) if v))
        score = " – ".join("?" if v is None else str(v) for v in r["score"])
        teams = " – ".join(r["teams"])
        items.append(f'<li><details><summary><b>{html.escape(teams)}</b><small>{html.escape(day)} · {html.escape(context)}</small>'
                     f'<p class="score" style="{BLUR}">{html.escape(r["teams"][0])} <b>{score}</b> {html.escape(r["teams"][1])}</p>'
                     f'<span class="voir">{x["reveal"]}</span></summary></details></li>')
    return RESULTS_START + f'<p class="maj">{x["spoil"]}</p><ul class="resultats">{"".join(items)}</ul>' + RESULTS_END


def refresh_results(site: Path, slug: str, langs: dict, extra: dict, results: list[dict]) -> list[str]:
    """Remplace le bloc des résultats des pages d'un événement, sans rien refabriquer d'autre : seules les pages qui changent
    vraiment sont réécrites, et une liste de résultats vide ne touche à rien (on n'efface jamais). Rend les chemins réécrits."""
    done: list[str] = []
    if not results:
        return done
    for code, t in langs.items():
        path = site / event_page(slug, code)
        if not path.is_file():
            continue
        page = path.read_text(encoding="utf-8")
        fresh = results_html(results, t, extra[code])
        if RESULTS_START in page and RESULTS_END in page:
            updated = RESULTS_BLOCK.sub(lambda _: fresh, page, count=1)
        elif RESULTS_LEGACY.search(page):
            updated = RESULTS_LEGACY.sub(lambda m: m.group(1) + fresh, page, count=1)
        else:
            continue  # page sans section de résultats reconnaissable : on n'y touche pas
        if REVEAL_STYLE not in updated and "</style>" in updated:
            # Le score flouté a besoin de la règle qui le révèle : une page faite avant elle la reçoit ici, sinon son score
            # resterait flouté pour toujours. Le robot du matin la pose de toute façon avec le reste du style.
            updated = updated.replace("</style>", REVEAL_STYLE + "</style>", 1)
        if updated != page:
            path.write_text(updated, encoding="utf-8")
            done.append(event_page(slug, code))
    return done



# Compétitions au nom d'un site de paris : on garde le match, mais on n'affiche que le jeu (règle « aucun pari »).
BETTING = re.compile(r"1win|stake|thunderpick|\bpari\b|parimatch|betboom|gg\.?bet|betway|bet365|rollbit|csgoempire|bc\.game", re.I)


def clean(description: str) -> str:
    if BETTING.search(description):
        return description.split(" · ")[0]
    return description


def unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").replace("\n ", "").splitlines()


def unescape_ics(value: str) -> str:
    return value.replace("\\n", " ").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\")


def read_calendar(slug: str, base: str = CAL) -> list[dict] | None:
    """None si le serveur n'a pas répondu (après un second essai) : la page garde alors son contenu d'hier."""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(f"{base}{slug}.ics", timeout=60) as response:
                text = response.read().decode("utf-8")
            break
        except Exception as error:  # une équipe indisponible ne bloque pas les autres
            print(f"{slug} : {error}")
    else:
        return None
    events, current = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if "DTSTART" in current and current.get("STATUS") != "CANCELLED":
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";")[0]] = clean(unescape_ics(value)) if key.startswith("DESCRIPTION") else unescape_ics(value)
    for event in events:
        event["start"] = datetime.strptime(event["DTSTART"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        event["end"] = datetime.strptime(event.get("DTEND", event["DTSTART"]), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    # Les matchs d'une marque de paris ne sont pas affichés (audit légal, risque ANJ/App Store).
    events = [e for e in events if not site_chrome.is_betting(e.get("SUMMARY", ""))]
    return events


def when(event: dict, t: dict, with_day: bool = True) -> str:
    local = event["start"].astimezone(PARIS)
    hour = local.strftime("%H:%M")
    if not with_day:
        return hour
    return f'{t["days"][local.weekday()]} {local.day} {t["months"][local.month - 1]}, {hour}'


def json_ld(events: list[dict]) -> str:
    items = []
    for event in events:
        names = [n.strip() for n in event.get("SUMMARY", "").split("–")]
        item = {
            "@context": "https://schema.org", "@type": "SportsEvent", "name": event.get("SUMMARY", "Match"),
            "startDate": event["start"].isoformat(), "endDate": event["end"].isoformat(),
            "eventStatus": "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
            "location": {"@type": "VirtualLocation", "url": event.get("URL", URL)},
            "description": event.get("DESCRIPTION", ""), "url": event.get("URL", URL),
        }
        if len(names) == 2:
            item["competitor"] = [{"@type": "SportsTeam", "name": n} for n in names]
        items.append(item)
    return '<script type="application/ld+json">' + json.dumps(items, ensure_ascii=False) + "</script>"


def match_item(event: dict, t: dict, with_day: bool = True) -> str:
    link = html.escape(event.get("URL", URL))
    return (f'<li><a href="{link}" target="_top"><time datetime="{event["start"].isoformat()}">{html.escape(when(event, t, with_day))}</time>'
            f'<b>{html.escape(event.get("SUMMARY", "Match"))}</b><small>{html.escape(event.get("DESCRIPTION", ""))}</small></a></li>')


STYLE = (".matchs{list-style:none;padding:0;margin:0;display:grid;gap:10px}"
         ".matchs a{display:grid;gap:2px;padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border);color:var(--text);text-decoration:none}"
         ".matchs time{font-size:15px;color:var(--or);font-weight:700}.matchs b{font-size:18px}.matchs small{font-size:14px;color:var(--soft)}"
         ".jour{font:700 26px var(--display);margin:30px 0 12px}.maj{font-size:14px;color:var(--muted)}"
         ".resultats{list-style:none;padding:0;margin:0;display:grid;gap:10px}.resultats details{padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}"
         ".resultats summary{display:grid;gap:2px;cursor:pointer;list-style:none}.resultats summary::-webkit-details-marker{display:none}.resultats summary b{font-size:18px}"
         ".resultats small{font-size:14px;color:var(--soft)}.resultats .voir{font-size:14px;font-weight:700;color:var(--text);text-decoration:underline}"
         ".resultats details[open] .voir{display:none}.score{margin:10px 0 0;font-size:18px;user-select:none}.score b{font:700 26px var(--display);margin:0 8px}"
         ".resultats summary .score{margin:10px 0 6px}"
         # Le score est flouté par son style en ligne ; l'ouverture le révèle (!important l'emporte sur le style en ligne).
         ".resultats details[open] .score{filter:none!important;user-select:auto}"
         ".evts{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}.evts a{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:999px;background:var(--surface);border:1px solid var(--border);color:var(--text);text-decoration:none;font-weight:600;font-size:15px}"
         ".cal-buttons{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.cal-google{display:inline-flex;align-items:center;min-height:54px;padding:0 24px;border-radius:999px;border:1px solid var(--border);color:var(--text);font-weight:700;text-decoration:none}")

# L'heure du visiteur à côté de l'heure de Paris, quand elles diffèrent (Brésil, Amériques, Asie…) :
# « 08:00 chez toi », avec le jour s'il change. Un seul petit script, autorisé par son empreinte (CSP).
LOCAL_JS = ("(function(){var d=document,h=d.documentElement,l=(h.lang||'fr').slice(0,2),"
            "w={fr:'chez toi',en:'your time',es:'tu hora',de:'deine Zeit',pt:'seu horário'}[l]||'your time',"
            "t=d.querySelectorAll('.matchs time[datetime]'),P='Europe/Paris';"
            "for(var i=0;i<t.length;i++){var x=new Date(t[i].getAttribute('datetime'));if(isNaN(x))continue;"
            "try{var o={hour:'2-digit',minute:'2-digit'},k=function(z){return new Intl.DateTimeFormat('en-CA',"
            "{timeZone:z,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(x)},"
            "a=k(P),b=k(undefined);if(a===b)continue;if(a.slice(0,10)!==b.slice(0,10))o.weekday='short';"
            "var s=d.createElement('span');s.className='loc';s.textContent=new Intl.DateTimeFormat(h.lang||'fr',o).format(x)+' '+w;"
            "t[i].insertAdjacentElement('afterend',s)}catch(e){}}})();")
LOCAL_HASH = base64.b64encode(hashlib.sha256(LOCAL_JS.encode("utf-8")).digest()).decode()
LOCAL_STYLE = ".matchs .loc{font-size:14px;color:var(--soft);font-weight:600}"


def with_local_times(page: str) -> str:
    """Ajoute (une fois) le script de l'heure locale, son empreinte dans la CSP et son style."""
    if LOCAL_JS not in page:
        page = re.sub(r"<script>\(function\(\)\{var d=document,h=d\.documentElement,l=.*?</script>\n?", "", page, flags=re.S)
        page = page.replace("</body>", f"<script>{LOCAL_JS}</script>\n</body>", 1)
    if f"'sha256-{LOCAL_HASH}'" not in page:
        page = re.sub(r"(script-src [^;\"]*)", lambda m: m.group(1) + f" 'sha256-{LOCAL_HASH}'", page, count=1)
    if ".matchs .loc{" not in page:
        page = page.replace("</style>", LOCAL_STYLE + "</style>", 1)
    return page


WIDGET = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<meta name="robots" content="noindex"><meta name="referrer" content="strict-origin-when-cross-origin"><title>{name} – eSportly</title>
<style>:root{{color-scheme:light dark;--bg:#0A0E1A;--card:#141A2B;--border:#2C3550;--text:#F4F6FF;--soft:#C9CEDA;--or:#FFC53D;--accent:#FFC53D}}
@media (prefers-color-scheme:light){{:root{{--bg:#F6F7FB;--card:#FFFFFF;--border:#D5DAE6;--text:#0E1424;--soft:#3A4250;--accent:#6A4900}}}}
body{{margin:0;padding:12px;background:var(--bg);color:var(--text);font:15px/1.4 -apple-system,BlinkMacSystemFont,system-ui,sans-serif}}
ul{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}a{{color:inherit;text-decoration:none}}
li a{{display:grid;gap:2px;padding:10px 12px;border-radius:12px;background:var(--card);border:1px solid var(--border)}}
time{{color:var(--accent);font-weight:700;font-size:13px}}b{{font-size:15px}}small{{color:var(--soft);font-size:12px}}
.f{{display:flex;justify-content:space-between;gap:8px;margin-top:10px;font-size:12px;color:var(--soft)}}.f a{{color:var(--accent);font-weight:700}}</style></head>
<body><ul>{items}</ul><p class="f"><span>{tz}</span><a href="{link}" target="_blank" rel="noopener">{follow} →</a></p></body></html>
"""

def event_page(slug: str, code: str) -> str:
    """La page d'un grand événement dans une langue, depuis la racine : worlds-2026-en.html en anglais, fr/worlds-2026.html en français."""
    return f"{site_chrome.LANG_DIRS[code]}{slug}{'-en' if code == 'en' else ''}.html"


# 1) Pages d'équipes
organisations = sorted(p.stem for p in (SITE / LANGS["fr"]["teams"]).glob("*.html"))  # les pages d'équipes (fr/equipes/) ; les fiches JSON restent dans equipes/
everything: dict[str, dict] = {}
week_results = read_results("semaine")
LATEST = {"fr": "Derniers résultats", "en": "Latest results"}


def team_names(slug: str) -> set[str]:
    """Les noms sous lesquels l'organisation joue (fiche equipes/<slug>.json), en minuscules."""
    fiche = SITE / "equipes" / f"{slug}.json"
    if not fiche.exists():
        return set()
    data = json.loads(fiche.read_text(encoding="utf-8"))
    return {n.lower() for n in [data.get("organisation", ""), *data.get("noms", []), *(e.get("nom", "") for e in data.get("equipes", []))] if n}

activity: dict[str, int] = {}  # {organisation: matchs de son calendrier}, pour les équipes mises en avant dans le menu

for slug in ([] if LIVE_ONLY else organisations):
    events = read_calendar(slug)
    if events is None:
        continue
    for event in events:
        everything[event.get("UID", event.get("URL"))] = event
    activity[slug] = len(events)  # tout son calendrier : les grosses équipes jouent beaucoup, sur toute la saison
    upcoming = sorted((e for e in events if NOW - timedelta(hours=3) <= e["start"] <= NOW + timedelta(days=14)),
                      key=lambda e: e["start"])[:5]
    # Ses matchs finis des 7 derniers jours, scores cachés : seulement s'il y en a (pas de rubrique vide).
    names = team_names(slug)
    latest = [r for r in week_results if names & {n.lower() for n in r["teams"]}][:3]
    for folder, code in ((LANGS["fr"]["teams"], "fr"), (LANGS["en"]["teams"], "en")):
        page = SITE / folder / f"{slug}.html"
        if not page.exists():
            continue
        t = LANGS[code]
        source = page.read_text(encoding="utf-8")
        body = (f'<ul class="matchs">{"".join(match_item(e, t) for e in upcoming)}</ul><p class="maj">{t["tz"]}</p>{json_ld(upcoming)}'
                if upcoming else f'<p>{t["upnone"]}</p>')
        if latest:
            body += f'\n<h2 id="resultats">{LATEST[code]}</h2>\n{results_html(latest, t, EXTRA[code])}'
        block = f'{START}\n<h2 id="prochains-matchs">{t["upcoming"]}</h2>\n{body}\n{END}'
        if START in source:
            source = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, source, flags=re.S)
        else:
            anchor = source.find("<!-- calendrier-equipe -->")
            if anchor < 0:
                anchor = source.find("</main>")
            source = source[:anchor] + block + "\n" + source[anchor:]
            source = source.replace("</style>", STYLE + "</style>", 1)
        if ".resultats{" not in source:
            source = source.replace("</style>", STYLE + "</style>", 1)
        page.write_text(with_local_times(source), encoding="utf-8")
    # Calendrier à intégrer sur un site de fans (iframe), une page par équipe et par langue, sans script.
    for code in ("fr", "en"):
        t = LANGS[code]
        team = SITE / t["teams"] / f"{slug}.html"
        if not team.exists():
            continue
        fiche = SITE / "equipes" / f"{slug}.json"
        name = json.loads(fiche.read_text(encoding="utf-8")).get("organisation", slug) if fiche.exists() else slug
        follow = (f"Suivre {name} avec eSportly" if code == "fr" else f"Follow {name} with eSportly")
        items = "".join(match_item(e, t) for e in upcoming[:3]) or f"<li><p>{t['upnone']}</p></li>"
        widget = SITE / "widget" / code / f"{slug}.html"
        widget.parent.mkdir(parents=True, exist_ok=True)
        widget.write_text(WIDGET.format(lang=code, name=html.escape(name), items=items, tz=t["tz"], follow=html.escape(follow),
                                        link=f"{URL}{t['teams']}/{slug}.html"), encoding="utf-8")

# 2) Les matchs de la semaine (5 langues)
week = sorted((e for e in everything.values() if NOW - timedelta(hours=3) <= e["start"] <= NOW + timedelta(days=7)),
              key=lambda e: e["start"])
names = {code: t["news"] for code, t in LANGS.items()}
for code, t in ({} if LIVE_ONLY else LANGS).items():
    template = (SITE / t["news"]).read_text(encoding="utf-8")
    for other, news in names.items():  # liens de langue et hreflang : vers les pages de la semaine
        template = rename_page(template, news, LANGS[other]["file"])
    template = template.replace(LANGS[code]["file"].replace(".html", ".xml"), "")
    template = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\n?', "", template)
    head, meta = (html.escape(s) for s in site_chrome.seo(SEO, t["file"], t["title"], t["meta"]))  # le H1 reste t["title"]
    template = re.sub(r"<title>.*?</title>", lambda _: f"<title>{head}</title>", template, flags=re.S)
    template = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + meta, template)
    template = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + head, template)
    template = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + meta, template)
    template = re.sub(r'(visite\?p=/)[a-z/-]+', lambda m: m.group(1) + t["file"][:-5], template)
    template = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + f"{URL}partage/semaine-{code}.jpg", template)
    days, groups = [], {}
    for event in week:
        key = event["start"].astimezone(PARIS).date()
        groups.setdefault(key, []).append(event)
    content = []
    for day, events in groups.items():
        label = f'{t["days"][day.weekday()]} {day.day} {t["months"][day.month - 1]}'
        content.append(f'<h2 class="jour">{label[0].upper() + label[1:]}</h2><ul class="matchs">{"".join(match_item(e, t, False) for e in events)}</ul>')
    today = NOW.astimezone(PARIS)
    main = (f'<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{t["kicker"]}</div>'
            f'<h1>{t["title"]}</h1><p class="lead">{t["lead"]}</p>'
            f'<a class="cta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{t["file"][:-5]}&amp;go=testflight">{t["cta"]}</a></section>'
            + f'<h2 class="jour">{EXTRA[code]["events"]}</h2><ul class="evts">'
            + "".join(f'<li><a href="{site_chrome.prefix_for(t["file"])}{event_page(slug, code)}">{name}</a></li>' for slug, (name, _) in EVENTS.items()) + "</ul>"
            + ("".join(content) if content else f'<p>{t["none"]}</p>')
            + f'<h2 class="jour" id="resultats">{EXTRA[code]["results"]}</h2>' + results_html(week_results, t, EXTRA[code])
            + f'<p class="maj">{t["updated"]} {today.day} {t["months"][today.month - 1]} {today.year} · {t["tz"]}</p>'
            + json_ld(week[:60]))
    template = re.sub(r'<main class="wrap">.*?</main>', lambda _: f'<main class="wrap">{main}</main>', template, flags=re.S)
    if ".matchs{" not in template:
        template = template.replace("</style>", STYLE + "</style>", 1)
    (SITE / t["file"]).write_text(with_local_times(public_urls(template)), encoding="utf-8")
# action= (le formulaire de recherche d'équipe) et data-src= (la liste des équipes chargée au premier clic) sont des chemins
# comme les autres : oubliés ici, la recherche du menu renvoyait à une page absente depuis une page de compétition.
RELATIVE = re.compile(r'(\s(?:href|src|action|data-src)=")(?!https?:|mailto:|data:|webcal:|#|/)([^"]*)')


def deeper(template: str) -> str:
    """Le modèle (une page des nouveautés) vu depuis un dossier de plus : ses adresses relatives gagnent un « ../ ». Les pages des
    compétitions vivent dans un dossier (competitions/, fr/competitions/…), le modèle non : sans cela, la marque d'une page
    anglaise mènerait à competitions/ au lieu de la racine."""
    return RELATIVE.sub(lambda m: m.group(1) + "../" + m.group(2), template)


def write_competition_pages(slug: str, event_name: str, game_name: str, upcoming: list[dict], results: list[dict],
                            pages: dict[str, str], ics_slug: str | None = None, extra_links: dict[str, str] | None = None,
                            in_folder: bool = False) -> None:
    """Écrit la page d'une compétition dans les cinq langues : programme groupé par jour, résultats (scores floutés), comment
    regarder. `pages` : {langue: chemin de la page depuis la racine} ; `ics_slug` : la compétition a un calendrier à s'abonner
    (les trois grands événements configurés), sinon les boutons de calendrier ne sont pas affichés — une compétition découverte
    dans les matchs n'a pas d'adresse .ics.    `extra_links` : {langue: liens ajoutés sous le chapeau} (page du jeu, toutes les compétitions)."""
    for code, t in LANGS.items():
        x = EXTRA[code]
        template = (SITE / t["news"]).read_text(encoding="utf-8")
        if in_folder:  # la page vit dans un dossier (competitions/…), le modèle non
            template = deeper(template)
        for other, news in names.items():
            template = rename_page(template, news, pages[other])
        template = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\n?', "", template)
        title = x["ev_title"].format(e=event_name)
        lead = x["ev_lead"].format(e=event_name)
        head, meta = (html.escape(s) for s in site_chrome.seo(SEO, pages[code], title, lead))  # le H1 et le chapeau restent title et lead
        template = re.sub(r"<title>.*?</title>", lambda _: f"<title>{head}</title>", template, flags=re.S)
        template = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + meta, template)
        template = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + head, template)
        template = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + meta, template)
        template = re.sub(r'(visite\?p=/)[a-z/-]+', lambda m: m.group(1) + pages[code][:-5], template)
        buttons = ""
        if ics_slug:
            ics = f"lmavqchwevcvvneblqld.supabase.co/functions/v1/calendrier/evenement/{ics_slug}.ics"
            gcal = "https://calendar.google.com/calendar/render?cid=" + quote("webcal://" + ics, safe="")
            buttons = (f'<p class="cal-buttons"><a class="cta" href="webcal://{ics}">{x["ev_cal"]}</a>'
                       f'<a class="cal-google" href="{gcal}" rel="noopener">{x["ev_gcal"]}</a></p>')
        groups: dict = {}
        for event in upcoming:
            groups.setdefault(event["start"].astimezone(PARIS).date(), []).append(event)
        days = []
        for day, evs in groups.items():
            label = f'{t["days"][day.weekday()]} {day.day} {t["months"][day.month - 1]}'
            days.append(f'<h3 class="jour">{label[0].upper() + label[1:]}</h3><ul class="matchs">{"".join(match_item(e, t, False) for e in evs)}</ul>')
        today = NOW.astimezone(PARIS)
        main = (f'<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{html.escape(game_name)}</div>'
                f'<h1>{html.escape(title)}</h1><p class="lead">{html.escape(lead)}</p>'
                f'<a class="cta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{pages[code][:-5]}&amp;go=testflight">{t["cta"]}</a></section>'
                + buttons + (extra_links or {}).get(code, "")
                + f'<h2 class="jour">{x["ev_up"]}</h2>' + ("".join(days) if days else f'<p>{t["none"]}</p>')
                + f'<h2 class="jour" id="resultats">{x["results"]}</h2>' + results_html(results, t, x)
                + f'<h2 class="jour">{x["ev_watch"]}</h2><p>{x["ev_watch_txt"]}</p>'
                + f'<p class="maj">{t["updated"]} {today.day} {t["months"][today.month - 1]} {today.year} · {t["tz"]}</p>'
                + json_ld(upcoming))
        template = re.sub(r'<main class="wrap">.*?</main>', lambda _: f'<main class="wrap">{main}</main>', template, flags=re.S)
        template = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + f"{URL}partage/semaine-{code}.jpg", template)
        if ".resultats{" not in template:
            template = template.replace("</style>", STYLE + "</style>", 1)
        path = SITE / pages[code]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(with_local_times(public_urls(template)), encoding="utf-8")


# 3) Grands événements (5 langues) : programme, résultats cachés, calendrier, comment regarder.
for slug, (event_name, game_name) in ({} if LIVE_ONLY else EVENTS).items():
    events = read_calendar(slug, API + "evenement/")
    if events is None:
        continue
    for event in events:  # pour la page Live : un match déjà vu depuis une équipe garde sa première version
        everything.setdefault(event.get("UID", event.get("URL")), event)
    upcoming = sorted((e for e in events if e["start"] >= NOW - timedelta(hours=3)), key=lambda e: e["start"])[:60]
    results = read_results(slug)
    write_competition_pages(slug, event_name, game_name, upcoming, results,
                            {code: event_page(slug, code) for code in LANGS}, ics_slug=slug)
    print(f"{event_name} : {len(upcoming)} à venir, {len(results)} résultats")

def comp_links(game: str, game_names: dict[str, dict[str, str]]) -> dict[str, str]:
    """Les deux liens d'une page de compétition, sous le chapeau : sa page de jeu et l'index des compétitions, vus du dossier des
    compétitions de la langue (« ../../fr/jeux/valorant.html »)."""
    links = {}
    for code in LANGS:
        up = "../" * (COMP_DIRS[code].count("/") + 1)
        name = game_names.get(code, {}).get(game) or game_names.get("en", {}).get(game, game)
        links[code] = (f'<nav class="others" aria-label="eSportly">'
                       f'<a href="{up}{site_chrome.GAME_DIRS[code]}/{game}.html">{html.escape(name)}</a>'
                       f'<a href="{up}{comp_index_page(code)}">{html.escape(EXTRA[code]["comp_all"])}</a></nav>')
    return links


def comp_index_page(code: str) -> str:
    """L'index des compétitions d'une langue : competitions.html en anglais, fr/competitions.html en français…"""
    return f"{COMP_DIRS[code]}.html"


def write_competitions_index(kept: dict[str, dict], game_names: dict[str, dict[str, str]]) -> None:
    """L'index des compétitions, une page par langue : les compétitions groupées par jeu, avec leur nombre de matchs suivis."""
    by_game: dict[str, list[tuple[str, dict]]] = {}
    for slug, entry in kept.items():
        by_game.setdefault(entry["game"], []).append((slug, entry))
    pages = {code: comp_index_page(code) for code in LANGS}
    for code, t in LANGS.items():
        x = EXTRA[code]
        template = (SITE / t["news"]).read_text(encoding="utf-8")
        for other, news in names.items():
            template = rename_page(template, news, pages[other])
        template = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\n?', "", template)
        title, lead = x["comp_title"], x["comp_lead"]
        head, meta = (html.escape(s) for s in site_chrome.seo(SEO, pages[code], title, lead))
        template = re.sub(r"<title>.*?</title>", lambda _: f"<title>{head}</title>", template, flags=re.S)
        template = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + meta, template)
        template = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + head, template)
        template = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + meta, template)
        template = re.sub(r'(visite\?p=/)[a-z/-]+', lambda m: m.group(1) + pages[code][:-5], template)
        blocks = []
        for game in site_chrome.GAMES:
            found = sorted(by_game.get(game, []), key=lambda pair: pair[1]["label"].lower())
            if not found:
                continue
            name = game_names.get(code, {}).get(game) or game_names.get("en", {}).get(game, game)
            items = "".join(
                f'<li data-game="{game}"><a href="{COMP_DIRS[code].split("/")[-1]}/{slug}.html"><b>{html.escape(entry["label"])}</b>'
                f'<small>{x["comp_n"].format(n=len(entry["events"]) + len(entry["results"]))}</small></a></li>'
                for slug, entry in found)
            blocks.append(f'<h2 class="jour">{html.escape(name)}</h2><ul class="matchs">{items}</ul>')
        today = NOW.astimezone(PARIS)
        main = (f'<section class="hero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{html.escape(x["comp_all"])}</div>'
                f'<h1>{html.escape(title)}</h1><p class="lead">{html.escape(lead)}</p>'
                f'<a class="cta" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{pages[code][:-5]}&amp;go=testflight">{t["cta"]}</a></section>'
                + ("".join(blocks) if blocks else f'<p>{t["none"]}</p>')
                + f'<p class="maj">{t["updated"]} {today.day} {t["months"][today.month - 1]} {today.year} · {t["tz"]}</p>')
        template = re.sub(r'<main class="wrap">.*?</main>', lambda _: f'<main class="wrap">{main}</main>', template, flags=re.S)
        template = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + f"{URL}partage/semaine-{code}.jpg", template)
        if ".resultats{" not in template:
            template = template.replace("</style>", STYLE + "</style>", 1)
        (SITE / pages[code]).write_text(with_local_times(public_urls(template)), encoding="utf-8")


def prune_competitions(keep: set[str]) -> int:
    """Supprime les pages des compétitions qui ne sont plus dans les calendriers : une compétition finie ne laisse pas de page morte."""
    gone = 0
    for code in LANGS:
        folder = SITE / COMP_DIRS[code]
        for path in sorted(folder.glob("*.html")) if folder.is_dir() else []:
            if path.stem not in keep:
                path.unlink()
                gone += 1
    return gone


SITEMAP_START, SITEMAP_END = "<!-- competitions -->", "<!-- /competitions -->"


def write_competitions_sitemap(kept: dict[str, dict]) -> None:
    """Met les pages des compétitions (et leur index) dans sitemap.xml, entre leurs repères : une ligne par page et par langue,
    avec les hreflang des cinq langues. Le reste du sitemap, écrit à la main, n'est pas touché."""
    path = SITE / "sitemap.xml"
    text = path.read_text(encoding="utf-8")
    if SITEMAP_START not in text or SITEMAP_END not in text:
        text = text.replace("</urlset>", f"{SITEMAP_START}\n{SITEMAP_END}\n</urlset>", 1)
    day = NOW.astimezone(PARIS).date().isoformat()
    lines = []
    for pages in [{code: comp_index_page(code) for code in LANGS}] + [{code: comp_page(slug, code) for code in LANGS} for slug in kept]:
        alt = "".join(f'<xhtml:link rel="alternate" hreflang="{code}" href="{public_url(pages[code])}"/>' for code in LANGS)
        alt += f'<xhtml:link rel="alternate" hreflang="x-default" href="{public_url(pages["en"])}"/>'
        for code in LANGS:
            lines.append(f'<url><loc>{public_url(pages[code])}</loc><lastmod>{day}</lastmod><changefreq>daily</changefreq>{alt}</url>')
    block = SITEMAP_START + "\n" + "\n".join(lines) + "\n" + SITEMAP_END
    updated = re.sub(re.escape(SITEMAP_START) + ".*?" + re.escape(SITEMAP_END), lambda _: block, text, flags=re.S)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def write_stars(count: dict[str, int], many: int = 10) -> int:
    """equipes/vedettes.json : les équipes qui jouent le plus sur la saison, avec leur logo, pour le panneau « Équipes » du menu.
    Le menu est recopié dans les 847 pages du site : il ne peut pas porter les 83 équipes, seulement une poignée, et celles-ci
    se choisissent toutes seules d'après le calendrier plutôt qu'à la main.

    À égalité, l'ordre alphabétique départage : le fichier ne change pas d'un jour à l'autre sans raison."""
    found = []
    for slug, matches in sorted(count.items(), key=lambda pair: (-pair[1], pair[0])):
        if matches < 1:
            continue
        fiche = SITE / "equipes" / f"{slug}.json"
        if not fiche.exists():
            continue
        data = json.loads(fiche.read_text(encoding="utf-8"))
        logo = next((f"{team['id']}.webp" for team in (data.get("equipes") or [])
                     if isinstance(team, dict) and (SITE / "logos-equipes" / f"{team.get('id')}.webp").is_file()), "")
        found.append({"slug": slug, "nom": data.get("organisation", slug), "logo": logo, "matchs": matches})
        if len(found) == many:
            break
    path = SITE / "equipes/vedettes.json"
    text = json.dumps(found, ensure_ascii=False, indent=1) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return len(found)


if not LIVE_ONLY:
    print(f"Équipes du menu : {write_stars(activity)} mise(s) en avant")


# 3 quater) Les compétitions (5 langues) : une page par compétition en cours, et leur index.
# Le site n'avait de page que pour trois grands événements, alors qu'il affiche des matchs d'une quarantaine de compétitions :
# un visiteur voyait « IEM · Beijing 2026 » sans rien derrière. Les compétitions sont découvertes dans les matchs eux-mêmes (leur
# description dit « jeu · ligue · série ») et dans le calendrier de chaque jeu (14 requêtes, bien plus complet que les seuls
# calendriers d'équipes : 400 matchs contre 25). Les compétitions au nom d'un site de paris n'ont pas de page (règle « aucun pari »).
COMP_DIRS = {"en": "competitions", "fr": "fr/competitions", "es": "es/competiciones", "de": "de/wettbewerbe", "pt-BR": "pt/competicoes"}
COMP_MIN = 3  # en dessous, une compétition n'a pas de quoi faire une page
COMP_MAX_UP, COMP_MAX_RES = 60, 30
SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def comp_slug(label: str) -> str:
    """« IEM · Beijing 2026 » → « iem-beijing-2026 »."""
    import unicodedata
    plain = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return SLUG_CLEAN.sub("-", plain.lower()).strip("-")


def comp_label(description: str) -> str | None:
    """La compétition d'un match (« Counter-Strike 2 · IEM · Beijing 2026 » → « IEM · Beijing 2026 ») ; None quand la description
    ne nomme pas de compétition, ou qu'elle porte le nom d'un site de paris (le site n'en fait jamais la promotion)."""
    parts = [part.strip() for part in description.split("·")]
    if len(parts) < 2 or not parts[1] or BETTING.search(description):
        return None
    return " · ".join(parts[1:])


def comp_page(slug: str, code: str) -> str:
    return f"{COMP_DIRS[code]}/{slug}.html"


if not LIVE_ONLY:
    game_names_all = site_chrome.read_game_names(SITE)
    names_en = game_names_all.get("en", {})
    known_slugs = set(EVENTS)  # les trois grands événements gardent leur page à la racine
    found_comps: dict[str, dict] = {}
    for slug_game in site_chrome.GAMES:
        calendar = read_calendar(slug_game, API + "jeu/") or []
        for event in calendar:
            everything.setdefault(event.get("UID", event.get("URL")), event)  # enrichit aussi la page Live et les jeux
            label = comp_label(event.get("DESCRIPTION", ""))
            if not label:
                continue
            slug = comp_slug(label)
            if any(slug == known or slug.startswith(known + "-") for known in known_slugs):
                continue
            entry = found_comps.setdefault(slug, {"label": label, "game": slug_game, "events": [], "results": []})
            entry["events"].append(event)
    for found in week_results:
        label = comp_label(" · ".join(str(found.get(key, "")) for key in ("game", "league", "serie") if found.get(key)))
        if not label:
            continue
        slug = comp_slug(label)
        if slug in found_comps:
            found_comps[slug]["results"].append(found)
    kept = {slug: entry for slug, entry in sorted(found_comps.items())
            if len(entry["events"]) + len(entry["results"]) >= COMP_MIN}
    for slug, entry in kept.items():
        upcoming = sorted((e for e in entry["events"] if e["start"] >= NOW - timedelta(hours=3)), key=lambda e: e["start"])[:COMP_MAX_UP]
        results = sorted(entry["results"], key=lambda r: str(r.get("date", "")), reverse=True)[:COMP_MAX_RES]
        pages = {code: comp_page(slug, code) for code in LANGS}
        game_name = names_en.get(entry["game"], entry["game"])
        entry["pages"] = pages
        write_competition_pages(slug, entry["label"], game_name, upcoming, results, pages,
                                extra_links=comp_links(entry["game"], game_names_all), in_folder=True)
    write_competitions_index(kept, game_names_all)
    gone = prune_competitions(set(kept))
    write_competitions_sitemap(kept)
    print(f"Compétitions : {len(kept)} page(s) sur {len(found_comps)} trouvée(s), {gone} page(s) périmée(s) supprimée(s)")

# 3 ter) Pages de jeux : leurs prochains matchs et leurs derniers résultats. Une page de jeu disait ce que fait l'app pour ce jeu,
# mais rien de ce qui s'y passe. Tout vient de ce que ce script a déjà en mémoire — les calendriers des équipes (everything) et le
# flux des résultats de la semaine (week_results) : aucune requête de plus, aucun texte nouveau (les libellés sont ceux des pages
# d'événements). Le bloc se glisse entre ses repères, juste avant le bloc du calendrier du jeu.
GAME_START, GAME_END = "<!-- jeu-matchs -->", "<!-- /jeu-matchs -->"
GAME_BLOCK = re.compile(re.escape(GAME_START) + ".*?" + re.escape(GAME_END), re.S)
# Où poser le bloc, par ordre de préférence : juste avant le calendrier du jeu, sinon avant le lien du guide du Blog (les pages
# des jeux sans calendrier ni liste d'équipes n'ont que celui-là). Une page qui n'a ni l'un ni l'autre est laissée telle quelle.
GAME_ANCHORS = ("<!-- calendrier-jeu -->", "<!-- blog-guide -->")
GAME_UPCOMING, GAME_RESULTS = 8, 8  # ce qu'on montre : de quoi voir la semaine sans noyer la page


def game_block(code: str, t: dict, upcoming: list[dict], results: list[dict]) -> str:
    """Le bloc d'une page de jeu : ses prochains matchs groupés par jour, puis ses derniers résultats (scores floutés)."""
    x = EXTRA[code]
    groups: dict = {}
    for event in upcoming[:GAME_UPCOMING]:
        groups.setdefault(event["start"].astimezone(PARIS).date(), []).append(event)
    days = []
    for day, evs in groups.items():
        label = f'{t["days"][day.weekday()]} {day.day} {t["months"][day.month - 1]}'
        days.append(f'<h3 class="jour">{label[0].upper() + label[1:]}</h3><ul class="matchs">{"".join(match_item(e, t, False) for e in evs)}</ul>')
    main = f'<h2 class="jour">{x["ev_up"]}</h2>' + ("".join(days) if days else f'<p>{t["none"]}</p>')
    return GAME_START + main + f'<h2 class="jour">{x["results"]}</h2>' + results_html(results[:GAME_RESULTS], t, x) + GAME_END


COMPS_LIST = re.compile(r'<ul class="comps">.*?</ul>', re.S)


def write_game_comps(site: Path, game: str, comps: list[tuple[str, str]]) -> list[str]:
    """Remplace la liste « Compétitions suivies » d'une page de jeu (du texte mort : « Majors », « IEM »…) par les liens vers les
    pages des compétitions réellement suivies pour ce jeu. Sans compétition, la liste d'origine est laissée telle quelle."""
    done: list[str] = []
    if not comps:
        return done
    for code in LANGS:
        path = site / f"{site_chrome.GAME_DIRS[code]}/{game}.html"
        if not path.is_file():
            continue
        page = path.read_text(encoding="utf-8")
        if not COMPS_LIST.search(page):
            continue
        up = "../" * (site_chrome.GAME_DIRS[code].count("/") + 1)
        items = "".join(f'<li><a href="{up}{comp_page(slug, code)}">{html.escape(label)}</a></li>' for slug, label in comps)
        updated = COMPS_LIST.sub(lambda _: f'<ul class="comps">{items}</ul>', page, count=1)
        if updated != page:
            path.write_text(updated, encoding="utf-8")
            done.append(f"{site_chrome.GAME_DIRS[code]}/{game}.html")
    return done


def write_game_blocks(site: Path, slug: str, upcoming: list[dict], results: list[dict]) -> list[str]:
    """Pose (ou remet à jour) le bloc sur les cinq pages du jeu ; rend les chemins réécrits. Une page sans le repère du calendrier
    du jeu est laissée telle quelle, et une page que le bloc ne change pas n'est pas réécrite (pas de commit pour rien)."""
    done: list[str] = []
    for code, t in LANGS.items():
        path = site / f"{site_chrome.GAME_DIRS[code]}/{slug}.html"
        if not path.is_file():
            continue
        page = path.read_text(encoding="utf-8")
        block = game_block(code, t, upcoming, results)
        anchor = next((found for found in GAME_ANCHORS if found in page), None)
        if GAME_BLOCK.search(page):
            updated = GAME_BLOCK.sub(lambda _: block, page, count=1)
        elif anchor is not None:
            updated = page.replace(anchor, block + anchor, 1)
        else:
            continue
        if ".resultats{" not in updated:
            updated = updated.replace("</style>", STYLE + "</style>", 1)
        if updated != page:
            path.write_text(with_local_times(public_urls(updated)), encoding="utf-8")
            done.append(f"{site_chrome.GAME_DIRS[code]}/{slug}.html")
    return done


if not LIVE_ONLY:
    # « Compétitions suivies » : la liste écrite à la main (« Majors », « IEM »…) devient les liens des compétitions du jeu.
    comps_by_game: dict[str, list[tuple[str, str]]] = {}
    for comp_slug_found, comp_entry in kept.items():
        comps_by_game.setdefault(comp_entry["game"], []).append((comp_slug_found, comp_entry["label"]))
    for game_slug_found, comps in comps_by_game.items():
        write_game_comps(SITE, game_slug_found, sorted(comps, key=lambda pair: pair[1].lower()))
    game_names_en = site_chrome.read_game_names(SITE).get("en", {})
    by_game: dict[str, list[dict]] = {}
    for event in everything.values():
        if NOW - timedelta(hours=3) <= event["start"] <= NOW + timedelta(days=7):
            slug = live.game_slug(event.get("DESCRIPTION", ""), game_names_en)
            if slug:
                by_game.setdefault(slug, []).append(event)
    results_by_game: dict[str, list[dict]] = {}
    for found in week_results:
        slug = live.game_slug(str(found.get("game", "")), game_names_en)
        if slug:
            results_by_game.setdefault(slug, []).append(found)
    touched = 0
    for slug in site_chrome.GAMES:
        upcoming = sorted(by_game.get(slug, []), key=lambda e: e["start"])
        touched += len(write_game_blocks(SITE, slug, upcoming, results_by_game.get(slug, [])))
    print(f"Pages de jeux : {touched} mise(s) à jour ({len(by_game)} jeux avec des matchs, {len(results_by_game)} avec des résultats)")

# 3 bis) Robot de l'heure : les pages de compétition ne sont refabriquées que le matin, un résultat y restait donc invisible
# jusqu'à 24 heures. On ne refabrique rien ici — on remplace seulement leur bloc de résultats entre ses repères, avec le flux de
# l'événement (une requête par événement). Rien ne change, rien n'est réécrit : le robot ne commite alors pas.
if LIVE_ONLY:
    for slug in EVENTS:
        written = refresh_results(SITE, slug, LANGS, EXTRA, read_results(slug))
        if written:
            print(f"Résultats : {len(written)} page(s) de {slug} mises à jour")

# 4) Live (5 langues) : les matchs du jour, toutes équipes et grands événements confondus ; l'état (en direct, terminé, à venir) vient
# du script de la page, qui compare les horaires à l'heure du visiteur, et de la fin notée par le robot (live_suivi.py : le flux de
# résultats confirme qu'un match est fini). Chaque match mène à sa propre page (live_match.py : fr/live/<id>.html…), pas à match.html,
# la page de renvoi vers l'app, inutile sur ordinateur. Tout est fabriqué en mémoire avant d'écrire quoi que ce soit : un échec ici
# n'envoie ni une page Live qui mènerait à des pages absentes, ni des pages orphelines, et n'empêche pas d'envoyer les pages de matchs.
# Le matin les matchs du jour viennent des calendriers et sont gardés dans suivi/live.json ; avec --live, de ce fichier.
try:
    saved, known = live_suivi.load(live_suivi.PATH)
    today_events = saved if LIVE_ONLY else live.select(everything.values(), NOW)
    known = live_suivi.keep_known(known, today_events)
    noted = live_suivi.new_finals(today_events, week_results, NOW, known)
    finals = {**known, **noted}
    for mid, fin in noted.items():
        print(f"Live : fin notée du match {mid} ({' – '.join(fin['equipes'])}), score {'caché' if fin['score'] is None else 'confirmé'}")
    if LIVE_ONLY and not noted:
        print(f"Live : {len(today_events)} matchs suivis, aucune fin nouvelle")
    else:
        game_names = site_chrome.read_game_names(SITE)
        asked = diffusions.resolve()  # où regarder : vrai nom des chaînes Twitch, direct en cours des chaînes YouTube
        print(f"Live : {asked['youtube']} chaîne(s) YouTube en direct, {asked['twitch']} chaîne(s) Twitch vérifiée(s)")
        home_pages = {code: (SITE / site_chrome.HOMES[code]).read_text(encoding="utf-8") for code in LANGS}
        event_pages = {code: [(name, event_page(slug, code)) for slug, (name, _) in EVENTS.items()] for code in LANGS}
        try:  # temps forts du jour (blog-src/topplays.json, écrit chaque matin par topplays.py) ; illisible : on s'en passe
            clips = blog.visible_topplays(blog.load_topplays(SITE), NOW.date())
        except Exception as error:
            clips = {}
            print(f"Live : temps forts ignorés ({error})")
        match_pages = live_match.build(SITE, today_events, LANGS, home_pages, game_names, event_pages,
                                       {code: t["file"] for code, t in LANGS.items()}, SEO, finals, clips)
        live_pages = {live.PAGES[code]: live.render_page(code, (SITE / t["news"]).read_text(encoding="utf-8"), today_events, NOW, t, home_pages[code],
                                                         game_names, SEO, finals) for code, t in LANGS.items()}
        for name, page in {**live_pages, **match_pages}.items():
            (SITE / name).parent.mkdir(parents=True, exist_ok=True)
            (SITE / name).write_text(with_local_times(page), encoding="utf-8")
        removed = live_match.prune(SITE, NOW, set(match_pages))
        live_suivi.save(live_suivi.PATH, today_events, finals, TODAY)
        print(f"Live : {len(today_events)} matchs du jour, {len(finals)} terminé(s) confirmé(s), {len(match_pages)} pages de match, {len(removed)} supprimée(s)")
except Exception as error:
    print(f"Live : page non fabriquée ({error})")
    if LIVE_ONLY:  # le robot de l'heure ne doit pas rester vert quand il ne fait plus rien
        sys.exit(1)

print(f"{len(organisations)} équipes, {len(week)} matchs cette semaine, {len(week_results)} résultats")
