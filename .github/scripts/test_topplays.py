"""Tests de topplays.py (top plays du Blog) : lecture du flux, sélection, rafraîchissement, ligne de commande.
Aucun accès réseau : faux flux YouTube, fausse page oEmbed, faux urlopen.

    PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONTZPATH=C:\\Users\\horny\\anaconda3\\Lib\\site-packages\\pytz\\zoneinfo \\
        py -3.13 -m unittest discover -s .github/scripts -p "test_topplays.py" -v
"""
import contextlib
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

import actualites as an
import blog
import topplays

UTC = timezone.utc
TODAY = date(2026, 10, 27)
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)  # 11 h à Paris le 27 octobre (heure d'hiver depuis le 25)
BEFORE_MIDNIGHT = datetime(2026, 10, 26, 23, 30, tzinfo=UTC)  # le 27 octobre à 0 h 30 à Paris
PUBLISHED = "2026-10-26T12:00:00+00:00"


def code(n: int) -> str:
    """Un identifiant de vidéo valide (11 caractères), numéroté."""
    return f"video{n:06d}"


def channel_id(letter: str) -> str:
    """Un identifiant de chaîne valide : UC suivi de 22 caractères."""
    return "UC" + letter * 22


def entry_xml(video_id: str, title: str, published: str, views=None, author: str = "LoL Esports") -> str:
    """Une entrée du flux Atom de YouTube ; sans `views`, l'élément media:statistics manque."""
    stats = "" if views is None else f'<media:statistics views="{views}"/>'
    return (f'<entry><id>yt:video:{video_id}</id><yt:videoId>{video_id}</yt:videoId><yt:channelId>UCxxxxxxxxxxxxxxxxxxxxxx</yt:channelId>'
            f'<title>{escape(title)}</title><link rel="alternate" href="https://www.youtube.com/watch?v={video_id}"/>'
            f'<author><name>{escape(author)}</name><uri>https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx</uri></author>'
            f'<published>{published}</published><updated>{published}</updated>'
            f'<media:group><media:title>{escape(title)}</media:title><media:community>'
            f'<media:starRating count="12" average="5.00" min="1" max="5"/>{stats}</media:community></media:group></entry>')


