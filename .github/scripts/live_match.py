"""Une page par match de la page Live (« fr/live/1713096.html »), pour que cliquer un match sur ordinateur ne renvoie pas vers l'app.

Avant, chaque match de la page Live menait à match.html?id=…, la page de renvoi de l'app : elle tente d'ouvrir esportly://match/…,
ce qui n'a aucun sens sur ordinateur. Maintenant chaque match du jour a sa page dans chaque langue (dossier DIRS : live/ en anglais,
fr/live/, es/live/, de/live/, pt/live/, comme blog/ et fr/blog/ ; les liens se lisent à travers _prefix, « ../../ » hors anglais) : le match (état en direct / terminé / à venir calculé par l'horloge
du visiteur avec le script de la page Live, heure locale ajoutée par matchs.py), les équipes avec leur fiche, comment suivre le match
avec eSportly (direct, alerte, sans spoiler), et les pages utiles (jeu, guide du Blog, grand événement, matchs de la semaine, Live).
Le bouton « Ouvrir ce match dans l'app » (vers match.html?id=…, qui ouvre l'app) n'apparaît que sur les écrans tactiles
(@media (hover:none) and (pointer:coarse)) : sur ordinateur, la page se lit comme un article.

Le calendrier du relais ne donne que les équipes, le jeu, la compétition et les horaires : la page n'invente rien d'autre. Elle est en
noindex (peu de texte propre à chaque match) et hors du sitemap. Fabriquée comme les guides du Blog : depuis la page du jeu du
match (celle de league-of-legends pour un jeu inconnu du site), dont elle garde la couleur, la CSP et le pied de page. Une page dont
le match a commencé il y a plus de KEEP est supprimée au passage suivant (prune).
"""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import actualites as an
import blog
import diffusions
import lecteur_differe
import live
import site_chrome

KEEP = timedelta(days=3)  # une page de match reste en ligne 3 jours après son coup d'envoi
DIRS = live.DIRS
ROBOTS = '<meta name="robots" content="noindex, follow">'
SPLIT = re.compile(r"\s+[–-]\s+")  # « Vitality – G2 » : les deux équipes
DATA_START = re.compile(r'data-start="([^"]+)"')
BLUR = "filter:blur(12px)"  # style en ligne du score caché : il tient même sans feuille de style (jamais de spoiler par accident)

