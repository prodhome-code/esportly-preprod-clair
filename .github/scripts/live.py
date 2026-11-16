"""Page « Live » : les matchs du jour, en direct selon l'horloge (une page par langue, fabriquée chaque matin par matchs.py).

Le relais eSportly ne publie que des calendriers (début et fin prévus, pas de score ni d'état « en cours ») et le site n'a pas de code
serveur : la page liste tous les matchs du jour (toutes équipes et grands événements confondus) avec leurs horaires en données
(`data-start`, `data-end`, ISO 8601 UTC), et un petit script (JS, autorisé par son empreinte dans la CSP) compare ces horaires à
l'heure du visiteur : « En direct », « Terminé » ou « À venir », recalculé chaque minute, sans réseau. Les textes du script sont lus
dans les attributs data-* de `#live-now`, le script est donc le même dans les 5 langues (une seule empreinte). Sans JavaScript, la
page reste la liste des matchs du jour en heure de Paris.

La page est fabriquée depuis la page « Nouveautés » de la langue (comme les pages de la semaine), habillée du menu du site
(site_chrome.with_chrome, « Live » marqué) ; matchs.py y ajoute ensuite l'heure locale du visiteur (with_local_times).
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta

import actualites as an
import site_chrome

URL = "https://esportly.eu/"
BEFORE, AFTER = timedelta(hours=6), timedelta(hours=30)  # fenêtre des matchs retenus autour de l'heure de fabrication (6 h 15 à Paris)
PAGES = site_chrome.LIVE_PAGES
DIRS = {lang: page.removesuffix(".html") for lang, page in PAGES.items()}  # dossier des pages de match de chaque langue : live-fr/<id>.html
MATCH_ID = re.compile(r"[?&]id=(\d{1,12})(?:&|$)")

# Textes de la page, par langue (mêmes clés partout ; aucun « < », « > », « & » ni « " »). `title` (H1, et <title> à défaut
# de seo/titres.json) tient en 63 caractères, `meta` en 155 (SEO). Les états (`live`, `done`, `soon`) et les comptes (`one`, `many`, `none`, `next`) sont donnés au
# script par les attributs data-* de #live-now ; {n} et {h} y sont remplacés par le nombre de directs et l'heure du prochain match.
# `h_done` : le titre de la section des matchs terminés, tout en bas de la page.
LABELS = {
    "fr": dict(kicker="En direct", title="Matchs e-sport en direct aujourd'hui",
               lead="Tous les matchs du jour des grandes équipes, en heure de Paris : en direct, terminés ou à venir, d'après le calendrier eSportly.",
               meta="Les matchs e-sport en direct aujourd'hui : LoL, Valorant, CS2, Rocket League, Dota 2… Qui joue en ce moment et ce qui vient, en heure de Paris.",
               live="En direct", done="Terminé", soon="À venir", one="{n} match en direct", many="{n} matchs en direct",
               none="Aucun match en direct pour l'instant", next="Prochain match à {h}", empty="Aucun match aujourd'hui.",
               today="Aujourd'hui", tomorrow="Demain", cta="Être prévenu avant chaque match",
               h_done="Matchs terminés",
               side_title="Être prévenu avant le match",
               side_text="Sur ordinateur tu vois le programme. Sur l'app, ton téléphone te prévient avant chaque match de tes équipes, où que tu sois.",
               side_note="Gratuit · iPhone et iPad",
               side_watch="Où regarder",
               side_watch_text="Ouvre un match : la chaîne officielle de sa compétition est sur sa page, quand elle est connue.",
               note="L'état d'un match se déduit des horaires du calendrier (début et fin prévus) ; dès que le résultat est publié, il passe en « Terminé ». Le score est sur la page du match, caché tant que tu ne le demandes pas."),
    "en": dict(kicker="Live", title="Live esports matches today",
               lead="Every match of the top esports teams today, Paris time: live now, finished or coming up, from the eSportly calendar.",
               meta="Live esports matches today: LoL, Valorant, CS2, Rocket League, Dota 2 and more. Who is playing right now and what comes next, Paris time.",
               live="Live", done="Finished", soon="Upcoming", one="{n} match live now", many="{n} matches live now",
               none="No match live right now", next="Next match at {h}", empty="No match today.",
               today="Today", tomorrow="Tomorrow", cta="Get alerted before every match",
               h_done="Finished matches",
               side_title="Get alerted before the match",
               side_text="On a computer you see the schedule. In the app, your phone warns you before every match of your teams, wherever you are.",
               side_note="Free · iPhone and iPad",
               side_watch="Where to watch",
               side_watch_text="Open a match: the official channel of its competition is on its page, when we know it.",
               note="A match's status comes from the calendar's scheduled start and end; once its result is published it moves to Finished. The score is on the match page, hidden until you ask for it."),
    "es": dict(kicker="En directo", title="Partidos de esports en directo hoy",
               lead="Todos los partidos de hoy de los grandes equipos, en hora de París: en directo, terminados o por jugar, según el calendario de eSportly.",
               meta="Partidos de esports en directo hoy: LoL, Valorant, CS2, Rocket League, Dota 2 y más. Quién juega ahora y qué viene después, en hora de París.",
               live="En directo", done="Terminado", soon="Por jugar", one="{n} partido en directo", many="{n} partidos en directo",
               none="Ningún partido en directo ahora mismo", next="Próximo partido a las {h}", empty="Hoy no hay partidos.",
               today="Hoy", tomorrow="Mañana", cta="Recibe un aviso antes de cada partido",
               h_done="Partidos terminados",
               side_title="Recibe un aviso antes del partido",
               side_text="En el ordenador ves el calendario. En la app, tu teléfono te avisa antes de cada partido de tus equipos, estés donde estés.",
               side_note="Gratis · iPhone y iPad",
               side_watch="Dónde verlo",
               side_watch_text="Abre un partido: el canal oficial de su competición está en su página, cuando lo conocemos.",
               note="El estado de un partido se deduce del inicio y el fin previstos en el calendario; cuando se publica el resultado pasa a Terminado. El marcador está en la página del partido, oculto hasta que lo pidas."),
    "de": dict(kicker="Live", title="Esport-Matches heute live",
               lead="Alle Matches der großen Esport-Teams heute, Pariser Zeit: live, beendet oder noch offen, nach dem eSportly-Kalender.",
               meta="Esport-Matches heute live: LoL, Valorant, CS2, Rocket League, Dota 2 und mehr. Wer gerade spielt und was als Nächstes kommt, Pariser Zeit.",
               live="Live", done="Beendet", soon="Demnächst", one="{n} Match live", many="{n} Matches live",
               none="Gerade kein Match live", next="Nächstes Match um {h}", empty="Heute keine Matches.",
               today="Heute", tomorrow="Morgen", cta="Vor jedem Match benachrichtigt werden",
               h_done="Beendete Matches",
               side_title="Vor dem Match benachrichtigt werden",
               side_text="Am Rechner siehst du den Spielplan. In der App meldet sich dein Handy vor jedem Match deiner Teams, wo immer du bist.",
               side_note="Kostenlos · iPhone und iPad",
               side_watch="Wo schauen",
               side_watch_text="Öffne ein Match: der offizielle Kanal seines Wettbewerbs steht auf seiner Seite, sofern bekannt.",
               note="Der Status eines Matches ergibt sich aus Beginn und Ende laut Kalender; sobald das Ergebnis veröffentlicht ist, steht es auf Beendet. Das Ergebnis steht auf der Match-Seite, verborgen, bis du es anzeigst."),
    "pt-BR": dict(kicker="Ao vivo", title="Partidas de esports ao vivo hoje",
                  lead="Todas as partidas de hoje dos grandes times, no horário de Paris: ao vivo, encerradas ou por vir, segundo o calendário do eSportly.",
                  meta="Partidas de esports ao vivo hoje: LoL, Valorant, CS2, Rocket League, Dota 2 e mais. Quem joga agora e o que vem depois, no horário de Paris.",
                  live="Ao vivo", done="Encerrada", soon="Em breve", one="{n} partida ao vivo", many="{n} partidas ao vivo",
                  none="Nenhuma partida ao vivo agora", next="Próxima partida às {h}", empty="Nenhuma partida hoje.",
                  today="Hoje", tomorrow="Amanhã", cta="Seja avisado antes de cada partida",
                  h_done="Partidas encerradas",
                  side_title="Seja avisado antes da partida",
                  side_text="No computador você vê a agenda. No app, seu telefone avisa antes de cada partida dos seus times, onde você estiver.",
                  side_note="Grátis · iPhone e iPad",
                  side_watch="Onde assistir",
                  side_watch_text="Abra uma partida: o canal oficial da competição está na página dela, quando conhecido.",
                  note="O estado de uma partida vem do início e do fim previstos no calendário; quando o resultado é publicado, ela passa a Encerrada. O placar está na página da partida, escondido até você pedir."),
}

# Le script : pour chaque match, début s et fin e (au moins s + 1 h, puis 30 min de marge : la fin du calendrier est une estimation),
# état « soon » avant s, « live » entre s et e, « done » après ou dès que le match porte data-final (fin confirmée par le flux de
# résultats, notée par le robot de live_suivi.py), écrit dans data-state et dans le texte de .etat ; puis #live-now reçoit le nombre de
# directs ou l'heure (de Paris) du prochain match. Quand un état change, les matchs sont rangés : les directs dans #l-live (tout en haut),
# les terminés dans #l-done (tout en bas, le plus récent d'abord), les autres dans leur groupe du jour ; une liste vide est cachée avec
# son titre (data-grp). Sans #l-live la page (celle d'un seul match) ne range rien. Recalculé chaque minute. Les trois états sont lus
# une fois dans S : data-live de #live-now reçoit ensuite le nombre de directs et ne doit plus servir de libellé.
REALTIME_ORIGIN = "wss://lmavqchwevcvvneblqld.supabase.co"
# Le WebSocket Realtime (Supabase) : l'état réel d'un match (statut publié par le relais PandaScore)
# est poussé ici. La clé publique (anon) est remplacée au rendu (realtime_script) ; ce n'est pas un
# secret (même clé que l'app iOS). Sans clé, le script ouvre une connexion qui échoue proprement.
REALTIME_JS = ("(function(){var u='wss://lmavqchwevcvvneblqld.supabase.co/realtime/v1/websocket?apikey=____REALTIME_KEY____&vsn=1.0.0',w;"
               "try{w=new WebSocket(u)}catch(e){return}"
               "w.onopen=function(){w.send(JSON.stringify({topic:'realtime:public',event:'phx_join',payload:{config:{postgres_changes:[{event:'*',schema:'public',table:'matches'}]}},ref:'rt'}))};"
               "setInterval(function(){if(w.readyState===1)w.send(JSON.stringify({topic:'phoenix',event:'heartbeat',payload:{},ref:'hb'}))},3e4);"
               "w.onmessage=function(ev){var m;try{m=JSON.parse(ev.data)}catch(e){return}"
               "if(!m||m.event!=='postgres_changes')return;var p=m.payload&&m.payload.data;if(!p||p.table!=='matches')return;"
               "var r=p.record||p.old_record||{},id=r.id,st=r.status;if(id===null||id===undefined)return;"
               "var lis=d.querySelectorAll('li[data-id]'),li=null,k=''+id;"
               "for(var j=0;j<lis.length;j++){if(lis[j].getAttribute('data-id')===k){li=lis[j];break}}"
               "if(!li)return;"
               "if(p.type==='DELETE'||st==='not_started'){li.removeAttribute('data-final')}else if(st==='finished'){li.setAttribute('data-final','')}"
               "tick()}})();")

JS = ("(function(){var d=document,p=d.getElementById('live-now');if(!p)return;var T=p.dataset,F=null,A=d.getElementById('l-live'),Z=d.getElementById('l-done'),L=null,S={live:T.live,done:T.done,soon:T.soon};"
      "try{F=new Intl.DateTimeFormat(d.documentElement.lang||'en',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Paris'})}catch(e){}"
      "function arrange(){if(!A||!Z)return;var i,li,k,g,h;"
      "if(!L){L=[].slice.call(d.querySelectorAll('.matchs li[data-start]'));for(i=0;i<L.length;i++)L[i].H=L[i].parentNode}"
      "for(i=0;i<L.length;i++){li=L[i];k=li.getAttribute('data-state');"
      "if(k==='live')A.appendChild(li);else if(k==='done')Z.insertBefore(li,Z.firstChild);else li.H.appendChild(li)}"
      "g=d.querySelectorAll('[data-grp]');for(i=0;i<g.length;i++){h=g[i].previousElementSibling;g[i].hidden=!g[i].children.length;if(h)h.hidden=g[i].hidden}}"
      "function tick(){var now=Date.now(),items=d.querySelectorAll('.matchs li[data-start]'),live=0,next=null,ch=0;"
      "for(var i=0;i<items.length;i++){var li=items[i],s=Date.parse(li.getAttribute('data-start')),e=Date.parse(li.getAttribute('data-end'));"
      "if(isNaN(s))continue;if(isNaN(e)||e<s+36e5)e=s+36e5;e+=18e5;"
      "var k=li.hasAttribute('data-final')?'done':now<s?'soon':now<e?'live':'done';"
      "if(li.getAttribute('data-state')!==k){li.setAttribute('data-state',k);ch=1}"
      "var x=li.querySelector('.etat');if(x)x.textContent=S[k]||'';if(k==='live')live++;else if(k==='soon'&&(next===null||s<next))next=s}"
      "if(live)p.textContent=(live>1?T.many:T.one).replace('{n}',live);"
      "else{var t=T.none;if(next!==null&&F)t+=' \\u00b7 '+T.next.replace('{h}',F.format(new Date(next)));p.textContent=t}"
      "p.setAttribute('data-live',live);if(ch)arrange()}"
      + REALTIME_JS
      + "tick();setInterval(tick,6e4)})();")

def realtime_key() -> str:
    """La clé publique Supabase (anon), lue dans realtime_config.json écrit au déploiement."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "realtime_config.json"), encoding="utf-8") as fh:
            return json.load(fh).get("supabase_anon_key", "")
    except (OSError, ValueError):
        return ""