def feed_xml(*entries: str) -> str:
    """Un flux Atom de YouTube : l'auteur du flux (autre que celui des entrées) précède les entrées."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">'
            '<link rel="self" href="http://www.youtube.com/feeds/videos.xml?channel_id=UCxxxxxxxxxxxxxxxxxxxxxx"/><id>yt:channel:x</id>'
            '<title>Chaîne du flux</title><author><name>Auteur du flux</name><uri>https://www.youtube.com/channel/x</uri></author>'
            f'<published>2012-01-01T00:00:00+00:00</published>{"".join(entries)}</feed>')


class Feeds:
    """Faux flux YouTube : sert {chaîne: texte} et note chaque adresse demandée ; une valeur qui est une exception est levée,
    une chaîne inconnue est en panne."""

    def __init__(self, feeds: dict):
        self.feeds, self.calls = feeds, []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        answer = self.feeds.get(url.removeprefix(topplays.FEED), OSError("flux indisponible"))
        if isinstance(answer, Exception):
            raise answer
        return answer


class Statuses:
    """Fausse page oEmbed : rend le code prévu pour la vidéo (`default`, 200 si rien n'est dit) et note chaque adresse demandée."""

    def __init__(self, codes: dict | None = None, default: int = 200):
        self.codes, self.default, self.calls = codes or {}, default, []

    def __call__(self, url: str) -> int:
        self.calls.append(url)
        return self.codes.get(url.rsplit("%3D", 1)[1], self.default)

    def asked(self) -> list[str]:
        """Identifiants des vidéos pour lesquelles l'intégration a été vérifiée, dans l'ordre."""
        return [url.rsplit("%3D", 1)[1] for url in self.calls]


def quiet(function, *args, **kwargs):
    """Appelle `function` en gardant sa sortie (les échecs de lecture sont signalés sur la sortie, comme actualites.py)."""
    with contextlib.redirect_stdout(io.StringIO()) as printed:
        result = function(*args, **kwargs)
    return result, printed.getvalue()


# --- Flux ---------------------------------------------------------------------------------------------------------

class Flux(unittest.TestCase):
    def test_lecture_du_flux(self):
        text = feed_xml(
            entry_xml(code(1), "Finale : T1 vs G2 & co", "2026-10-26T15:00:12+00:00", 120345),
            entry_xml(code(2), "Éclats de la semaine — « 日本語 »", "2026-10-25T09:30:00+00:00", 0, author="Chaîne Ñandú"),
            entry_xml(code(3), "Sans statistiques", "2026-10-20T08:00:00+01:00"),
            entry_xml(code(4), "Tard le soir", "2026-10-25T23:30:00+00:00", 7))
        calls = []

        def fetch(url):
            calls.append(url)
            return text

        found = topplays.read_feed(channel_id("a"), fetch)
        self.assertEqual(calls, ["https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id("a")])
        self.assertEqual(topplays.FEED, "https://www.youtube.com/feeds/videos.xml?channel_id=")
        self.assertEqual(found, [
            {"id": code(1), "title": "Finale : T1 vs G2 & co", "channel": "LoL Esports", "published": date(2026, 10, 26), "views": 120345},
            {"id": code(2), "title": "Éclats de la semaine — « 日本語 »", "channel": "Chaîne Ñandú", "published": date(2026, 10, 25), "views": 0},
            {"id": code(3), "title": "Sans statistiques", "channel": "LoL Esports", "published": date(2026, 10, 20), "views": 0},  # views manquant : 0
            {"id": code(4), "title": "Tard le soir", "channel": "LoL Esports", "published": date(2026, 10, 26), "views": 7},  # jour de Paris
        ])

    def test_flux_illisible_ou_a_moitie_lu(self):
        calls = []

        def broken(url):
            calls.append(url)
            raise OSError("serveur indisponible")

        found, printed = quiet(topplays.read_feed, channel_id("a"), broken)
        self.assertIsNone(found)
        self.assertEqual(len(calls), 2)  # un second essai, puis abandon
        self.assertIn("serveur indisponible", printed)
        self.assertIn(channel_id("a"), printed)
        for garbage in ("", "pas du XML", "<feed><entry>", "<feed xmlns='http://www.w3.org/2005/Atom'><entry></feed>"):
            self.assertIsNone(quiet(topplays.read_feed, channel_id("a"), lambda url, garbage=garbage: garbage)[0], garbage)
        answers = iter([OSError("une fois"), feed_xml(entry_xml(code(1), "Titre", PUBLISHED, 5))])

        def second_time(url):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        found, _ = quiet(topplays.read_feed, channel_id("a"), second_time)
        self.assertEqual([entry["id"] for entry in found], [code(1)])
        found, _ = quiet(topplays.read_feed, channel_id("a"), lambda url: feed_xml())
        self.assertEqual(found, [])  # un flux sans entrée est lu : une chaîne sans vidéo n'est pas une panne

    def test_document_qui_n_est_pas_un_flux_atom(self):
        # bien formés, mais pas un flux Atom : une page d'erreur ou un autre document n'est pas « une chaîne sans vidéo »
        for other in ("<html><head><title>Erreur</title></head><body><p>Désolé</p></body></html>", "<error><code>403</code></error>",
                      '<feed xmlns="http://example.com/x"><entry/></feed>', "<feed><entry/></feed>",
                      '<entry xmlns="http://www.w3.org/2005/Atom"><published>2026-10-26T12:00:00+00:00</published></entry>',
                      '<rss version="2.0"><channel><title>x</title></channel></rss>'):
            with self.subTest(other[:40]):
                calls = []

                def fetch(url, other=other):
                    calls.append(url)
                    return other

                found, printed = quiet(topplays.read_feed, channel_id("a"), fetch)
                self.assertIsNone(found)
                self.assertEqual(len(calls), 2)  # une panne comme les autres : un second essai, puis abandon
                self.assertIn("pas un flux Atom", printed)
                self.assertIn(channel_id("a"), printed)

    def test_entrees_inutilisables_ignorees(self):
        text = feed_xml(
            entry_xml(code(1), "Bonne", PUBLISHED, 10),
            entry_xml("", "Sans identifiant", PUBLISHED, 10),
            entry_xml(code(2), "Date absente", "", 10),
            entry_xml(code(3), "Date illisible", "hier", 10),
            entry_xml(code(4), "Vues illisibles", PUBLISHED, "beaucoup"))
        found, _ = quiet(topplays.read_feed, channel_id("a"), lambda url: text)
        self.assertEqual([(entry["id"], entry["views"]) for entry in found], [(code(1), 10), (code(4), 0)])

    def test_dtd_et_entites_refusees(self):
        bomb = ('<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
                + feed_xml(entry_xml(code(1), "&b;", PUBLISHED, 10)).split("?>", 1)[1])
        found, printed = quiet(topplays.read_feed, channel_id("a"), lambda url: bomb)
        self.assertIsNone(found)
        self.assertIn(channel_id("a"), printed)


# --- Sélection ----------------------------------------------------------------------------------------------------

def video(n: int, days: int = 1, views: int = 0, title: str | None = None, channel: str = "LoL Esports", id: str | None = None,
          cid: str | None = None) -> dict:
    """Une vidéo lue du flux, publiée il y a `days` jours ; `cid` est l'identifiant de sa chaîne (ajouté par refresh), absent sinon."""
    one = {"id": id or code(n), "title": title or f"Match {n}", "channel": channel, "published": TODAY - timedelta(days=days), "views": views}
    if cid is not None:
        one["channel_id"] = cid
    return one


def select(videos: list[dict], is_embeddable=lambda video_id: True, now: datetime = NOW, includes: dict | None = None) -> list[dict]:
    return topplays.select_videos(videos, now, is_embeddable, includes)


def ids(videos: list[dict]) -> list[str]:
    return [one["id"] for one in videos]


HIGHLIGHTS = r"\bhighlights?\b"  # une expression `include`, comme celle de channels.json


class Selection(unittest.TestCase):
    def test_fenetre_de_7_puis_21_jours(self):
        recent = [video(1, 0, 10), video(2, 3, 20), video(3, 7, 30)]
        older = [video(4, 8, 9000), video(5, 10, 8000)]  # plus vues, mais hors de la fenêtre de 7 jours : 3 vidéos récentes suffisent
        self.assertEqual(ids(select(recent + older)), [code(3), code(2), code(1)])
        recent = [video(1, 2, 500), video(2, 6, 400)]  # 2 récentes seulement : fenêtre de 21 jours
        older = [video(n, 10, views) for n, views in ((3, 100), (4, 300), (5, 200), (6, 50), (7, 150))]
        self.assertEqual(ids(select(recent + older)), [code(1), code(2), code(4)])
        self.assertEqual(ids(select([video(1, 21, 5), video(2, 22, 9000), video(3, 40, 9000)])), [code(1)])  # 21 jours : oui ; 22 : jamais
        self.assertEqual(select([video(1, 22, 9000)]), [])
        self.assertEqual(select([]), [])

    def test_les_directs_ne_comptent_pas_dans_la_fenetre(self):
        # 3 vidéos des 7 derniers jours, dont un direct : 2 seulement qualifient, la fenêtre passe à 21 jours
        videos = [video(1, 1, 10), video(2, 2, 20), video(3, 3, 30, title="LIVE: Day 3"), video(4, 12, 5)]
        self.assertEqual(ids(select(videos)), [code(2), code(1), code(4)])

    def test_jour_de_paris_et_dates_futures(self):
        today = {"id": code(1), "title": "Aujourd'hui", "channel": "C", "published": date(2026, 10, 27), "views": 1}
        self.assertEqual(ids(select([today], now=BEFORE_MIDNIGHT)), [code(1)])  # le 27 à Paris, bien que le 26 en UTC
        tomorrow = dict(today, id=code(2), published=date(2026, 10, 28))
        self.assertEqual(select([tomorrow]), [])  # une date postérieure à aujourd'hui (horloge fausse, première en direct) n'est pas retenue
        seven = dict(today, id=code(3), published=date(2026, 10, 20))
        extra = [dict(today, id=code(n), published=date(2026, 10, 26), views=n) for n in (4, 5)]
        eight = dict(today, id=code(6), published=date(2026, 10, 19), views=99)
        self.assertEqual(ids(select([seven, eight, *extra], now=BEFORE_MIDNIGHT)), [code(5), code(4), code(3)])  # 7 jours : oui ; 8 : non

    def test_exclusion_par_mots_entiers(self):
        discarded = ["LIVE: Day 3", "Full VOD", "Replay of game 2", "Worlds livestream", "FULL MATCH: T1 vs G2", "lIvE", "Day 2 live",
                     "Full\tVOD\n(day 1)", "Full  Match", "Résumé — REPLAY",
                     "G2 vs. TLV | MATCH HIGHLIGHTS #shorts", "Clutch #SHORTS", "Shorts", "VERTICAL | TLAW vs. AL | Day 4", "Vertical", "Day 4 (vertical)"]
        kept = ["Alive in the final", "Delivery", "Olive oil", "Replayed", "Livestreams", "Fullmatch", "Full Matches", "Full VODs",
                "Shortstop", "Verticality", "Verticals", "Short film"]  # « shorts » et « vertical » comptent comme mots entiers seulement
        videos = [video(n, 1, 100, title=title) for n, title in enumerate(discarded + kept, start=1)]
        selected = select(videos, lambda video_id: True)
        self.assertEqual(ids(selected), [code(n) for n in range(len(discarded) + 1, len(discarded) + 4)])  # 3 au plus : les 3 premières gardées
        for title in discarded:
            self.assertEqual(select([video(1, 1, 1, title=title)]), [], title)
        for title in kept:
            self.assertEqual([one["title"] for one in select([video(1, 1, 1, title=title)])], [title])
        self.assertEqual(select([video(1, 1, 1, title="x" * 200 + " LIVE")]), [])  # le mot compte même après la coupe à 100 caractères

    def test_classement_et_limite(self):
        top, middle, tie_old, tie_new_z, tie_new_a, last = (
            video(1, 4, 900), video(2, 3, 500), video(3, 3, 500), video(4, 1, 500, id="zzzzzzzzzzz"), video(5, 1, 500, id="aaaaaaaaaaa"), video(6, 1, 10))
        self.assertEqual(ids(select([last, tie_old, tie_new_z, top, tie_new_a, middle])),
                         [code(1), "aaaaaaaaaaa", "zzzzzzzzzzz"])  # vues décroissantes ; à égalité la plus récente, puis l'identifiant
        self.assertEqual(ids(select([video(1, 2, 5), video(2, 1, 5), video(3, 2, 5, id="000000000aa"), video(4, 2, 5, id="000000000ab")])),
                         [code(2), "000000000aa", "000000000ab"])
        self.assertEqual(len(select([video(n, 1, n) for n in range(1, 30)])), 3)
        self.assertEqual(ids(select([video(1, 1, 5), video(1, 2, 9)])), [code(1)])  # la même vidéo dans deux chaînes : une seule fois
        selected = select([video(1, 2, 5, title="Finale", channel="LoL Esports")])
        self.assertEqual(selected, [{"id": code(1), "title": "Finale", "channel": "LoL Esports", "published": "2026-10-25"}])

    def test_integration_interdite(self):
        videos = [video(n, 1, 100 - n) for n in range(1, 8)]  # classement : 1, 2, 3, 4, 5, 6, 7
        asked = []

        def embeddable(video_id):
            asked.append(video_id)
            return video_id not in (code(1), code(3))

        self.assertEqual(ids(select(videos, embeddable)), [code(2), code(4), code(5)])
        self.assertEqual(asked, [code(1), code(2), code(3), code(4), code(5)])  # dans l'ordre du classement, sans demander la suite
        self.assertEqual(select(videos, lambda video_id: False), [])
        calls = []

        def status(url):
            calls.append(url)
            return {code(1): 200, code(2): 401, code(3): 404, code(4): 400, code(5): 403, code(6): 410, code(7): 204}[url.rsplit("%3D", 1)[1]]

        self.assertEqual([topplays.oembed_ok(code(n), status) for n in range(1, 8)], [True] + [False] * 6)  # 200 : oui ; un refus : non
        self.assertEqual(calls[0], "https://www.youtube.com/oembed?format=json&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D" + code(1))

    def test_refus_d_integration_vu_par_oembed(self):
        videos = [video(n, 1, 100 - n) for n in range(1, 8)]
        status = Statuses({code(1): 404, code(2): 401, code(3): 400, code(4): 403})  # refus définitifs : écartées, les suivantes sont prises
        selected = select(videos, lambda video_id: topplays.oembed_ok(video_id, status))
        self.assertEqual(ids(selected), [code(5), code(6), code(7)])
        self.assertEqual(status.asked(), [code(n) for n in range(1, 8)])

    def test_panne_d_oembed(self):
        for outage in (0, 429, 500, 502, 503, 599):  # aucune réponse après le second essai, trop de requêtes, erreurs du serveur
            with self.subTest(outage):
                with self.assertRaises(topplays.OutageError) as raised:
                    topplays.oembed_ok(code(1), lambda url, outage=outage: outage)
                self.assertIn(code(1), str(raised.exception))
                self.assertIn(str(outage) if outage else "pas de réponse", str(raised.exception))
                videos = [video(n, 1, 100 - n) for n in range(1, 8)]
                status = Statuses({code(2): outage})
                with self.assertRaises(topplays.OutageError):  # la sélection reste pure : la panne passe, ce n'est pas un refus
                    select(videos, lambda video_id: topplays.oembed_ok(video_id, status))
                self.assertEqual(status.asked(), [code(1), code(2)])  # on ne demande rien après la panne

    def test_include_garde_les_temps_forts(self):
        a, b = channel_id("a"), channel_id("b")
        includes = {a: HIGHLIGHTS}
        videos = [video(1, 1, 900, title="X vs Y | HIGHLIGHTS", cid=a), video(2, 1, 50000, title="X vs Y | Day 4", cid=a),
                  video(3, 2, 40000, title="VERTICAL | X vs Y | Day 4", cid=a), video(4, 2, 100, title="Swiss Stage Day 4 Highlights | Worlds 2026", cid=a),
                  video(5, 3, 30000, title="Un clutch #shorts", cid=a)]
        self.assertEqual(ids(select(videos, includes=includes)), [code(1), code(4)])  # les temps forts seuls, même moins vus que les rediffusions
        self.assertEqual(ids(select(videos)), [code(2), code(1), code(4)])  # sans expression : tout reste, sauf « VERTICAL » et « #shorts » (écartés partout)
        # la casse ne compte pas, et c'est le titre entier qui est cherché, même au-delà de la coupe à 100 caractères
        for title in ("highlights", "MATCH HIGHLIGHTS", "Top Highlight: T1", "Day 4 (Highlights)", "x" * 150 + " Highlights"):
            self.assertEqual(ids(select([video(1, 1, 5, title=title, cid=a)], includes=includes)), [code(1)], title)
        for title in ("Highlighted", "Nohighlights", "Day 4", "High lights"):
            self.assertEqual(select([video(1, 1, 5, title=title, cid=a)], includes=includes), [], title)
        # les autres règles restent : un temps fort « replay », en « live », « #shorts » ou « vertical » est écarté, une vidéo hors fenêtre aussi
        videos = [video(1, 1, 5, title="Highlights (replay)", cid=a), video(2, 1, 6, title="LIVE: Highlights", cid=a),
                  video(3, 22, 7, title="Highlights", cid=a), video(4, 1, 8, title="Highlights", cid=a, id="abc"),
                  video(5, 1, 9, title="X vs Y | MATCH HIGHLIGHTS #shorts", cid=a), video(6, 1, 10, title="VERTICAL | X vs Y | Highlights", cid=a)]
        self.assertEqual(select(videos, includes=includes), [])

    def test_include_par_chaine(self):
        a, b, c = channel_id("a"), channel_id("b"), channel_id("c")
        videos = [video(1, 1, 100, title="Day 1 Highlights", cid=a), video(2, 1, 900, title="Day 1 | The final", cid=a),
                  video(3, 1, 800, title="Day 2", cid=a), video(4, 1, 300, title="Interview", cid=b), video(5, 1, 200, title="Highlights", cid=b),
                  video(6, 1, 700, title="Sans chaîne connue"), video(7, 1, 50, title="Autre", cid=c)]
        # a a une expression, b et c n'en ont pas : leurs vidéos gardent le comportement d'avant ; une vidéo sans `channel_id` n'est pas filtrée
        self.assertEqual(ids(select(videos, includes={a: HIGHLIGHTS})), [code(6), code(4), code(5)])
        self.assertEqual(ids(select(videos, includes={a: HIGHLIGHTS, c: "autre"})), [code(6), code(4), code(5)])
        self.assertEqual(ids(select(videos, includes={a: HIGHLIGHTS, b: HIGHLIGHTS, c: HIGHLIGHTS})), [code(6), code(5), code(1)])
        for nothing in (None, {}, {"UCinconnue": HIGHLIGHTS}):  # includes absent, vide ou sans rapport : rien n'est filtré
            self.assertEqual(ids(select(videos, includes=nothing)), [code(2), code(3), code(6)])
        self.assertEqual(ids(topplays.select_videos(videos, NOW, lambda video_id: True)), [code(2), code(3), code(6)])  # `includes` est facultatif
        # la même vidéo dans deux chaînes : écartée dans celle qui filtre, elle reste via celle qui ne filtre pas
        videos = [video(1, 1, 5, title="Day 4", cid=a), video(1, 1, 5, title="Day 4", cid=b)]
        self.assertEqual(ids(select(videos, includes={a: HIGHLIGHTS})), [code(1)])
        self.assertEqual(select(videos, includes={a: HIGHLIGHTS, b: HIGHLIGHTS}), [])

    def test_include_mlbb_exige_un_contexte_de_match(self):
        # l'expression réelle de la chaîne MLBB eSports (channels.json) : un « Highlights » hors compétition est écarté
        root = Path(__file__).resolve().parents[2]
        channels = json.loads((root / "blog-src" / "channels.json").read_text(encoding="utf-8"))
        mlbb = channels["mobile-legends"][0]
        a = channel_id("a")
        includes = {a: mlbb["include"]}
        for title in ("10th Anniversary Offline Birthday Party Highlights | Mobile Legends: Bang Bang", "Nathzzz is back in PH", "Cosplay Highlights | MPL PH"):
            self.assertEqual(select([video(1, 1, 5, title=title, cid=a)], includes=includes), [], title)
        for title in ("MPL ID S17 Week 3 Highlights", "ONIC vs. RRQ | Highlights", "Highlights | MSC 2026 Grand Finals", "Top plays of the week"):
            self.assertEqual(ids(select([video(1, 1, 5, title=title, cid=a)], includes=includes)), [code(1)], title)

    def test_include_avant_la_fenetre_de_7_jours(self):
        a = channel_id("a")
        includes = {a: HIGHLIGHTS}
        unqualified = [video(n, n, 9000 + n, title=f"Day {n}", cid=a) for n in (1, 2, 3)]  # 3 vidéos des 7 derniers jours, aucune qualifiée
        # moins de 3 qualifiées sur 7 jours (même si 3 vidéos non qualifiées y sont) : la fenêtre passe à 21 jours
        qualified = [video(4, 1, 10, title="Day 1 Highlights", cid=a), video(5, 2, 20, title="Day 2 Highlights", cid=a),
                     video(6, 12, 50, title="Day 12 Highlights", cid=a), video(7, 15, 5, title="Day 15 Highlights", cid=a),
                     video(8, 22, 99999, title="Day 22 Highlights", cid=a)]
        self.assertEqual(ids(select(unqualified + qualified, includes=includes)), [code(6), code(5), code(4)])
        # 3 qualifiées sur 7 jours : la fenêtre reste à 7 jours, les temps forts plus anciens (plus vus) ne comptent pas
        recent = [video(n, n - 3, 10 * n, title=f"Day {n - 3} Highlights", cid=a) for n in (4, 5, 6)]
        older = [video(n, 10, 99999, title="Older Highlights", cid=a) for n in (7, 8)]
        self.assertEqual(ids(select(unqualified + recent + older, includes=includes)), [code(6), code(5), code(4)])
        # la fenêtre de 7 jours elle-même : 7 jours oui, 8 jours non (avec 3 qualifiées à 7 jours au plus)
        edge = [video(1, 7, 1, title="Highlights", cid=a), video(2, 7, 2, title="Highlights", cid=a), video(3, 6, 3, title="Highlights", cid=a),
                video(4, 8, 99999, title="Highlights", cid=a)]
        self.assertEqual(ids(select(edge, includes=includes)), [code(3), code(2), code(1)])

    def test_include_moins_de_trois_ou_aucune_video(self):
        a = channel_id("a")
        includes = {a: HIGHLIGHTS}
        unqualified = [video(n, n, 9000, title=f"Day {n}", cid=a) for n in range(1, 8)]
        # moins de 3 qualifiées sur 21 jours : on en montre moins, jamais complétées par des non qualifiées
        qualified = [video(10, 2, 5, title="Highlights A", cid=a), video(11, 20, 7, title="Highlights B", cid=a),
                     video(12, 22, 9, title="Highlights C", cid=a)]  # 22 jours : hors fenêtre
        self.assertEqual(ids(select(unqualified + qualified, includes=includes)), [code(11), code(10)])
        self.assertEqual(ids(select(unqualified + qualified[:1], includes=includes)), [code(10)])
        # aucune : liste vide, et l'intégration n'est même pas demandée pour les vidéos non qualifiées
        asked = []

        def embeddable(video_id):
            asked.append(video_id)
            return True

        self.assertEqual(select(unqualified + qualified[2:], embeddable, includes=includes), [])
        self.assertEqual(select([], embeddable, includes=includes), [])
        self.assertEqual(asked, [])
        select(unqualified + qualified[:2], embeddable, includes=includes)
        self.assertEqual(asked, [code(11), code(10)])  # seules les qualifiées sont vérifiées, dans l'ordre du classement
        # un refus d'intégration écarte une qualifiée : on n'en montre que moins, sans rattraper une non qualifiée
        self.assertEqual(ids(select(unqualified + qualified[:2], lambda video_id: video_id != code(11), includes=includes)), [code(10)])

    def test_titre_nettoye(self):
        self.assertEqual(topplays.clean_title("  Finale\x00 :\x07 T1\t vs\n G2\x1f  \x7f "), "Finale : T1 vs G2")
        self.assertEqual(topplays.clean_title("a\u2028b\u00a0c\x85d"), "a b c d")  # séparateurs de lignes et espaces insécables : des espaces
        self.assertEqual(topplays.clean_title("<b>é</b> & « 日本語 » 🎮"), "<b>é</b> & « 日本語 » 🎮")  # le reste est gardé tel quel (échappé à l'affichage)
        self.assertEqual(topplays.clean_title("x" * 100), "x" * 100)
        self.assertEqual(topplays.clean_title("x" * 101), "x" * 99 + "…")
        self.assertEqual(len(topplays.clean_title("é" * 500)), 100)
        self.assertEqual(topplays.clean_title("a" * 98 + " " + "b" * 10), "a" * 98 + "…")  # espace avant la coupe : retirée
        self.assertEqual(topplays.clean_title("c" * 70, 60), "c" * 59 + "…")
        self.assertEqual(topplays.clean_title(" \x00 "), "")
        hostile = video(1, 1, 5, title="\x00  Finale\n\n" + "x" * 150, channel="\x07" + "C" * 80)
        selected = select([hostile, video(2, 1, 4, id="abc"), video(3, 1, 3, id="abcdefghij\n"), video(4, 1, 2, id="abcdefghijkl"),
                           video(5, 1, 1, id="abcdef/hijk")])  # identifiants de vidéo invalides : ignorés
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], ("Finale " + "x" * 150)[:99] + "…")
        self.assertEqual(selected[0]["channel"], "C" * 59 + "…")
        self.assertEqual(select([video(6, 1, 1, title="\x00\x07"), video(7, 1, 1, channel=" \n ")]), [])  # titre ou chaîne vide : ignorée

    def test_sortie_acceptee_par_blog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = site(Path(tmp), ("valorant",))
            selected = select([video(n, 1, n, title=f"Titre {n} \x00" + "x" * 150, channel="Chaîne " * 20) for n in range(1, 6)])
            write(root, "blog-src/topplays.json", json.dumps({"valorant": {"fetched": "2026-10-27", "videos": selected}}))
            self.assertEqual(blog.load_topplays(root)["valorant"]["videos"], selected)


# --- Réseau (faux urlopen) ----------------------------------------------------------------------------------------

class Answer:
    """Réponse de urlopen : gestionnaire de contexte avec `status` et `read`."""

    def __init__(self, status: int = 200, body: bytes = b""):
        self.status, self.body, self.limit = status, body, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=None):
        self.limit = limit
        return self.body if limit is None else self.body[:limit]