# Textes de la page, par langue (mêmes clés partout). Les états (« En direct », « Terminé », « À venir ») sont ceux de la page Live.
# `h_result`, `spoil`, `reveal` et `score_final` : le bloc « Résultat » d'un match dont la fin est notée (live_suivi.py), score caché.
TEXTS = {
    "fr": dict(title="{match} : horaire et comment suivre le match", lead="Coup d'envoi {day} à {hour}, heure de Paris.",
               meta="{match} ({comp}) : coup d'envoi {day} à {hour}, heure de Paris, et comment suivre le match avec eSportly.",
               h_match="Le match", h_teams="Les équipes", h_follow="Comment suivre ce match", h_more="Pour aller plus loin",
               h_video="Les temps forts", h_watch="Où regarder", watch_open="Ouvrir la chaîne", watch_also="Aussi en direct sur ", watch_on="{match} est diffusé sur la chaîne officielle de la compétition, {c}.", watch_spoil="Le direct montre le score en cours : ne le lance pas si tu veux garder la surprise.", watch_title="Direct de {c}", watch_note="Chaîne officielle de la compétition :", video_spoil="La vidéo peut montrer le résultat : elle ne se charge que si tu cliques.", video_reveal="Voir les temps forts",
               h_result="Résultat", spoil="Le score reste caché tant que tu ne le demandes pas.", reveal="Voir le score",
               score_final="il est dans l'app, sur l'écran verrouillé et dans la Dynamic Island ; ici, il reste caché tant que tu ne le demandes pas.",
               team_more="fiche et prochains matchs",
               follow=(("Le direct", "quand le match est diffusé sur Twitch, YouTube ou Kick, eSportly l'affiche dans la fiche du match, seulement si tu le lances."),
                       ("Une alerte", "1 heure et 30 minutes avant le match, au coup d'envoi et au résultat, réglable équipe par équipe."),
                       ("Sans spoiler", "les scores restent cachés jusqu'à ce que tu décides de les voir."),
                       ("Le score", "il est dans l'app, sur l'écran verrouillé et dans la Dynamic Island ; cette page ne publie ni score ni résultat.")),
               open_app="Ouvrir ce match dans l'app", live_all="Tous les matchs du jour", week="Les matchs de la semaine",
               guide="Guide : {game}", game="{game} sur eSportly"),
    "en": dict(title="{match}: kick-off time and how to follow the match", lead="Kick-off {day} at {hour}, Paris time.",
               meta="{match} ({comp}): kick-off {day} at {hour}, Paris time, and how to follow the match with eSportly.",
               h_match="The match", h_teams="The teams", h_follow="How to follow this match", h_more="Keep exploring",
               h_video="Highlights", h_watch="Where to watch", watch_open="Open the channel", watch_also="Also live on ", watch_on="{match} is broadcast on the competition's official channel, {c}.", watch_spoil="A live stream shows the current score: don't press play if you want to keep the surprise.", watch_title="{c} live stream", watch_note="Official channel of the competition:", video_spoil="The video may show the result: it only loads if you click.", video_reveal="Show the highlights",
               h_result="Result", spoil="The score stays hidden until you ask for it.", reveal="Show the score",
               score_final="it is in the app, on your Lock Screen and in the Dynamic Island; here it stays hidden until you ask for it.",
               team_more="profile and next matches",
               follow=(("Live stream", "when the match is streamed on Twitch, YouTube or Kick, eSportly shows it on the match page, only if you start it."),
                       ("An alert", "1 hour and 30 minutes before the match, at kick-off and at the result, adjustable team by team."),
                       ("No spoilers", "scores stay hidden until you decide to see them."),
                       ("The score", "it is in the app, on your Lock Screen and in the Dynamic Island; this page publishes no score or result.")),
               open_app="Open this match in the app", live_all="All of today's matches", week="Matches this week",
               guide="Guide: {game}", game="{game} on eSportly"),
    "es": dict(title="{match}: horario y cómo seguir el partido", lead="Comienza el {day} a las {hour}, hora de París.",
               meta="{match} ({comp}): comienza el {day} a las {hour}, hora de París, y cómo seguir el partido con eSportly.",
               h_match="El partido", h_teams="Los equipos", h_follow="Cómo seguir este partido", h_more="Para ir más lejos",
               h_video="Lo mejor del día", h_watch="Dónde verlo", watch_open="Abrir el canal", watch_also="También en directo en ", watch_on="{match} se emite en el canal oficial de la competición, {c}.", watch_spoil="El directo muestra el marcador en curso: no le des al play si quieres mantener la sorpresa.", watch_title="Directo de {c}", watch_note="Canal oficial de la competición:", video_spoil="El vídeo puede mostrar el resultado: solo se carga si haces clic.", video_reveal="Ver lo mejor del día",
               h_result="Resultado", spoil="El marcador sigue oculto hasta que lo pidas.", reveal="Ver el marcador",
               score_final="está en la app, en la pantalla bloqueada y en la Dynamic Island; aquí sigue oculto hasta que lo pidas.",
               team_more="ficha y próximos partidos",
               follow=(("El directo", "cuando el partido se emite en Twitch, YouTube o Kick, eSportly lo muestra en la ficha del partido, solo si lo inicias."),
                       ("Un aviso", "1 hora y 30 minutos antes del partido, al comenzar y con el resultado, ajustable equipo por equipo."),
                       ("Sin spoilers", "los marcadores siguen ocultos hasta que decidas verlos."),
                       ("El marcador", "está en la app, en la pantalla bloqueada y en la Dynamic Island; esta página no publica marcadores ni resultados.")),
               open_app="Abrir este partido en la app", live_all="Todos los partidos de hoy", week="Los partidos de la semana",
               guide="Guía: {game}", game="{game} en eSportly"),
    "de": dict(title="{match}: Uhrzeit und wie du das Match verfolgst", lead="Anpfiff am {day} um {hour} Uhr, Pariser Zeit.",
               meta="{match} ({comp}): Anpfiff am {day} um {hour} Uhr, Pariser Zeit, und wie du das Match mit eSportly verfolgst.",
               h_match="Das Match", h_teams="Die Teams", h_follow="So verfolgst du dieses Match", h_more="Weiterlesen",
               h_video="Die Highlights", h_watch="Wo schauen", watch_open="Kanal öffnen", watch_also="Ebenfalls live auf ", watch_on="{match} läuft auf dem offiziellen Kanal des Wettbewerbs, {c}.", watch_spoil="Ein Livestream zeigt den laufenden Spielstand: Starte ihn nicht, wenn du dich überraschen lassen willst.", watch_title="Livestream von {c}", watch_note="Offizieller Kanal des Wettbewerbs:", video_spoil="Das Video kann das Ergebnis zeigen: Es lädt erst, wenn du klickst.", video_reveal="Highlights zeigen",
               h_result="Ergebnis", spoil="Das Ergebnis bleibt verborgen, bis du es anzeigst.", reveal="Ergebnis zeigen",
               score_final="steht in der App, auf dem Sperrbildschirm und in der Dynamic Island; hier bleibt es verborgen, bis du es anzeigst.",
               team_more="Profil und nächste Matches",
               follow=(("Der Livestream", "läuft das Match auf Twitch, YouTube oder Kick, zeigt eSportly es auf der Match-Seite, nur wenn du es startest."),
                       ("Eine Meldung", "1 Stunde und 30 Minuten vor dem Match, zum Anpfiff und zum Ergebnis, pro Team einstellbar."),
                       ("Ohne Spoiler", "Ergebnisse bleiben verborgen, bis du sie sehen willst."),
                       ("Das Ergebnis", "steht in der App, auf dem Sperrbildschirm und in der Dynamic Island; diese Seite zeigt kein Ergebnis.")),
               open_app="Dieses Match in der App öffnen", live_all="Alle Matches von heute", week="Spiele der Woche",
               guide="Guide: {game}", game="{game} bei eSportly"),
    "pt-BR": dict(title="{match}: horário e como acompanhar a partida", lead="Início em {day} às {hour}, horário de Paris.",
                  meta="{match} ({comp}): início em {day} às {hour}, horário de Paris, e como acompanhar a partida com o eSportly.",
                  h_match="A partida", h_teams="Os times", h_follow="Como acompanhar esta partida", h_more="Para ir além",
                  h_video="Os melhores momentos", h_watch="Onde assistir", watch_open="Abrir o canal", watch_also="Também ao vivo em ", watch_on="{match} é transmitida no canal oficial da competição, {c}.", watch_spoil="A transmissão mostra o placar atual: não dê play se quiser manter a surpresa.", watch_title="Transmissão de {c}", watch_note="Canal oficial da competição:", video_spoil="O vídeo pode mostrar o resultado: ele só carrega se você clicar.", video_reveal="Ver os melhores momentos",
               h_result="Resultado", spoil="O placar fica escondido até você pedir.", reveal="Ver o placar",
                  score_final="está no app, na tela bloqueada e na Dynamic Island; aqui ele fica escondido até você pedir.",
                  team_more="ficha e próximas partidas",
                  follow=(("A transmissão", "quando a partida passa na Twitch, no YouTube ou no Kick, o eSportly mostra na página da partida, só se você iniciar."),
                          ("Um alerta", "1 hora e 30 minutos antes da partida, no início e no resultado, ajustável time a time."),
                          ("Sem spoiler", "os placares ficam ocultos até você decidir ver."),
                          ("O placar", "está no app, na tela bloqueada e na Dynamic Island; esta página não publica placar nem resultado.")),
                  open_app="Abrir esta partida no app", live_all="Todas as partidas de hoje", week="Partidas da semana",
                  guide="Guia: {game}", game="{game} no eSportly"),
}

