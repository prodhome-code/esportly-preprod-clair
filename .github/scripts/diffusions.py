"""Où regarder un match : les chaînes officielles de sa compétition, Twitch, YouTube ou Kick.

Le calendrier ne dit pas où un match est diffusé : il donne « Dota 2 · DreamLeague · Season 30 2026 ». Ce tableau, tenu à la
main, relie une compétition à ses chaînes officielles. Chaque chaîne a été vérifiée une par une (Twitch et Kick par leur page,
YouTube par son identifiant de chaîne, le seul que son lecteur de direct accepte). Une compétition absente du tableau n'affiche
aucun lecteur, plutôt qu'un mauvais.

La première chaîne d'une compétition porte le lecteur ; les suivantes sont proposées à côté, en liens. Ajouter une compétition :
une ligne dans CHANNELS, le mot-clé tel qu'il apparaît dans la description du calendrier. L'ordre compte : le premier mot-clé
trouvé gagne, donc du plus précis au plus large.
"""
from __future__ import annotations

import json
import re
import unicodedata

import direct
import urllib.error
import urllib.request

PLAYERS = {
    "twitch": "https://player.twitch.tv/?channel={c}&parent=esportly.eu&autoplay=false&muted=true",
    "youtube": "https://www.youtube-nocookie.com/embed/live_stream?channel={c}",
    "kick": "https://player.kick.com/{c}?autoplay=false&muted=true",
}
PAGES = {
    "twitch": "https://www.twitch.tv/{c}",
    "youtube": "https://www.youtube.com/channel/{c}/live",
    "kick": "https://kick.com/{c}",
}
FRAMES = {
    "twitch": ("https://player.twitch.tv", "https://*.twitch.tv"),
    "youtube": ("https://www.youtube-nocookie.com",),
    "kick": ("https://player.kick.com",),
}
NAMES = {"twitch": "Twitch", "youtube": "YouTube", "kick": "Kick"}

# Les chaînes YouTube, par leur identifiant « UC… » : le lecteur de direct de YouTube ne connaît pas les noms en @.
YT_LOL = ("youtube", "UCSF_aFGIIIoWY30GVV19TKA", "LoL Esports")
YT_VALORANT = ("youtube", "UCA1d3HFGFUmkKr2JIUA5Vlw", "VALORANT")
YT_BLAST = ("youtube", "UCbWA4nLSXvfWnOS2Q4yP48A", "BLAST Premier")
YT_ESLCS = ("youtube", "UCPq2ETz4aAGo2Z-8JisDPIA", "ESL Counter-Strike")
YT_PGL = ("youtube", "UC7VWLs_Ivccq22rM2_xo0Rg", "PGL")
YT_R6 = ("youtube", "UCWKHac5bjhsUtSnMDFCT-7A", "Rainbow 6")
YT_RL = ("youtube", "UCdKuPY64fEpI4cdlBSyvEJw", "Rocket League")
YT_COD = ("youtube", "UCbLIqv9Puhyp9_ZjVtfOy7w", "Call of Duty")
YT_ESLDOTA = ("youtube", "UCaYLBJfw6d8XqmNlL204lNg", "ESL Dota 2")
YT_TI = ("youtube", "UCkz_eteAIMzeQ5wfzbjAI3A", "Dota2Ti")