def realtime_script() -> tuple[str, str]:
    """Le script Live complet (horloge + temps réel), avec la clé, et son empreinte CSP."""
    js = JS.replace("____REALTIME_KEY____", realtime_key())
    digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
    return js, digest


CONNECT_SRC = re.compile(r"(?<![\w-])connect-src(?![\w-])[^;]*")


def with_realtime(page: str) -> str:
    """Autorise le WebSocket Realtime dans le connect-src de la CSP (pages Live et match)."""
    meta = site_chrome.CSP_META.search(page)
    if meta is None:
        return page
    policy = meta.group(1)
    connect = CONNECT_SRC.search(policy)
    if connect is None:
        policy = f"{policy}; connect-src 'self' {REALTIME_ORIGIN}"
    elif REALTIME_ORIGIN not in connect.group(0).split():
        kept = connect.group(0).rstrip()
        policy = policy[:connect.start()] + f"{kept} {REALTIME_ORIGIN}" + policy[connect.start() + len(kept):]
    return page[:meta.start(1)] + policy + page[meta.end(1):]

STYLE = (".matchs[hidden]{display:none}.live-now{margin:0 0 20px;font:700 20px var(--display);color:var(--text)}"
         '.live-now[data-live]:not([data-live="0"])::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;'
         "background:#FF4D4D;margin:0 10px 2px 0;animation:live-pulse 1.2s ease-in-out infinite}"
         ".matchs .etat{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--soft)}"
         ".matchs .etat:empty{display:none}"
         '.matchs li[data-state="live"] a{border-color:var(--or);background:color-mix(in srgb,var(--or) 10%,var(--surface))}'
         '.matchs li[data-state="live"] .etat{color:#FF4D4D}'
         '.matchs li[data-state="live"] .etat::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:#FF4D4D;'
         "margin:0 6px 1px 0;animation:live-pulse 1.2s ease-in-out infinite}"
         '.matchs li[data-state="done"] a{opacity:.62}'
         "@keyframes live-pulse{50%{opacity:.25}}"
         "@media (prefers-reduced-motion:reduce){.live-now::before,.matchs .etat::before{animation:none}}"
         ".live-note{margin:24px 0 0;font-size:14px;color:var(--muted)}"
         # Deux colonnes sur ordinateur : les matchs à gauche, l'encart de l'app à droite, qui suit le défilement. Sous 1000 px
         # une seule colonne, et l'encart passe sous les matchs.
         ".livew{display:grid;grid-template-columns:minmax(0,1fr);gap:28px;align-items:start}"
         "@media (min-width:1000px){.livew{grid-template-columns:minmax(0,1fr) 304px;gap:32px}}"
         ".liveside .lsc{position:sticky;top:92px;padding:20px;border-radius:20px;background:var(--surface);"
         "border:1px solid var(--border)}"
         ".liveside h2{margin:0 0 8px;font:700 20px var(--display)}"
         ".liveside p{margin:0 0 14px;font-size:14px;color:var(--muted);line-height:1.5}"
         ".liveside .cta{display:block;text-align:center}"
         ".liveside .lsnote{margin:10px 0 0;font-size:13px}"
         ".liveside .lsmore{margin:16px 0 0;padding-top:14px;border-top:1px solid var(--border)}"
         ".liveside .lsmore b{display:block;color:var(--text);font-size:14px;margin-bottom:4px}"
         # Sur ordinateur l'encart porte déjà le bouton : celui du héros ferait doublon. Sur mobile il reste, l'encart étant plus bas.
         "@media (min-width:1000px){.liveh .cta{display:none}}"
         # Le héros d'une page de match : plus court, sans bouton, pour que le direct soit visible sans faire défiler.
         ".mhero{padding-top:14px;padding-bottom:14px}"
         ".mhero h1{margin:4px 0 6px}"
         ".mhero .lead{margin:0}"
         "@media (prefers-reduced-motion:reduce){.liveside .lsc{position:static}}")