MATCH_STYLE = (
    ".mcard{display:grid;gap:2px;padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}",
    ".mcard time{font-size:15px;color:var(--or);font-weight:700}",
    ".mcard b{font-size:20px}",
    ".mcard small{font-size:14px;color:var(--soft)}",
    '.matchs li[data-state="live"] .mcard{border-color:var(--or);background:color-mix(in srgb,var(--or) 10%,var(--surface))}',
    '.matchs li[data-state="done"] .mcard{opacity:.62}',
    ".mwatch{margin:0 0 10px}",
    ".mwatch .wlead{margin:10px 0 2px;font-size:15px;color:var(--soft)}",
    ".mwatch .topnote{margin:0}",
    ".mwatch .walso{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 6px;font-size:14px;color:var(--muted)}",
    ".mwatch .walso a{padding:4px 12px;border-radius:999px;border:1px solid var(--border);background:var(--surface);"
    "color:var(--text);font-weight:700;text-decoration:none}",
    # Le direct garde ses proportions quelle que soit la largeur, et ne charge rien tant que le bloc est replié.
    ".wframe{position:relative;aspect-ratio:16/9;margin:12px 0 0;border-radius:14px;overflow:hidden;background:#000}",
    ".wframe iframe{position:absolute;inset:0;width:100%;height:100%;border:0}",
    ".mres{padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}",
    ".mres summary{cursor:pointer;list-style:none;display:grid;gap:8px;justify-items:start}",
    ".mres summary::-webkit-details-marker{display:none}",
    ".mres .voir{font-size:14px;font-weight:700;color:var(--text);text-decoration:underline}",
    ".mres[open] .voir{display:none}",
    ".mres .score{display:block;margin:0;font-size:18px;user-select:none}",
    ".mres .score b{font:700 26px var(--display);margin:0 8px}",
    # Le score est écrit en clair mais flouté par son style en ligne (il tient même sans feuille de style) ; l'ouverture le révèle,
    # la règle de la feuille l'emporte sur le style en ligne grâce à !important.
    ".mres[open] .score{filter:none!important;user-select:auto}",
    "@media (prefers-reduced-motion:no-preference){.mres .score{transition:filter .25s ease}}",
    ".open-app{display:none;margin:20px 0 0}",
    "@media (hover:none) and (pointer:coarse){.open-app{display:block}}",
    # Temps forts du match : la carte de lecture au clic du Blog (aucune ressource de tiers tant qu'on n'a pas cliqué), rangée
    # derrière un « details » comme le score, parce qu'un titre de vidéo peut dire qui a gagné.
    ".mvid{margin:0;padding:14px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--border)}",
    ".mvid>summary{cursor:pointer;list-style:none}",
    ".mvid>summary::-webkit-details-marker{display:none}",
    ".mvid .voir{font-size:14px;font-weight:700;color:var(--text);text-decoration:underline}",
    ".mvid[open]>summary{display:none}",
    ".mvid .play{display:grid;gap:10px;align-content:start;max-width:560px}",
    ".video{position:relative;display:grid;place-items:center;aspect-ratio:16/9;border-radius:14px;overflow:hidden;background:var(--raised);border:1px solid var(--border);text-decoration:none}",
    ".video .btn{display:grid;place-items:center;width:64px;height:64px;border-radius:50%;background:var(--or);color:var(--on-or);font-size:24px;line-height:1;padding-left:4px;box-sizing:border-box}",
    ".video:hover .btn{transform:scale(1.08)}",
    ".video:focus-visible{outline:2px solid var(--or);outline-offset:3px}",
    ".video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}",
    ".mvid .legend{display:grid;gap:2px;margin:0}",
    ".mvid .legend b{font-size:17px;line-height:1.3;color:var(--text)}",
    ".mvid .legend small{font-size:14px;color:var(--soft)}",
    ".mvid .topnote{margin:10px 0 0;font-size:14px;color:var(--muted)}",
)
CSS = "\n".join([*site_chrome.MENU_STYLE, *site_chrome.FOOTER_STYLE, an.STYLE, live.STYLE, *MATCH_STYLE])