# (mot-clé cherché dans la description, jeu attendu ou None, chaînes — la première porte le lecteur)
CHANNELS: tuple[tuple[str, str | None, tuple[tuple[str, str, str], ...]], ...] = (
    # League of Legends
    ("worlds", "league of legends", (("twitch", "riotgames", "Riot Games"), YT_LOL)),
    ("msi", "league of legends", (("twitch", "riotgames", "Riot Games"), YT_LOL)),
    ("lec", "league of legends", (("twitch", "lec", "LEC"), YT_LOL)),
    ("lck", "league of legends", (("twitch", "lck", "LCK"), YT_LOL)),
    ("lcs", "league of legends", (("twitch", "lcs", "LCS"), YT_LOL)),
    ("lpl", "league of legends", (("twitch", "lpl", "LPL"), YT_LOL)),
    ("demacia", "league of legends", (("twitch", "lpl", "LPL"), YT_LOL)),
    # Counter-Strike 2
    ("iem", "counter-strike 2", (("twitch", "esl_csgo", "ESL CS"), YT_ESLCS)),
    ("esl pro league", "counter-strike 2", (("twitch", "esl_csgo", "ESL CS"), YT_ESLCS)),
    ("pgl", "counter-strike 2", (("twitch", "pgl", "PGL"), YT_PGL)),
    ("blast", "counter-strike 2", (("twitch", "blastpremier", "BLAST Premier"), YT_BLAST)),
    # Valorant
    ("vct", "valorant", (("twitch", "valorant", "VALORANT"), YT_VALORANT)),
    ("champions", "valorant", (("twitch", "valorant", "VALORANT"), YT_VALORANT)),
    ("game changers", "valorant", (("twitch", "valorant", "VALORANT"), YT_VALORANT)),
    # Dota 2
    ("the international", "dota 2", (("twitch", "dota2ti", "The International"), YT_TI)),
    ("dreamleague", "dota 2", (("twitch", "esl_dota2", "ESL Dota 2"), YT_ESLDOTA)),
    ("esl one", "dota 2", (("twitch", "esl_dota2", "ESL Dota 2"), YT_ESLDOTA)),
    ("pgl", "dota 2", (("twitch", "pgl_dota2", "PGL Dota 2"), YT_PGL)),
    ("blast", "dota 2", (("twitch", "blast", "BLAST"), YT_BLAST)),
    # EPL diffuse sur Kick, sur deux chaînes anglaises en parallèle (deux matchs à la fois).
    ("epl masters", "dota 2", (("kick", "epldota_en1", "EPL Dota 1"), ("kick", "epldota_en2", "EPL Dota 2"))),
    ("epl", "counter-strike 2", (("kick", "eplcs_en", "EPL CS"),)),
    # Rainbow Six Siege
    ("blast r6", "rainbow six siege", (("twitch", "rainbow6", "Rainbow Six"), YT_R6)),
    ("rivals", "rainbow six siege", (("twitch", "rainbow6", "Rainbow Six"), YT_R6)),
    ("league", "rainbow six siege", (("twitch", "rainbow6", "Rainbow Six"), YT_R6)),
    ("major", "rainbow six siege", (("twitch", "rainbow6", "Rainbow Six"), YT_R6)),
    # Overwatch 2 : pas de chaîne YouTube vérifiée, seulement Twitch.
    ("ocs", "overwatch", (("twitch", "owcs", "Overwatch Champions Series"),)),
    ("champions series", "overwatch", (("twitch", "owcs", "Overwatch Champions Series"),)),
    # Les autres jeux
    ("rlcs", "rocket league", (("twitch", "rocketleague", "Rocket League"), YT_RL)),
    ("cdl", "call of duty", (("twitch", "callofduty", "Call of Duty"), YT_COD)),
    ("call of duty league", "call of duty", (("twitch", "callofduty", "Call of Duty"), YT_COD)),
    ("mpl", "mobile legends", (("twitch", "mobilelegends", "Mobile Legends"),)),
    ("kpl", "honor of kings", (("twitch", "honorofkings", "Honor of Kings"),)),
    ("capcom", "street fighter", (("twitch", "capcomfighters", "Capcom Fighters"),)),
    ("esl", "starcraft", (("twitch", "esl_sc2", "ESL StarCraft"),)),
    ("algs", "apex legends", (("twitch", "playapex", "Apex Legends"),)),
)


def plain(text: str) -> str:
    """Le texte sans accents, en minuscules, espaces resserrés : pour chercher un mot-clé sans se soucier de la casse.
    Le point médian des descriptions n'est pas de l'ASCII et disparaît ici : les morceaux se découpent avant."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


_LIVE: dict[str, bool] = {}  # une seule question par chaîne et par exécution


def kick_live(channel: str) -> bool | None:
    """La chaîne Kick est-elle en direct ? None quand la question n'a pas pu être posée (réseau, format inattendu) : l'ordre
    écrit dans le tableau est alors gardé tel quel. Une chaîne n'est demandée qu'une fois par exécution."""
    if channel in _LIVE:
        return _LIVE[channel]
    try:
        request = urllib.request.Request(f"https://kick.com/api/v2/channels/{channel}",
                                         headers={"User-Agent": "Mozilla/5.0 (eSportly)"})
        with urllib.request.urlopen(request, timeout=12) as answer:
            data = json.loads(answer.read().decode("utf-8"))
        live = bool(data.get("livestream"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    _LIVE[channel] = live
    return live


def live_first(streams: list[dict]) -> list[dict]:
    """Les chaînes réordonnées pour que **celle qui diffuse** porte le lecteur : une chaîne YouTube dont le direct a été trouvé
    passe devant, puis une chaîne Kick qui diffuse (EPL en a deux en parallèle : sans cela, la moitié des matchs montrerait un
    lecteur éteint). À défaut, l'ordre du tableau est gardé. Une seule question par chaîne et par exécution."""
    if len(streams) < 2:
        return streams
    live = [stream for stream in streams if stream.get("live")]
    live += [stream for stream in streams
             if stream["platform"] == "kick" and stream not in live and kick_live(stream["channel"])]
    return live + [stream for stream in streams if stream not in live] if live else streams