def select(events, now: datetime) -> list[dict]:
    """Les matchs du jour : début entre now − 6 h et now + 30 h, un seul par UID (ou adresse), triés par début.
    Les matchs d'une marque de paris sont ignorés (site_chrome.is_betting)."""
    kept: dict[str, dict] = {}
    for event in events:
        if now - BEFORE <= event["start"] <= now + AFTER:
            if site_chrome.is_betting(event.get("SUMMARY", "")):
                continue
            kept.setdefault(event.get("UID") or event.get("URL") or event["start"].isoformat(), event)
    return sorted(kept.values(), key=lambda e: (e["start"], e.get("SUMMARY", "")))


def game_slug(description: str, names_en: dict[str, str]) -> str | None:
    """Le jeu d'un match (« Counter-Strike 2 · PGL Major · 2026 » → counter-strike-2) d'après les noms anglais des pages de jeux : le nom
    exact, sinon le nom du site qui commence par celui du calendrier (« Overwatch » → Overwatch 2) ; None pour un jeu inconnu du site."""
    game = description.split("·", 1)[0].strip().lower()
    if not game:
        return None
    names = [(slug, name.lower()) for slug, name in names_en.items()]
    return next((slug for slug, name in names if name == game), None) or next((slug for slug, name in names if name.startswith(game + " ")), None)