def _prefix(lang: str) -> str:
    """Ce qui précède un chemin depuis la racine, vu d'une page de match de la langue : « ../ » en anglais (live/), « ../../ » sinon."""
    return site_chrome.prefix_for(f"{DIRS[lang]}/x.html")


def teams_of(summary: str) -> list[str]:
    """Les deux équipes de « Vitality – G2 » ; une liste vide si le titre n'en nomme pas exactement deux."""
    names = [name.strip() for name in SPLIT.split(summary) if name.strip()]
    return names if len(names) == 2 else []


def template_file(lang: str, event: dict, names_en: dict[str, str]) -> str:
    """La page qui sert de modèle au match : la page de son jeu dans la langue, celle de league-of-legends pour un jeu inconnu du site."""
    game = live.game_slug(event.get("DESCRIPTION", ""), names_en) or blog.TEMPLATE_GAME
    return f"{site_chrome.GAME_DIRS[lang]}/{game}.html"


def _day(event: dict, t: dict) -> str:
    local = event["start"].astimezone(an.paris())
    return f'{t["days"][local.weekday()]} {local.day} {t["months"][local.month - 1]}'


def _link(href: str, text: str, attrs: str = "") -> str:
    return f'<a href="{html.escape(href)}"{attrs}>{html.escape(text)}</a>'


def video_for(videos: list[dict], day: date) -> dict | None:
    """La vidéo de temps forts qui va avec un match joué le `day` (jour de Paris) : parmi les vidéos du jeu (blog-src/topplays.json,
    choisies le matin par topplays.py), la plus récente publiée le jour du match ou le lendemain (les temps forts sortent souvent la
    nuit suivante). None quand aucune ne tombe dans cette fenêtre : la page n'invente rien et reste sans bloc vidéo."""
    window = {day.isoformat(), (day + timedelta(days=1)).isoformat()}
    found = [v for v in videos if isinstance(v, dict) and v.get("published") in window and isinstance(v.get("id"), str)]
    return max(found, key=lambda v: v["published"]) if found else None