def http_error(code_: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://www.youtube.com/x", code_, "Erreur", {}, io.BytesIO())


class Reseau(unittest.TestCase):
    def test_http_get(self):
        answer = Answer(200, "<feed>é</feed>".encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=answer) as urlopen:
            self.assertEqual(topplays.http_get("https://www.youtube.com/feeds/videos.xml?channel_id=x"), "<feed>é</feed>")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://www.youtube.com/feeds/videos.xml?channel_id=x")
        self.assertEqual(request.get_header("User-agent"), "esportly-site/1.0 (+https://esportly.eu)")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 20)
        self.assertEqual(answer.limit, 2_000_000)
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            with self.assertRaises(urllib.error.HTTPError):  # pas d'essai ici : c'est read_feed qui retente
                topplays.http_get("https://www.youtube.com/feeds/videos.xml?channel_id=x")

    def test_http_status(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(200)) as urlopen:
            self.assertEqual(topplays.http_status("https://www.youtube.com/oembed?x"), 200)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].get_header("User-agent"), "esportly-site/1.0 (+https://esportly.eu)")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 20)
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)) as urlopen:
            self.assertEqual(topplays.http_status("https://www.youtube.com/oembed?x"), 404)  # un code d'erreur HTTP est rendu tel quel
        self.assertEqual(urlopen.call_count, 1)
        with mock.patch("urllib.request.urlopen", side_effect=[OSError("coupé"), http.client.IncompleteRead(b"")]) as urlopen:
            self.assertEqual(topplays.http_status("https://www.youtube.com/oembed?x"), 0)  # panne réseau : un second essai, puis 0
        self.assertEqual(urlopen.call_count, 2)
        with mock.patch("urllib.request.urlopen", side_effect=[TimeoutError("trop long"), Answer(200)]) as urlopen:
            self.assertEqual(topplays.http_status("https://www.youtube.com/oembed?x"), 200)
        self.assertEqual(urlopen.call_count, 2)