def _hour(event: dict) -> str:
    return event["start"].astimezone(an.paris()).strftime("%H:%M")


def match_id(event: dict) -> str | None:
    """Le numéro du match (« https://esportly.eu/match.html?id=1713096 » → « 1713096 ») ; None si l'adresse n'en porte pas."""
    found = MATCH_ID.search(event.get("URL", ""))
    return found.group(1) if found else None


SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def match_slug(event: dict) -> str | None:
    """L'adresse d'un match : les deux équipes et la date (« furia-vs-betboom-team-2026-11-06 »). Un numéro seul ne dit rien à
    personne, ni à un visiteur qui partage le lien, ni à un moteur. None quand le titre ne se coupe pas en deux équipes sûres
    (« Journée 3 ») : l'appelant garde alors le numéro."""
    title = event.get("SUMMARY", "")
    stage = re.match(r"^[^:]{1,40}:\s*", title)
    if stage and re.search(r"\s+(?:–|—|-|vs\.?|VS|v\.?)\s+", title[stage.end():]):
        title = title[stage.end():]
    parts = [part.strip() for part in re.split(r"\s+(?:–|—|-|vs\.?|VS|v\.?)\s+", title)]
    if len(parts) != 2 or not all(parts) or any(len(part) > 40 for part in parts):
        return None
    sides = [SLUG_CLEAN.sub("-", unicodedata.normalize("NFKD", part).encode("ascii", "ignore").decode().lower()).strip("-")
             for part in parts]
    if not all(sides):
        return None
    day = event["start"].astimezone(an.paris()).date().isoformat()
    return f"{sides[0]}-vs-{sides[1]}-{day}"