YT_WATCH = "https://www.youtube-nocookie.com/embed/{c}?rel=0"
YT_PAGE = "https://www.youtube.com/watch?v={c}"


# Ce que les chaînes ont répondu, rempli une seule fois par `resolve()` au moment de fabriquer le site. Rien n'est demandé
# ailleurs : une page se fabrique sans réseau, et les tests restent les mêmes d'un jour à l'autre.
LOGIN: dict[str, str] = {}   # nom Twitch d'origine -> nom que le lecteur accepte
LIVE: dict[str, str] = {}    # chaîne YouTube -> vidéo qu'elle diffuse en ce moment


def resolve() -> dict[str, int]:
    """Demande à chaque chaîne du tableau ce qu'il faut savoir pour que le lecteur marche : le vrai nom d'une chaîne Twitch
    (renommée, son ancienne adresse redirige mais le lecteur, lui, affiche « hors ligne »), et le direct en cours d'une chaîne
    YouTube. Une question par chaîne et par fabrication, jamais pendant le rendu d'une page."""
    LOGIN.clear(), LIVE.clear()
    for _, _, streams in CHANNELS:
        for platform, channel, _ in streams:
            if platform == "twitch" and channel not in LOGIN:
                LOGIN[channel] = direct.twitch_login(channel)
            elif platform == "youtube" and channel not in LIVE:
                found = direct.youtube_live(channel)
                if found:
                    LIVE[channel] = found
    return {"twitch": len(LOGIN), "youtube": len(LIVE)}


def _stream(platform: str, channel: str, label: str) -> dict:
    """Une chaîne, avec son lecteur et sa page, d'après ce que `resolve()` a appris. Une chaîne YouTube qui diffuse donne le
    lecteur de SA vidéo en cours plutôt qu'un lecteur de chaîne, qui ne marche pas toujours."""
    live = LIVE.get(channel) if platform == "youtube" else None
    if platform == "twitch":
        channel = LOGIN.get(channel, channel)
    found = {"platform": platform, "channel": channel, "label": label, "site": NAMES[platform],
             "player": PLAYERS[platform].format(c=channel), "page": PAGES[platform].format(c=channel), "live": bool(live)}
    # Pour YouTube, on garde le lecteur de la CHAÎNE (live_stream + /channel/UC/live), jamais la vidéo trouvée à
    # l'heure de la fabrication : deux jours plus tard, elle ne montre plus le match, mais une autre émission.
    return found


def channels_for(description: str) -> list[dict]:
    """Les chaînes officielles de la compétition d'un match, la porteuse du lecteur en tête ; liste vide quand la compétition
    n'est pas dans le tableau — mieux vaut aucun lecteur qu'un lecteur qui diffuse autre chose.

    Le jeu est un des morceaux de la description (le premier, sauf quand elle commence par une date) : il garde le « PGL » de
    Counter-Strike séparé de celui de Dota 2, et empêche un mot-clé large (« league », « major ») de s'appliquer ailleurs.
    """
    parts = [plain(part) for part in description.split("·") if plain(part)]
    text = plain(description)
    if not parts:
        return []
    for word, wanted, streams in CHANNELS:
        if wanted is not None and not any(part.startswith(plain(wanted)) for part in parts):
            continue
        if word in text:
            return live_first([_stream(*stream) for stream in streams])
    return []


def channel_for(description: str) -> dict | None:
    """La chaîne qui porte le lecteur, ou None. Raccourci de channels_for pour qui n'a besoin que de la première."""
    found = channels_for(description)
    return found[0] if found else None