def render_video(lang: str, video: dict, t: dict) -> str:
    """Le bloc « temps forts » d'un match terminé : la carte de lecture au clic du Blog (lien vers YouTube sans JavaScript, lecteur
    youtube-nocookie au clic), rangée derrière un « details » parce qu'un titre de vidéo peut nommer le vainqueur. Rien n'est chargé
    depuis YouTube tant que le visiteur n'a pas cliqué."""
    x, esc = TEXTS[lang], html.escape
    vid, title = str(video["id"]), str(video.get("title", ""))
    published = str(video.get("published", ""))
    try:
        when = date.fromisoformat(published)
        shown = f'{when.day} {t["months"][when.month - 1]}'
    except ValueError:
        shown = published
    card = (f'<li class="play"><a class="video" href="{esc(blog.WATCH_URL + quote(vid, safe=""))}" data-id="{esc(vid, quote=True)}" '
            f'aria-label="{esc(blog.LABELS[lang]["play"].format(title=title), quote=True)}" rel="noopener">'
            f'<span class="btn" aria-hidden="true">▶</span></a>'
            f'<p class="legend"><b>{esc(title)}</b><small>{esc(str(video.get("channel", "")))} · '
            f'<time datetime="{esc(published, quote=True)}">{esc(shown)}</time></small></p></li>')
    return (f'<h2>{esc(x["h_video"])}</h2><details class="mvid"><summary><span class="voir">{esc(x["video_reveal"])}</span></summary>'
            f'<p class="maj">{esc(x["video_spoil"])}</p><ul class="topplays">{card}</ul>'
            f'<p class="topnote">{esc(blog.LABELS[lang]["topnote"])}</p></details>')


FRAME_SRC = re.compile(r"frame-src ([^;]*)")


def _with_frames(page: str, sources: tuple[str, ...]) -> str:
    """La CSP de la page avec `sources` dans frame-src : ajoutées à celle qui existe déjà (le lecteur de temps forts a pu la
    poser), sinon une directive frame-src est créée juste avant object-src. Une page refabriquée ne change pas.

    Lève ChromeError sans balise de CSP ou sans object-src : on ne devine pas où placer l'ajout."""
    meta = site_chrome.CSP_META.search(page)
    if meta is None:
        raise site_chrome.ChromeError(["balise Content-Security-Policy introuvable, impossible d'ajouter frame-src"])
    policy, found = meta.group(1), FRAME_SRC.search(meta.group(1))
    if found is not None:
        missing = [source for source in sources if source not in found.group(1).split()]
        if not missing:
            return page
        policy = policy[:found.end(1)] + " " + " ".join(missing) + policy[found.end(1):]
    else:
        if blog.OBJECT_SRC.search(policy) is None:
            raise site_chrome.ChromeError(["CSP sans object-src 'none', impossible d'ajouter frame-src"])
        policy = blog.OBJECT_SRC.sub(lambda hit: f"frame-src {' '.join(sources)}; {hit.group(0)}", policy, count=1)
    return page[:meta.start(1)] + policy + page[meta.end(1):]


def render_watch(lang: str, event: dict) -> str:
    """Le direct du match, tout en haut de sa page : le lecteur de la chaîne qui diffuse sa compétition, visible d'emblée —
    c'est ce qu'on vient chercher. Rien ne démarre tout seul (le lecteur est en pause et muet) et une ligne prévient qu'un
    direct montre le score. Vide quand la compétition n'a pas de chaîne connue (diffusions.py) : pas de lecteur au hasard."""
    streams = diffusions.channels_for(event.get("DESCRIPTION", ""))
    if not streams:
        return ""
    channel, others = streams[0], streams[1:]
    x, esc = TEXTS[lang], html.escape
    title = esc(x["watch_title"].format(c=channel["label"]), quote=True)
    match = esc(event.get("SUMMARY", ""))
    # Les autres chaînes (YouTube quand le lecteur est sur Twitch, la deuxième chaîne d'un diffuseur qui tourne en parallèle).
    links = "".join(f'<a href="{esc(stream["page"], quote=True)}" rel="noopener nofollow" target="_blank">{esc(stream["site"])}</a>'
                    for stream in others)
    also = f'<p class="walso">{esc(x["watch_also"])}{links}</p>' if links else ""
    # Le lecteur en premier, sa légende dessous : un titre et une phrase au-dessus repousseraient le direct de 100 px,
    # c'est-à-dire hors de l'écran sur un portable.
    return (f'<section class="mwatch" aria-label="{esc(x["h_watch"], quote=True)}">'
            f'<div class="wframe"><iframe src="{esc(channel["player"], quote=True)}" title="{title}" loading="lazy" '
            f'allowfullscreen referrerpolicy="no-referrer"></iframe></div>'
            f'<p class="wlead">{esc(x["watch_on"]).format(match=f"<b>{match}</b>", c=esc(channel["label"]))} '
            f'<a href="{esc(channel["page"], quote=True)}" rel="noopener nofollow" target="_blank">{esc(x["watch_open"])}</a></p>'
            f'{also}<p class="topnote">{esc(x["watch_spoil"])}</p></section>')