def match_page(event: dict) -> str | None:
    """Le nom de fichier d'un match, sans le dossier : son adresse lisible, ou son numéro à défaut."""
    slug, mid = match_slug(event), match_id(event)
    return (slug or mid) if mid else None


def match_href(lang: str, event: dict) -> str:
    """Où mène un match de la page Live (PAGES[lang], « fr/live.html ») : sa page dans la langue (live_match.py, « ../fr/live/1713096.html »
    vu de la page Live, « live/1713096.html » en anglais), pas la page de renvoi vers l'app (match.html), qui ne sert à rien sur
    ordinateur ; sans numéro, l'adresse du calendrier."""
    name = match_page(event)
    return f"{site_chrome.prefix_for(PAGES[lang])}{DIRS[lang]}/{name}.html" if name else event.get("URL", URL)


def _when(event: dict, t: dict) -> str:
    """« Mercredi 11 novembre · 05:30 ». L'heure seule trompe : un match joué à Hong Kong tombe à 5 h du matin chez nous, et
    sous un titre « Aujourd'hui » il a tout l'air d'une erreur de la veille. Le jour écrit en toutes lettres lève le doute."""
    local = event["start"].astimezone(an.paris())
    label = f'{t["days"][local.weekday()]} {local.day} {t["months"][local.month - 1]}'
    return f"{label[0].upper() + label[1:]} · {_hour(event)}"