# --- Rafraîchissement ---------------------------------------------------------------------------------------------

def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def site(root: Path, games=("league-of-legends", "valorant", "dota-2")) -> Path:
    """Crée les 5 pages (vides) de chaque jeu : games/<id>.html et ses 4 équivalents (load_channels les exige)."""
    for folder in blog.GAME_DIRS.values():
        (root / folder).mkdir(parents=True, exist_ok=True)
        for game in games:
            (root / folder / f"{game}.html").write_text("<html></html>", encoding="utf-8")
    return root


def channel(letter: str, name: str) -> dict:
    return {"id": channel_id(letter), "name": name, "proof": "https://lolesports.com/"}


CHANNELS = {"league-of-legends": [channel("a", "LoL Esports"), channel("b", "LCK")],
            "valorant": [channel("c", "VALORANT Esports")],
            "dota-2": [channel("d", "Dota 2")]}


def feeds() -> Feeds:
    """Les 4 flux du site factice : tous répondent ; pour la chaîne « a », 5000 et 100 vues ; pour « b », 3000 ; pour « c », un direct de plus."""
    return Feeds({
        channel_id("a"): feed_xml(entry_xml(code(1), "Finale T1 – G2 : « é »", "2026-10-26T12:00:00+00:00", 5000, author="LoL Esports"),
                                  entry_xml(code(2), "Résumé", "2026-10-25T12:00:00+00:00", 100, author="LoL Esports")),
        channel_id("b"): feed_xml(entry_xml(code(3), "LCK Highlights", "2026-10-24T12:00:00+00:00", 3000, author="LCK")),
        channel_id("c"): feed_xml(entry_xml(code(4), "Ace clutch", "2026-10-26T08:00:00+00:00", 700, author="VALORANT Esports"),
                                  entry_xml(code(5), "LIVE: Day 3", "2026-10-26T09:00:00+00:00", 9999, author="VALORANT Esports")),
        channel_id("d"): feed_xml(entry_xml(code(6), "Rampage", "2026-10-26T10:00:00+00:00", 40, author="Dota 2")),
    })