def render_main(lang: str, event: dict, t: dict, names: dict[str, dict[str, str]], home: tuple[str, str], mid: str, links: dict,
                final: dict | None = None, video: dict | None = None, page_name: str | None = None) -> str:
    """Le <main> d'une page de match : fil d'Ariane, héros, le match (état et heure), son résultat (caché derrière un bouton) si sa fin
    est notée, bouton de l'app (écrans tactiles), équipes, comment suivre, pages utiles. `final` : la fin notée (live_suivi.py) ;
    sans score à deux nombres, le match est « terminé » mais la page n'a rien à montrer. `links` (adresses vues de la page, en « ../ ») : `teams` {nom en minuscules: adresse de la fiche},
    `event` (libellé, adresse) du grand événement, `week` adresse des matchs de la semaine, `guide` adresse du guide du Blog."""
    x, labels, up = TEXTS[lang], live.LABELS[lang], _prefix(lang)
    summary, description = event.get("SUMMARY", "Match"), event.get("DESCRIPTION", "")
    game = live.game_slug(description, names.get("en", {}))
    game_name = names.get(lang, {}).get(game, "") if game else ""
    hour, day = live._hour(event), _day(event, t)
    esc = html.escape
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{esc(home[0])}">{esc(home[1])}</a> › '
              f'<a href="{up}{live.PAGES[lang]}">{site_chrome.LIVE_LABEL}</a> › <span>{esc(summary)}</span></nav>')
    # Pas de bouton dans le héros : sur la page d'un match, la colonne principale est pour le match, l'application est à droite.
    hero = (f'<section class="hero mhero"><span class="big" aria-hidden="true">eS</span><div class="kicker">{esc(description) or site_chrome.LIVE_LABEL}</div>'
            f'<h1>{esc(summary)}</h1><p class="lead">{esc(x["lead"].format(day=day, hour=hour))}</p></section>')
    attrs = (f' data-start="{event["start"].isoformat()}" data-end="{event["end"].isoformat()}"' + (f' data-game="{game}"' if game else "")
             + (f' data-final="{esc(str(final.get("vu", "")), quote=True)}"' if final is not None else ""))
    state = "".join(f' data-{key}="{esc(labels[key], quote=True)}"' for key in ("live", "done", "soon", "one", "many", "none", "next"))
    card = (f'<h2>{x["h_match"]}</h2><p class="live-now" id="live-now" hidden{state}></p><ul class="matchs"><li{attrs}><div class="mcard">'
            f'<span class="etat"></span><time datetime="{event["start"].isoformat()}">{esc(day)}, {hour}</time><b>{esc(summary)}</b>'
            f'<small>{esc(description)}</small></div></li></ul>')
    score = (final or {}).get("score")
    shown = final is not None and isinstance(score, list) and len(score) == 2 and isinstance(final.get("equipes"), list) and len(final["equipes"]) == 2
    if shown:
        card += (f'<h2>{x["h_result"]}</h2><p class="maj">{x["spoil"]}</p><details class="mres">'
                 f'<summary><span class="score" style="{BLUR}">{esc(str(final["equipes"][0]))} <b>{score[0]} – {score[1]}</b> '
                 f'{esc(str(final["equipes"][1]))}</span><span class="voir">{x["reveal"]}</span></summary></details>')
    if shown and video is not None:  # les temps forts n'ont de sens qu'une fois le match fini, et jamais avant le clic
        card += render_video(lang, video, t)

    teams = ""
    rows = [f'<li><b>{esc(name)}</b> · {_link(links["teams"][name.lower()], x["team_more"])}</li>'
            for name in teams_of(summary) if name.lower() in links.get("teams", {})]
    if rows:
        teams = f'<h2>{x["h_teams"]}</h2><ul class="list">{"".join(rows)}</ul>'
    steps = [(head, x["score_final"] if shown and i == 3 else text) for i, (head, text) in enumerate(x["follow"])]  # le score : « caché ici » s'il est derrière le bouton
    follow = (f'<h2>{x["h_follow"]}</h2><ul class="list">' + "".join(f'<li><b>{esc(head)}</b> {esc(text)}</li>' for head, text in steps) + "</ul>")
    more = []
    if game:
        more.append(_link(f"{up}{site_chrome.GAME_DIRS[lang]}/{game}.html", x["game"].format(game=game_name or game)))
    if links.get("guide") and game:
        more.append(_link(links["guide"], x["guide"].format(game=game_name or game)))
    if links.get("event"):
        more.append(_link(links["event"][1], links["event"][0]))
    if links.get("week"):
        more.append(_link(links["week"], x["week"]))
    more.append(_link(f"{up}{live.PAGES[lang]}", x["live_all"]))
    nav = f'<h2>{x["h_more"]}</h2><nav class="others" aria-label="{esc(x["h_more"])}">{"".join(more)}</nav>'
    # Le direct passe avant la carte du match : sur la page d'un match qui n'est pas fini, c'est ce qu'on vient chercher.
    # Après le match, la chaîne diffuse autre chose : plus de lecteur.
    watch = "" if shown else render_watch(lang, event)
    side = live.render_side(lang, f"{live.DIRS[lang]}/{page_name or mid}", app=f"{up}match.html?id={mid}", app_label=x["open_app"])
    return crumbs + hero + f'<div class="livew"><div class="livec">{watch + card + teams + follow + nav}</div>{side}</div>' 