def match_item(event: dict, names_en: dict[str, str], href: str | None = None, final: dict | None = None,
               t: dict | None = None) -> str:
    """Un match : horaires en données (pour le script), état vide (rempli par le script), heure de Paris, équipes, compétition.
    `href` : l'adresse du lien (match_href) ; à défaut, celle du calendrier. `final` : la fin notée du match (live_suivi.py), qui lui
    met `data-final` (le script le met alors en « terminé » quelle que soit l'horloge) ; son score n'est jamais écrit ici."""
    game = game_slug(event.get("DESCRIPTION", ""), names_en)
    mid = match_id(event)
    attrs = (f' data-start="{event["start"].isoformat()}" data-end="{event["end"].isoformat()}"' + (f' data-game="{game}"' if game else "")
             + (f' data-id="{mid}"' if mid else "") + (f' data-final="{html.escape(str(final.get("vu", "")), quote=True)}"' if final is not None else ""))
    return (f'<li{attrs}><a href="{html.escape(href or event.get("URL", URL))}"><span class="etat"></span><time datetime="{event["start"].isoformat()}">'
            f'{html.escape(_when(event, t) if t else _hour(event))}</time><b>{html.escape(event.get("SUMMARY", "Match"))}</b><small>{html.escape(event.get("DESCRIPTION", ""))}</small></a></li>')


def day_label(day: date, today: date, lang: str, t: dict) -> str:
    """« Aujourd'hui », « Demain », sinon « Jeudi 5 novembre » (jour et mois de `t`, le dictionnaire LANGS de matchs.py)."""
    if day == today:
        return LABELS[lang]["today"]
    if day == today + timedelta(days=1):
        return LABELS[lang]["tomorrow"]
    label = f'{t["days"][day.weekday()]} {day.day} {t["months"][day.month - 1]}'
    return label[0].upper() + label[1:]