LOL = [{"id": code(1), "title": "Finale T1 – G2 : « é »", "channel": "LoL Esports", "published": "2026-10-26"},
       {"id": code(3), "title": "LCK Highlights", "channel": "LCK", "published": "2026-10-24"},
       {"id": code(2), "title": "Résumé", "channel": "LoL Esports", "published": "2026-10-25"}]
VALORANT = [{"id": code(4), "title": "Ace clutch", "channel": "VALORANT Esports", "published": "2026-10-26"}]
DOTA = [{"id": code(6), "title": "Rampage", "channel": "Dota 2", "published": "2026-10-26"}]
NAME = "blog-src/topplays.json"


class Rafraichissement(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = site(Path(tmp.name))
        self.put_channels(CHANNELS)

    def put_channels(self, channels: dict) -> None:
        write(self.root, "blog-src/channels.json", json.dumps(channels, ensure_ascii=False))

    def put_previous(self, data: dict, eol: str = "\n") -> None:
        write(self.root, NAME, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).replace("\n", eol) + eol)

    def read(self, name: str = NAME) -> str:
        with (self.root / name).open(encoding="utf-8", newline="") as file:  # read_text n'a `newline` que depuis Python 3.13 ; le job est en 3.12
            return file.read()

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def refresh(self, now=BEFORE_MIDNIGHT, fetch=None, status=None) -> dict[str, str]:
        return quiet(topplays.refresh, self.root, now, fetch or feeds(), status or Statuses())[0]

    def apply(self, **kwargs) -> dict[str, str]:
        changes = self.refresh(**kwargs)
        for name, content in changes.items():
            write(self.root, name, content)
        return changes

    def run_main(self, *argv, fetch=None, status=None, now=BEFORE_MIDNIGHT) -> tuple[int, str, str]:
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            exit_code = topplays.main(list(argv), root=self.root, now=now, fetch=fetch or feeds(), status=status or Statuses())
        return exit_code, out.getvalue(), err.getvalue()

    def test_une_chaine_en_panne(self):
        yesterday = {"league-of-legends": {"fetched": "2026-10-26", "videos": [{"id": code(9), "title": "Veille", "channel": "LCK", "published": "2026-10-24"}]}}
        self.put_previous(yesterday)
        fetch = feeds()
        fetch.feeds[channel_id("b")] = OSError("LCK indisponible")  # le jeu à 2 chaînes : une répond, l'autre non
        fetch.feeds[channel_id("d")] = OSError("Dota indisponible")  # jamais relevé, en panne : absent
        status = Statuses()
        changes = self.refresh(fetch=fetch, status=status)
        data = json.loads(changes[NAME])
        self.assertEqual(data["league-of-legends"], yesterday["league-of-legends"])  # gardée telle quelle, fetched compris
        self.assertNotIn("dota-2", data)
        self.assertEqual(data["valorant"], {"fetched": "2026-10-27", "videos": VALORANT})  # les autres jeux avancent
        self.assertNotIn(code(1), status.asked())  # le jeu en panne n'est pas mis à jour : aucune vidéo vérifiée
        # tous les jeux en panne : rien à changer
        self.apply()
        fetch = Feeds({})
        self.assertEqual(self.refresh(fetch=fetch), {})
        self.assertEqual(json.loads(self.read()), {"league-of-legends": {"fetched": "2026-10-27", "videos": LOL},
                                                    "valorant": {"fetched": "2026-10-27", "videos": VALORANT},
                                                    "dota-2": {"fetched": "2026-10-27", "videos": DOTA}})

    def test_document_non_atom_garde_la_veille(self):
        yesterday = {"league-of-legends": {"fetched": "2026-10-26", "videos": [{"id": code(9), "title": "Veille", "channel": "LCK", "published": "2026-10-24"}]}}
        self.put_previous(yesterday)
        fetch = feeds()
        fetch.feeds[channel_id("b")] = "<html><body>Service indisponible</body></html>"  # bien formé, mais pas un flux : la chaîne est en panne
        fetch.feeds[channel_id("d")] = '<feed xmlns="http://example.com/x"><entry/></feed>'  # jamais relevé : absent
        changes = self.refresh(fetch=fetch)
        data = json.loads(changes[NAME])
        self.assertEqual(data["league-of-legends"], yesterday["league-of-legends"])  # gardée telle quelle, pas une liste vide
        self.assertNotIn("dota-2", data)
        self.assertEqual(data["valorant"], {"fetched": "2026-10-27", "videos": VALORANT})

    def test_include_lu_dans_channels_json(self):
        # le nom du fichier (« Nom du fichier ») n'est pas celui du flux (« LoL Esports ») : le filtre se fait par identifiant de chaîne
        self.put_channels({**CHANNELS, "league-of-legends": [{**channel("a", "Nom du fichier"), "include": HIGHLIGHTS}, channel("b", "LCK")]})
        fetch = feeds()
        fetch.feeds[channel_id("a")] = feed_xml(
            entry_xml(code(11), "T1 vs G2 | HIGHLIGHTS", "2026-10-26T12:00:00+00:00", 100, author="LoL Esports"),
            entry_xml(code(12), "T1 vs G2 | Day 4", "2026-10-26T13:00:00+00:00", 90000, author="LoL Esports"),
            entry_xml(code(13), "VERTICAL | T1 vs G2 | Day 4", "2026-10-26T14:00:00+00:00", 80000, author="LoL Esports"))
        status = Statuses()
        changes = self.refresh(fetch=fetch, status=status)
        data = json.loads(changes[NAME])
        self.assertEqual(data["league-of-legends"], {"fetched": "2026-10-27", "videos": [
            {"id": code(3), "title": "LCK Highlights", "channel": "LCK", "published": "2026-10-24"},  # la chaîne b n'a pas d'include : gardée
            {"id": code(11), "title": "T1 vs G2 | HIGHLIGHTS", "channel": "LoL Esports", "published": "2026-10-26"}]})  # les plus vues, non
        self.assertEqual(data["valorant"], {"fetched": "2026-10-27", "videos": VALORANT})  # les jeux sans include ne changent pas
        self.assertEqual(data["dota-2"], {"fetched": "2026-10-27", "videos": DOTA})
        self.assertEqual(status.asked(), [code(3), code(11), code(4), code(6)])  # l'intégration n'est jamais vérifiée pour une vidéo écartée
        write(self.root, NAME, changes[NAME])
        self.assertEqual(blog.load_topplays(self.root), data)
        self.assertEqual(self.refresh(fetch=fetch), {})  # idempotent
        self.assertEqual(self.run_main("--essai", fetch=fetch), (0, "0 fichier(s) à changer.\n", ""))

    def test_include_sans_aucune_video_qualifiee(self):
        yesterday = {"league-of-legends": {"fetched": "2026-10-26", "videos": [{"id": code(9), "title": "Veille", "channel": "LCK", "published": "2026-10-24"}]}}
        self.put_previous(yesterday)
        self.put_channels({"league-of-legends": [{**channel("a", "LoL Esports"), "include": HIGHLIGHTS}, {**channel("b", "LCK"), "include": HIGHLIGHTS}]})
        fetch = feeds()
        fetch.feeds[channel_id("b")] = feed_xml(entry_xml(code(3), "LCK Day 4", "2026-10-24T12:00:00+00:00", 3000, author="LCK"))
        status = Statuses()
        data = json.loads(self.refresh(fetch=fetch, status=status)[NAME])
        self.assertEqual(data, {"league-of-legends": {"fetched": "2026-10-27", "videos": []}})  # un résultat valide : la veille est remplacée par une liste vide
        self.assertEqual(status.asked(), [])
        write(self.root, NAME, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertEqual(blog.visible_topplays(blog.load_topplays(self.root), TODAY), {})  # la liste vide n'est pas affichée : le bloc est masqué

    def test_include_et_pannes(self):
        yesterday = {"league-of-legends": {"fetched": "2026-10-26", "videos": [{"id": code(9), "title": "Veille", "channel": "LCK", "published": "2026-10-24"}]}}
        self.put_channels({"league-of-legends": [{**channel("a", "LoL Esports"), "include": HIGHLIGHTS}, channel("b", "LCK")]})
        self.put_previous(yesterday)
        fetch = feeds()
        fetch.feeds[channel_id("b")] = OSError("LCK indisponible")  # une chaîne en panne : la veille est gardée, include ou pas
        self.assertEqual(self.refresh(fetch=fetch), {})  # la sélection de la veille reste telle quelle : rien à changer
        self.assertEqual(self.refresh(status=Statuses(default=503)), {})  # de même quand la page oEmbed est en panne
        self.put_channels({"league-of-legends": [{**channel("a", "LoL Esports"), "include": "["}]})  # une expression invalide est refusée avant toute lecture
        fetch = feeds()
        with self.assertRaises(blog.BlogError):
            self.refresh(fetch=fetch)
        self.assertEqual(fetch.calls, [])
        code_, out, err = self.run_main("--verifier", fetch=fetch)
        self.assertEqual((code_, out), (1, ""))
        self.assertTrue(err.startswith("Refus : 1 problème(s)\n  - channels.json : league-of-legends[0].include : expression invalide"), err)
        self.assertEqual(fetch.calls, [])

    def test_panne_signalee_sur_la_sortie(self):
        fetch = feeds()
        fetch.feeds[channel_id("b")] = OSError("LCK indisponible")
        _, printed = quiet(topplays.refresh, self.root, NOW, fetch, Statuses())
        self.assertIn(channel_id("b"), printed)
        self.assertIn("LCK indisponible", printed)

    def test_mise_a_jour_et_idempotence(self):
        status = Statuses()
        changes = self.refresh(status=status)
        self.assertEqual(list(changes), [NAME])
        text = changes[NAME]
        data = json.loads(text)
        self.assertEqual(data, {"league-of-legends": {"fetched": "2026-10-27", "videos": LOL},  # jour de Paris, bien que le 26 en UTC
                                "valorant": {"fetched": "2026-10-27", "videos": VALORANT},
                                "dota-2": {"fetched": "2026-10-27", "videos": DOTA}})
        self.assertEqual(text, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertTrue(text.startswith('{\n  "dota-2": {\n    "fetched": "2026-10-27",\n    "videos": [\n      {\n        "channel"'), text[:90])
        self.assertTrue(text.endswith("}\n") and not text.endswith("\n\n"))
        self.assertIn("« é »", text)  # pas d'échappement \\u00e9
        self.assertNotIn("\\u", text)
        self.assertNotIn("\r", text)  # fichier neuf : fins de ligne LF
        self.assertEqual(status.asked(), [code(1), code(3), code(2), code(4), code(6)])  # l'intégration n'est vérifiée que pour les vidéos retenues
        write(self.root, NAME, text)
        self.assertEqual(self.refresh(), {})  # deuxième exécution le même jour : rien à changer
        self.assertEqual(self.refresh(now=NOW), {})  # même jour de Paris, autre heure
        later = self.refresh(now=NOW + timedelta(days=1))  # le lendemain : fetched avance
        self.assertEqual(json.loads(later[NAME])["valorant"]["fetched"], "2026-10-28")
        self.assertEqual(blog.load_topplays(self.root), data)  # le fichier écrit passe la validation de blog.py

    def test_integration_interdite_dans_le_rafraichissement(self):
        changes = self.refresh(status=Statuses({code(1): 401, code(4): 404, code(6): 403}))  # des refus : la vidéo est écartée, la suivante prise
        data = json.loads(changes[NAME])
        self.assertEqual([one["id"] for one in data["league-of-legends"]["videos"]], [code(3), code(2)])
        self.assertEqual(data["valorant"], {"fetched": "2026-10-27", "videos": []})  # liste vide : un résultat valide
        self.assertEqual(data["dota-2"], {"fetched": "2026-10-27", "videos": []})

    def test_panne_d_oembed_garde_la_veille(self):
        yesterday = {"league-of-legends": {"fetched": "2026-10-26", "videos": [{"id": code(9), "title": "Veille", "channel": "LCK", "published": "2026-10-24"}]}}
        for outage in (0, 429, 500, 503):
            for hit in (code(1), code(3)):  # la panne frappe la 1re vidéo du jeu, ou la 2e : le jeu entier garde la veille
                with self.subTest(outage=outage, hit=hit):
                    self.put_previous(yesterday)
                    status = Statuses({hit: outage, code(6): outage})  # league-of-legends (relevé la veille) et dota-2 (jamais relevé) sont touchés
                    changes, printed = quiet(topplays.refresh, self.root, BEFORE_MIDNIGHT, feeds(), status)
                    data = json.loads(changes[NAME])
                    self.assertEqual(data["league-of-legends"], yesterday["league-of-legends"])  # gardée telle quelle, fetched compris
                    self.assertNotIn("dota-2", data)  # jamais relevé et en panne : absent
                    self.assertEqual(data["valorant"], {"fetched": "2026-10-27", "videos": VALORANT})  # le jeu sans panne est mis à jour
                    self.assertIn("league-of-legends : oEmbed", printed)
                    self.assertIn("dota-2 : oEmbed", printed)
                    self.assertNotIn("valorant : oEmbed", printed)

    def test_panne_d_oembed_rien_a_changer(self):
        self.apply()  # la veille : les 3 jeux relevés
        before = self.snapshot()
        later = NOW + timedelta(days=1)  # le lendemain, fetched avancerait si les jeux étaient mis à jour
        self.assertIn(NAME, self.refresh(now=later))
        for outage in (0, 429, 500, 503):
            with self.subTest(outage):
                self.assertEqual(self.refresh(now=later, status=Statuses(default=outage)), {})  # tous les jeux gardent la veille : rien à changer
                exit_code, out, err = self.run_main(now=later, status=Statuses(default=outage))
                self.assertEqual((exit_code, err), (0, ""))
                self.assertTrue(out.endswith("0 fichier(s) changé(s).\n"), out)  # les pannes sont signalées avant, sur la sortie
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(blog.load_topplays(self.root)["league-of-legends"], {"fetched": "2026-10-27", "videos": LOL})

    def test_fins_de_ligne_conservees(self):
        old = {"league-of-legends": {"fetched": "2026-10-20", "videos": []}}
        self.put_previous(old, eol="\r\n")
        text = self.apply()[NAME]
        self.assertGreater(text.count("\r\n"), 10)
        self.assertEqual(text.count("\n"), text.count("\r\n"))  # CRLF partout, aucune fin de ligne mélangée
        self.assertEqual(text.replace("\r\n", "\n"), json.dumps(json.loads(text), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertEqual(self.refresh(), {})  # identique, en CRLF : rien à changer
        self.assertEqual(self.read(), text)
        self.put_previous({"league-of-legends": {"fetched": "2026-10-20", "videos": []}})  # un fichier LF reste en LF
        self.assertNotIn("\r", self.apply()[NAME])

    def test_jeux_retires_ou_sans_chaine(self):
        self.put_previous({"dota-2": {"fetched": "2026-10-26", "videos": DOTA}, "valorant": {"fetched": "2026-10-26", "videos": VALORANT}})
        self.put_channels({"valorant": [channel("c", "VALORANT Esports")], "dota-2": []})  # dota-2 sans chaîne ; league-of-legends retiré
        data = json.loads(self.refresh()[NAME])
        self.assertEqual(list(data), ["valorant"])  # un jeu sans chaîne n'a pas d'entrée, ni son ancienne sélection
        self.assertEqual(data["valorant"]["fetched"], "2026-10-27")

    def test_rien_a_ecrire_sans_chaines(self):
        (self.root / "blog-src" / "channels.json").unlink()
        self.assertEqual(self.refresh(), {})  # ni chaînes ni sélection : pas de fichier créé
        self.put_channels({})
        self.assertEqual(self.refresh(), {})
        self.assertEqual(self.run_main(), (0, "0 fichier(s) changé(s).\n", ""))
        self.assertFalse((self.root / NAME).exists())
        self.put_previous({"valorant": {"fetched": "2026-10-26", "videos": VALORANT}})  # chaînes toutes retirées : la sélection part
        self.assertEqual(json.loads(self.refresh()[NAME]), {})

    def test_donnees_invalides_refusees(self):
        write(self.root, NAME, "{")
        code_, out, err = self.run_main()
        self.assertEqual((code_, out), (1, ""))
        self.assertTrue(err.startswith("Refus : 1 problème(s)\n  - topplays.json : illisible"), err)
        self.assertEqual(self.read(), "{")
        with self.assertRaises(blog.BlogError):
            self.refresh()

    def test_verifier(self):
        with mock.patch.object(an, "paris", side_effect=AssertionError("fuseau demandé")):  # --verifier n'a pas besoin de la base des fuseaux
            self.assertEqual(self.run_main("--verifier"), (0, "blog-src/channels.json : valide\n", ""))
            self.assertEqual(self.run_main("--verifier", "--essai"), (0, "blog-src/channels.json : valide\n", ""))
            self.put_channels({"league-of-legends": [{"id": "UCabc", "name": "LoL Esports", "proof": "https://lolesports.com/"}]})
            before = self.snapshot()
            code_, out, err = self.run_main("--verifier")
            self.assertEqual((code_, out), (1, ""))
            self.assertTrue(err.startswith("Refus : 1 problème(s)\n  - channels.json : league-of-legends[0].id : « UCabc » invalide"), err)
            self.assertEqual(self.snapshot(), before)
            (self.root / "blog-src" / "channels.json").unlink()  # un fichier absent : rien à valider, donc valide
            self.assertEqual(self.run_main("--verifier"), (0, "blog-src/channels.json : valide\n", ""))

    def test_options_essai_et_ecriture(self):
        before = self.snapshot()
        fetch = feeds()
        self.assertEqual(self.run_main("--essai", fetch=fetch), (0, "1 fichier(s) à changer.\n", ""))
        self.assertEqual(self.snapshot(), before)  # --essai n'écrit rien
        self.assertEqual(self.run_main(fetch=fetch), (0, "1 fichier(s) changé(s).\n", ""))
        self.assertEqual(json.loads(self.read())["valorant"], {"fetched": "2026-10-27", "videos": VALORANT})
        self.assertEqual(self.run_main(fetch=fetch), (0, "0 fichier(s) changé(s).\n", ""))
        self.assertEqual(self.run_main("--essai", fetch=fetch), (0, "0 fichier(s) à changer.\n", ""))
        self.assertEqual(self.run_main(now=None, fetch=Feeds({}))[0], 0)  # sans `now` : l'heure courante ; tout en panne, rien à changer


if __name__ == "__main__":
    unittest.main()