def json_ld(lang: str, event: dict, mid: str) -> str:
    """Les données « événement sportif » du match, avec l'adresse de la page (celle de l'app reste celle du calendrier)."""
    url = an.public_url(f"{live.DIRS[lang]}/{live.match_page(event) or mid}.html")
    item = {"@context": "https://schema.org", "@type": "SportsEvent", "name": event.get("SUMMARY", "Match"),
            "startDate": event["start"].isoformat(), "endDate": event["end"].isoformat(),
            "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
            "location": {"@type": "VirtualLocation", "url": url}, "description": event.get("DESCRIPTION", ""), "url": url}
    names = teams_of(event.get("SUMMARY", ""))
    if names:
        item["competitor"] = [{"@type": "SportsTeam", "name": name} for name in names]
    text = json.dumps([item], ensure_ascii=False).replace("<", "\\u003c")  # un texte du calendrier ne peut pas fermer la balise <script>
    return f'<script type="application/ld+json">{text}</script>'


def render_page(lang: str, template: str, event: dict, t: dict, home_page: str, names: dict[str, dict[str, str]], links: dict | None = None,
                seo: dict[str, dict[str, str]] | None = None, final: dict | None = None, video: dict | None = None) -> str:
    """La page d'un match, fabriquée dans `template` (template_file) : liens de langue, canonical et hreflang vers les pages du match
    dans les 5 langues, noindex, titre, description, og:* et compteur de visites du match, menu et pied de page du site (« Live »
    marqué), styles, <main> (render_main), données structurées, puis le script de la page Live avec son empreinte.

    `event` : un match de matchs.py (SUMMARY, DESCRIPTION, URL avec ?id=, start, end) ; `t` : LANGS[lang] de matchs.py ; `links` : voir
    render_main ; `final` : la fin notée du match, voir render_main. Lève ValueError sans numéro de match et site_chrome.ChromeError si le modèle ou l'accueil manque de quoi le recevoir."""
    mid = live.match_id(event)
    if mid is None:
        raise ValueError(f"match sans numéro : {event.get('SUMMARY', '?')}")
    name = live.match_page(event) or mid  # « furia-vs-betboom-team-2026-11-06 », le numéro seulement à défaut
    names_en = names.get("en", {})
    game = live.game_slug(event.get("DESCRIPTION", ""), names_en) or blog.TEMPLATE_GAME
    page = template
    for other in an.LANGS:
        page = an.rename_page(page, f"{site_chrome.GAME_DIRS[other]}/{game}.html", f"{live.DIRS[other]}/{name}.html")
    page = an.public_urls(page)
    summary, description = event.get("SUMMARY", "Match"), event.get("DESCRIPTION", "")
    x = TEXTS[lang]
    values = dict(match=summary, comp=description or site_chrome.LIVE_LABEL, day=_day(event, t), hour=live._hour(event))
    page = blog._retitle(page, x["title"].format(**values), x["meta"].format(**values), f"{live.DIRS[lang]}/{name}", seo)
    end = "\r\n" if "\r\n" in page else "\n"
    if 'name="robots"' not in page:
        page = page.replace('<meta name="viewport"', ROBOTS + end + '<meta name="viewport"', 1)
    home, up = blog.read_home(template), _prefix(lang)
    main = render_main(lang, event, t, names, home, mid, links or {}, final, video, page_name=name)
    page = site_chrome.with_chrome(page, lang, home_page, an.HOMES[lang], up, f"{live.DIRS[lang]}/{name}", home=site_chrome.home_link(lang, up),
                                   news=up + an.PAGES[lang], hub=up + site_chrome.HUBS[lang], label=site_chrome.BLOG_LABEL,
                                   current="live", live=up + live.PAGES[lang], css=CSS)
    page = blog._with_jsonld(blog._with_main(page, main), json_ld(lang, event, mid))
    if 'class="video"' in main:  # lecteur au clic : son script, son empreinte et frame-src youtube-nocookie dans la CSP
        page = blog._with_player(page)
    if 'class="wframe"' in main:  # direct de la compétition : la plateforme du lecteur entre dans frame-src
        channel = diffusions.channel_for(event.get("DESCRIPTION", ""))
        page = _with_frames(page, diffusions.FRAMES[channel["platform"]]) if channel else page
    page = site_chrome.with_script(page, live.JS, live.HASH, "de la page Live")
    # Un direct YouTube pas encore commencé s'affiche en vignette, pas en erreur 153.
    return lecteur_differe.poser_vignette(page, up)