def json_ld(events: list[dict]) -> str:
    items = []
    for event in events:
        names = [n.strip() for n in event.get("SUMMARY", "").split("–")]
        item = {"@context": "https://schema.org", "@type": "SportsEvent", "name": event.get("SUMMARY", "Match"),
                "startDate": event["start"].isoformat(), "endDate": event["end"].isoformat(),
                "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
                "location": {"@type": "VirtualLocation", "url": event.get("URL", URL)}, "description": event.get("DESCRIPTION", ""),
                "url": event.get("URL", URL)}
        if len(names) == 2:
            item["competitor"] = [{"@type": "SportsTeam", "name": n} for n in names]
        items.append(item)
    return '<script type="application/ld+json">' + json.dumps(items, ensure_ascii=False) + "</script>"


def _group(title: str, ident: str) -> str:
    """Une section vide et cachée (le script la remplit) : titre et liste, tout en haut (en direct) ou tout en bas (terminés)."""
    return f'<h2 class="jour" hidden>{title}</h2><ul class="matchs" id="{ident}" data-grp hidden></ul>'


def render_side(lang: str, slug: str, app: str | None = None, app_label: str = "") -> str:
    """L'encart de droite, qui suit le défilement : sur ordinateur les gens n'ont pas l'application, et c'est là — et nulle part
    ailleurs — qu'on leur dit ce qu'elle apporte (être prévenu avant un match). La colonne principale reste au match.

    `app` : l'adresse « ouvrir dans l'application » d'une page de match (avec `app_label`) ; sans elle, l'encart parle de
    l'endroit où regarder un direct, qui n'a pas de sens sur la page d'un match qui a déjà son lecteur."""
    x, esc = LABELS[lang], html.escape
    extra = (f'<p class="lsmore"><a href="{esc(app, quote=True)}">{esc(app_label)}</a></p>' if app
             else f'<p class="lsmore"><b>{esc(x["side_watch"])}</b>{esc(x["side_watch_text"])}</p>')
    return (f'<aside class="liveside"><div class="lsc"><h2>{esc(x["side_title"])}</h2><p>{esc(x["side_text"])}</p>'
            f'<a class="cta" href="{site_chrome.VISIT}?p=/{slug}&amp;go=testflight">{esc(x["cta"])}</a>'
            f'<p class="lsnote">{esc(x["side_note"])}</p>{extra}</div></aside>')


def render_main(lang: str, events: list[dict], now: datetime, t: dict, names: dict[str, dict[str, str]], finals: dict[str, dict] | None = None) -> str:
    """Le <main> de la page Live : héros, état (#live-now), filtre par jeu, les directs (section cachée, le script la remplit), matchs
    groupés par jour, les terminés (idem, tout en bas), note, date de mise à jour, JSON-LD. `finals` : {numéro du match: fin notée}.

    `events` : les matchs déjà choisis (select) ; `t` : LANGS[lang] de matchs.py (jours, mois, fuseau, « Mis à jour le ») ;
    `names` : {langue: {jeu: nom}} (site_chrome.read_game_names), les noms anglais servant à reconnaître le jeu d'un match.
    """
    x, slug = LABELS[lang], PAGES[lang][:-5]
    names_en = names.get("en", {})
    data = "".join(f' data-{key}="{html.escape(x[key], quote=True)}"' for key in ("live", "done", "soon", "one", "many", "none", "next"))
    hero = (f'<section class="hero liveh"><span class="big" aria-hidden="true">eS</span><div class="kicker">{x["kicker"]}</div>'
            f'<h1>{x["title"]}</h1><p class="lead">{x["lead"]}</p>'
            f'<a class="cta" href="{site_chrome.VISIT}?p=/{slug}&amp;go=testflight">{x["cta"]}</a></section>')
    status = f'<p class="live-now" id="live-now"{data}>{t["tz"][0].upper() + t["tz"][1:]}</p>'
    games = [game for game in (game_slug(e.get("DESCRIPTION", ""), names_en) for e in events) if game]
    today, groups = now.astimezone(an.paris()).date(), {}
    for event in events:
        groups.setdefault(event["start"].astimezone(an.paris()).date(), []).append(event)
    finals = finals or {}
    days = "".join(f'<h2 class="jour">{day_label(day, today, lang, t)}</h2><ul class="matchs" data-grp>'
                   f'{"".join(match_item(e, names_en, match_href(lang, e), finals.get(match_id(e) or ""), t) for e in evs)}</ul>' 
                   for day, evs in groups.items())
    stamp = now.astimezone(an.paris())
    # Les directs d'abord, avant même le filtre : c'est ce qu'on vient chercher. Puis le filtre, les jours, et les terminés en bas.
    column = (status + (_group(x["live"], "l-live") + site_chrome.render_filter(lang, games, names.get(lang, {}))
                        + days + _group(x["h_done"], "l-done") if days else f'<p>{x["empty"]}</p>')
              + f'<p class="live-note">{x["note"]}</p>')
    return (hero + f'<div class="livew"><div class="livec">{column}</div>{render_side(lang, slug)}</div>'
            + f'<p class="maj">{t["updated"]} {stamp.day} {t["months"][stamp.month - 1]} {stamp.year} · {t["tz"]}</p>' + json_ld(events))