def team_pages(root: Path, lang: str) -> dict[str, str]:
    """{nom d'équipe en minuscules: adresse de sa fiche vue d'une page de match} : les fiches equipes/<organisation>.json donnent les noms,
    la page est fr/equipes/<organisation>.html en français et teams/<organisation>.html dans les autres langues (qui n'ont que celle-là)."""
    folder, up = ("fr/equipes" if lang == "fr" else "teams"), _prefix(lang)
    found: dict[str, str] = {}
    for path in sorted((root / "equipes").glob("*.json")):
        slug = path.stem
        if not (root / folder / f"{slug}.html").is_file():
            continue
        data = json.loads(path.read_bytes().decode("utf-8"))
        names = {data.get("organisation", ""), *data.get("noms", []), *(team.get("nom", "") for team in data.get("equipes", []))}
        for name in names:
            if name:
                found.setdefault(name.lower(), f"{up}{folder}/{slug}.html")
    return found


def event_link(description: str, events: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Le grand événement d'un match (« League of Legends · Worlds · 2026 » → « Worlds 2026 ») : la compétition du calendrier (le
    deuxième morceau de la description) contenue dans le nom d'un événement de `events` [(nom, adresse)] ; None sinon."""
    parts = [part.strip().lower() for part in description.split("·")]
    if len(parts) < 2 or not parts[1]:
        return None
    return next(((name, href) for name, href in events if parts[1] in name.lower()), None)


def build(root: Path, events: list[dict], t_by_lang: dict[str, dict], home_pages: dict[str, str], names: dict[str, dict[str, str]],
          event_pages: dict[str, list[tuple[str, str]]], week_pages: dict[str, str],
          seo: dict[str, dict[str, str]] | None = None, finals: dict[str, dict] | None = None,
          videos: dict[str, list[dict]] | None = None) -> dict[str, str]:
    """{chemin de la page: texte} pour tous les matchs de `events` qui ont un numéro, dans les 5 langues. `event_pages` {langue: [(nom,
    page du grand événement)]} et `week_pages` {langue: page des matchs de la semaine} (adresses de la racine) viennent de matchs.py ;
    `finals` : {numéro du match: fin notée} (live_suivi.py) ; `videos` : {jeu: vidéos} (blog-src/topplays.json), d'où vient le bloc
    « temps forts » d'un match terminé joué le jour de la vidéo ou la veille."""
    out: dict[str, str] = {}
    cache: dict[str, str] = {}
    names_en = names.get("en", {})
    for lang, t in t_by_lang.items():
        teams, up = team_pages(root, lang), _prefix(lang)
        for event in events:
            mid = live.match_id(event)
            if mid is None:
                continue
            model = template_file(lang, event, names_en)
            if model not in cache:
                cache[model] = (root / model).read_text(encoding="utf-8")
            game = live.game_slug(event.get("DESCRIPTION", ""), names_en)
            guide = f"{up}{site_chrome.BLOG_DIRS[lang]}/{game}.html" if game and (root / site_chrome.BLOG_DIRS[lang] / f"{game}.html").is_file() else None
            found = event_link(event.get("DESCRIPTION", ""), [(name, up + page) for name, page in event_pages.get(lang, [])])
            links = {"teams": teams, "event": found, "week": up + week_pages[lang] if lang in week_pages else None, "guide": guide}
            clip = video_for((videos or {}).get(game or "", []), event["start"].astimezone(an.paris()).date())
            name = live.match_page(event) or mid
            out[f"{live.DIRS[lang]}/{name}.html"] = render_page(lang, cache[model], event, t, home_pages[lang], names, links, seo,
                                                                (finals or {}).get(mid), clip)
    return out


def prune(root: Path, now: datetime, keep: set[str] = frozenset(), remove: Callable[[Path], None] = Path.unlink) -> list[str]:
    """Supprime les pages de match dont le coup d'envoi date de plus de KEEP (lu dans leur data-start), sauf celles de `keep` (chemins
    relatifs, fabriquées à l'instant) ; rend les chemins supprimés. Une page sans heure lisible reste.

    Supprime aussi une page qui n'a pour nom qu'un numéro et qui n'a pas été refabriquée : c'est une page de l'ancienne façon de
    nommer (le numéro du match, avant que l'adresse ne dise les équipes et la date). Rien ne pointe plus vers elle."""
    gone: list[str] = []
    for folder in DIRS.values():
        for path in sorted((root / folder).glob("*.html")):
            rel = f"{folder}/{path.name}"
            found = DATA_START.search(path.read_bytes().decode("utf-8"))
            if rel in keep or found is None:
                continue
            try:
                start = datetime.fromisoformat(found.group(1))
            except ValueError:
                continue
            if start < now - KEEP or path.stem.isdigit():
                remove(path)
                gone.append(rel)
    return gone