def render_page(lang: str, template: str, events: list[dict], now: datetime, t: dict, home_page: str,
                names: dict[str, dict[str, str]], seo: dict[str, dict[str, str]] | None = None, finals: dict[str, dict] | None = None) -> str:
    """La page Live d'une langue depuis sa page « Nouveautés » : liens de langue et adresses déclarées vers les 5 pages Live, titre,
    description et og:* (`seo` : site_chrome.seo_texts, sinon LABELS), compteur de visites, <main> (render_main), styles, menu et pied de page du site (« Live » marqué),
    puis le script avec son empreinte. Une page refabriquée depuis son propre texte ne change pas. Lève site_chrome.ChromeError
    si le modèle ou l'accueil n'a pas ce qu'il faut."""
    page = template
    for other, name in an.TEMPLATES.items():
        page = an.rename_page(page, name, PAGES[other])
    page = an.public_urls(page)
    page = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>\r?\n?', "", page)
    x = LABELS[lang]
    title, meta = (html.escape(s) for s in site_chrome.seo(seo or {}, PAGES[lang], x["title"], x["meta"]))
    page = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title}</title>", page, flags=re.S)
    page = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + meta, page)
    page = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + title, page)
    page = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + meta, page)
    page = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + f"{URL}partage/semaine-{lang}.jpg", page)
    slug, prefix = PAGES[lang][:-5], site_chrome.prefix_for(PAGES[lang])
    page = re.sub(r"(visite\?p=/)[a-z/-]+", lambda m: m.group(1) + slug, page)
    main = render_main(lang, events, now, t, names, finals)
    page = re.sub(r'<main class="wrap">.*?</main>', lambda _: f'<main class="wrap">{main}</main>', page, flags=re.S)
    if ".matchs{" not in page:
        page = page.replace("</style>", an.STYLE + "</style>", 1)
    if ".live-now{" not in page:
        page = page.replace("</style>", STYLE + "</style>", 1)
    elif ".livew{" not in page:  # page d'avant les deux colonnes : on ajoute ce qui manque, sans toucher au reste
        page = page.replace("</style>", STYLE[STYLE.index(".livew{"):] + "</style>", 1)
    page = site_chrome.with_chrome(page, lang, home_page, an.HOMES[lang], prefix, slug, home=site_chrome.home_link(lang, prefix),
                                   news=prefix + an.PAGES[lang], hub=prefix + site_chrome.HUBS[lang], label=site_chrome.BLOG_LABEL,
                                   current="live", live=prefix + PAGES[lang])
    page = with_realtime(page)
    live_js, live_hash = realtime_script()
    return site_chrome.with_script(page, live_js, live_hash, "de la page Live")
