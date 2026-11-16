"""Menu et pied de page des accueils, pour les pages fabriquées par les scripts (Blog, News).

Un accueil (index.html, fr.html, es.html, de.html, pt.html) a une barre de menu (sections, News, Blog, langues, thème), un menu
burger et un grand pied de page ; les pages fabriquées à partir d'un modèle plus léger (page de jeu, « What's new ») les reçoivent
d'ici, sans rien changer d'autre. Le menu est recopié des accueils (MENU) ; le pied de page est lu dans l'accueil de la langue,
adresses réécrites, si bien qu'un lien ajouté au pied de page d'un accueil arrive sur toutes les pages au prochain passage.

Module commun à actualites.py et blog.py, qui ne s'importent pas l'un l'autre : lancé seul (python3 actualites.py), un script
doit lever ses propres erreurs, d'où ChromeError, que chacun convertit en sa propre exception.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from pathlib import Path

SEO_FILE = "seo/titres.json"  # title et description SEO de chaque page, par chemin public (« /blog-fr/valorant ») ; skill titres-seo
VISIT ="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite"  # compteur de visites et bouton de la bêta
# Depuis le 1er novembre 2026, les pages fr, es, de et pt-BR vivent sous leur sous-dossier de langue (LANG_DIRS) ; l'anglais reste à la
# racine. Les tables donnent des chemins depuis la racine du site ; une page les voit à travers prefix_for (« ../ » par dossier).
LANG_DIRS = {"en": "", "fr": "fr/", "es": "es/", "de": "de/", "pt-BR": "pt/"}
HOMES = {"fr": "fr.html", "en": "index.html", "es": "es.html", "de": "de.html", "pt-BR": "pt.html"}  # les accueils, à la racine
HUBS = {"en": "blog.html", "fr": "fr/blog.html", "es": "es/blog.html", "de": "de/blog.html", "pt-BR": "pt/blog.html"}  # accueils du Blog
BLOG_LABEL = "Blog"  # le lien du Blog dans le menu, le même dans les 5 langues
LIVE_LABEL = "Live"  # le lien de la page Live (matchs du jour) dans le menu, le même dans les 5 langues, pastille rouge (a.live::before)
LIVE_PAGES = {"en": "live.html", "fr": "fr/live.html", "es": "es/live.html", "de": "de/live.html", "pt-BR": "pt/live.html"}  # une par langue
BLOG_DIRS = {"en": "blog", "fr": "fr/blog", "es": "es/blog", "de": "de/blog", "pt-BR": "pt/blog"}  # une page par article : <dossier>/<id>.html

# Marques de paris (bookmakers) : le site n'en affiche aucune (audit légal, risque ANJ/App Store). Sous-chaînes ;
# « pari » et « stake » ne comptent que comme mots entiers, pour ne pas filtrer « Paris » (PSG) par simple sous-chaîne.
BETTING = ("1win", "betboom", "betway", "gg.bet", "ggbet", "bet365", "winline", "fonbet", "parivision")
BETTING_WORDS = ("pari", "stake")


def is_betting(name: str) -> bool:
    """Vrai si un nom d'équipe ou le titre d'un match est une marque de paris."""
    low = (name or "").lower()
    if any(b in low for b in BETTING):
        return True
    words = low.replace("\u2013", " ").replace("\u2014", " ").replace("-", " ").replace(".", " ").split()
    return any(w in BETTING_WORDS for w in words)


def prefix_for(path: str) -> str:
    """Ce qui précède un chemin depuis la racine, vu de la page `path` (chemin depuis la racine) : « ../ » par dossier."""
    return "../" * path.count("/")


def home_link(lang: str, prefix: str) -> str:
    """L'accueil de la langue vu d'une page, sous la forme des liens du site : « ./ », « ../ » ou « / » pour l'anglais (index.html),
    « fr.html », « ../../fr.html » ou « /fr.html » sinon."""
    if lang == "en":
        return prefix or "./"
    return prefix + HOMES[lang]


class ChromeError(Exception):
    """Page impossible à habiller : `problems` liste ce qui manque dans le modèle ou l'accueil."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def seo_texts(root: Path) -> dict[str, dict[str, str]]:
    """Les titles et descriptions SEO du site (SEO_FILE) : {chemin public: {"title", "description"}} ; {} sans fichier.
    Le fichier est tenu par le skill titres-seo (règles : pas de marque en suffixe, 55 à 63 caractères) ; les générateurs y
    lisent le <title> et la description d'une page, le H1 restant le titre de la page."""
    path = root / SEO_FILE
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(not isinstance(v, dict) or set(v) != {"title", "description"} for v in data.values()):
        raise ChromeError([f"{SEO_FILE} : un objet {{chemin: {{title, description}}}} attendu"])
    return data


def seo(texts: dict[str, dict[str, str]], path: str, title: str, description: str) -> tuple[str, str]:
    """Le title et la description d'une page : ceux de `texts` (seo_texts) si la page y est, sinon `title` et `description`
    (sans marque ajoutée). `path` : le fichier de la page (« blog-fr/valorant.html ») ou son chemin public."""
    entry = texts.get("/" + path.removeprefix("/").removesuffix(".html"), {})
    return entry.get("title", title), entry.get("description", description)


# Menu du site, recopié des accueils (index.html, fr.html, es.html, de.html, pt.html ; test_menu_identique_aux_accueils le vérifie) :
# `nav` aria-label de la barre ; `bar` liens de la barre (ancre de l'accueil, libellé) ; `panel` ceux du panneau mobile, qui diffèrent ;
# `news` la page News de la langue (an.PAGES) ; `beta` le bouton de la bêta ; `theme` le groupe puis les boutons système, clair, sombre.
# Sur le Blog, la barre et le panneau finissent par la page News puis « Blog » (LABELS kicker), marqué aria-current="page".
# Mêmes règles que LABELS : aucun « < », « > », « & » ni « " ».
MENU = {
    "en": dict(nav="Sections", bar=(("jeux", "Games"), ("equipes", "Teams"), ("offres", "eSportly+")),
               panel=(("jeux", "Games"), ("offres", "eSportly+")),
               news="News", beta="Join the beta", theme=("Theme", "System theme", "Light theme", "Dark theme")),
    "fr": dict(nav="Sections de la page", bar=(("jeux", "Jeux"), ("equipes", "Équipes"), ("offres", "eSportly+")),
               panel=(("jeux", "Jeux"), ("offres", "eSportly+")),
               news="Actualités", beta="Rejoindre la bêta", theme=("Thème", "Thème du système", "Thème clair", "Thème sombre")),
    "es": dict(nav="Secciones", bar=(("jeux", "Juegos"), ("equipes", "Equipos"), ("offres", "eSportly+")),
               panel=(("jeux", "Juegos"), ("offres", "eSportly+")),
               news="Noticias", beta="Únete a la beta", theme=("Tema", "Tema del sistema", "Tema claro", "Tema oscuro")),
    "de": dict(nav="Abschnitte", bar=(("jeux", "Spiele"), ("equipes", "Teams"), ("offres", "eSportly+")),
               panel=(("jeux", "Spiele"), ("offres", "eSportly+")),
               news="Nachrichten", beta="Zur Beta", theme=("Design", "Systemdesign", "Helles Design", "Dunkles Design")),
    "pt-BR": dict(nav="Seções", bar=(("jeux", "Jogos"), ("equipes", "Times"), ("offres", "eSportly+")),
                  panel=(("jeux", "Jogos"), ("offres", "eSportly+")),
                  news="Notícias", beta="Entrar na beta", theme=("Tema", "Tema do sistema", "Tema claro", "Tema escuro")),
}
# Icônes des accueils : boutons du thème (système, clair, sombre) et bouton du menu burger (ouvrir, fermer).
THEME_ICONS = {
    "system": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
              'aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    "light": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
             '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4'
             'M17.7 6.3l1.4-1.4"/></svg>',
    "dark": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></svg>',
}
MENU_ICONS = ('<svg class="open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
              'aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg><svg class="close" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>')

# Style du menu du site (render_menu), règle pour règle celui des accueils (fr.html), mêmes variables et mêmes points de rupture :
# barre au-dessus de 860 px, menu burger en dessous, bouton de la bêta caché sous 520 px. Les règles de MENU_STYLE_OWN n'ont pas
# d'équivalent exact sur l'accueil : largeur de l'en-tête (le .wrap des pages modèles fait 960 px, la barre ne tiendrait pas), entrée
# active (« Blog », « Live »), ancres des sources qui passent sous l'en-tête désormais collant, et deux points de rupture propres aux
# pages fabriquées : avec « Blog » et « Live » en plus, la barre ne tient plus sur une ligne sous 1280 px (mesuré : environ 1 260 px
# en français). De 1150 à 1279 px, l'en-tête reprend la marge des pages modèles (20 px) et cache le sélecteur de thème (comme
# l'accueil le fait déjà sous 860 px) ; sous 1150 px (mesuré : la barre espagnole, la plus large, tient encore à 1 150 px), la barre
# laisse place au menu burger, comme sous 860 px sur l'accueil.
MENU_STYLE_OWN = (
    "header .wrap{max-width:1440px;padding:0 clamp(16px,5.5vw,80px);height:clamp(64px,7vw,88px);gap:clamp(12px,3vw,40px)}",
    "header nav>a[aria-current]{color:var(--text)}",
    "header nav>a[aria-current]::after{transform:scaleX(1)}",
    ".menu .panel>a[aria-current]{border-bottom-color:var(--or)}",
    "@media (max-width:720px){.soon{margin-left:auto;font-size:14px;padding:0 14px}}",
    "@media (prefers-color-scheme:light){:root:not([data-theme]) a.soon{color:#FFC53D}}",
    ".sources li{scroll-margin-top:96px}",
    "@media (max-width:1279px){header .wrap{padding:0 20px}}",
    "@media (max-width:1149px){header nav{display:none!important}.menu{display:block}}",
)
MENU_STYLE = (
    "header{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--nuit) 82%,transparent);"
    "-webkit-backdrop-filter:blur(18px) saturate(1.6);backdrop-filter:blur(18px) saturate(1.6)}",
    "@media (prefers-reduced-transparency:reduce){header{background:var(--nuit);-webkit-backdrop-filter:none;backdrop-filter:none}}",
    MENU_STYLE_OWN[0],
    "header nav{margin-left:auto;display:flex;gap:28px;font-size:16px}",
    "header nav{align-items:center}",
    "header nav a{color:var(--soft);text-decoration:none}",
    "header nav a:hover{color:var(--text)}",
    'a.live::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:#FF4D4D;margin:0 8px 2px 0}',
    "header nav>a:not(.lang){position:relative;padding:6px 0}",
    'header nav>a:not(.lang)::after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;border-radius:2px;background:var(--or);'
    "transform:scaleX(0);transition:transform .2s}",
    "header nav>a:not(.lang):hover::after{transform:scaleX(1)}",
    MENU_STYLE_OWN[1],
    MENU_STYLE_OWN[2],
    ".soon{min-height:44px;padding:0 20px;border-radius:999px;background:var(--text);color:var(--nuit);display:flex;align-items:center;"
    "font-weight:700;font-size:15px;text-decoration:none;white-space:nowrap}",
    ".menu{display:none;margin-left:auto}",
    ".menu summary{list-style:none;width:44px;height:44px;border-radius:12px;border:1px solid var(--border);display:flex;align-items:center;"
    "justify-content:center;cursor:pointer;color:var(--text)}",
    ".menu summary::-webkit-details-marker{display:none}",
    ".menu summary svg{width:22px;height:22px}",
    ".menu .close{display:none}",
    ".menu[open] .open{display:none}",
    ".menu[open] .close{display:block}",
    ".menu .panel{position:fixed;left:0;right:0;top:100%;height:calc(100dvh - var(--hh,64px));background:var(--nuit);"
    "padding:20px clamp(16px,5.5vw,80px) 32px;display:flex;flex-direction:column;gap:4px;overflow:auto;border-top:1px solid var(--raised)}",
    ".menu .panel a{display:flex;align-items:center;min-height:56px;font:700 28px var(--display);color:var(--text);text-decoration:none;"
    "border-bottom:1px solid var(--raised)}",
    ".menu .panel .soonm{margin-top:20px;justify-content:center;border:0;border-radius:999px;background:var(--or);color:var(--on-or);"
    "font:700 17px -apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif}",
    MENU_STYLE_OWN[3],
    ".menu .panel .langsm{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}",
    ".menu .panel .langsm a{min-height:44px;padding:0 14px;border:1px solid var(--border);border-radius:999px;"
    "font:600 15px -apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif;color:var(--soft)}",
    ".menu .panel .langsm a[aria-current]{border-color:var(--or);color:var(--text)}",
    "[hidden]{display:none!important}",
    ".theme{position:fixed;right:12px;bottom:12px;z-index:30;display:inline-flex;gap:2px;padding:2px;border-radius:999px;border:1px solid var(--border);background:var(--surface);opacity:.4;transition:opacity .2s}",
    ".theme:hover,.theme:focus-within{opacity:1}",
    ".theme button{width:28px;height:28px;border:0;border-radius:999px;background:transparent;color:var(--muted);display:flex;"
    "align-items:center;justify-content:center;cursor:pointer}",
    ".theme button svg{width:16px;height:16px}",
    ".theme button[aria-pressed=true]{background:var(--raised);color:var(--text)}",
    "@media (max-width:1320px){header nav{gap:16px}}",
    "@media (max-width:860px){header nav{display:none!important}.menu{display:block}}",
    MENU_STYLE_OWN[4],
    "@media (max-width:520px){.soon{display:none}}",
    ':root[data-theme="light"] a.soon{color:#FFC53D}',
    MENU_STYLE_OWN[5],
    MENU_STYLE_OWN[6],
    MENU_STYLE_OWN[7],
    MENU_STYLE_OWN[8],
)

# Script des accueils, recopié tel quel (même texte, donc même empreinte que dans leur CSP ; test_menu_identique_aux_accueils le
# vérifie) : il applique le thème choisi, montre le sélecteur de thème (caché sans JavaScript), mesure la hauteur de l'en-tête pour
# le panneau du menu burger (--hh) et le referme au clic sur un lien. Ses autres parties (compte à rebours #worlds, data-until,
# Échap sur #voir-…) ne trouvent rien sur le Blog et ne font rien. Sans JavaScript, le menu burger (<details>) s'ouvre quand même.
MENU_JS = (
    "(function(){var d=document.documentElement,k='esportly-theme';function g(){try{return localStorage.getItem(k)}"
    "catch(e){return null}}function s(v){try{if(v==='system')localStorage.removeItem(k);else localStorage.setItem(k"
    ",v)}catch(e){}}function a(v){if(v==='light'||v==='dark')d.setAttribute('data-theme',v);else d.removeAttribute("
    "'data-theme');var b=document.querySelectorAll('[data-theme-set]');for(var i=0;i<b.length;i++)b[i].setAttribute"
    "('aria-pressed',String(b[i].getAttribute('data-theme-set')===(v==='light'||v==='dark'?v:'system')))}a(g());doc"
    "ument.addEventListener('DOMContentLoaded',function(){var t=document.getElementById('theme');if(t)t.hidden=fals"
    "e;a(g());var b=document.querySelectorAll('[data-theme-set]');for(var i=0;i<b.length;i++)b[i].addEventListener("
    "'click',function(){var v=this.getAttribute('data-theme-set');s(v);a(v)});var w=document.getElementById('worlds"
    "');if(w){var f=Date.UTC(2026,10,14),n=new Date(),x=Math.round((f-Date.UTC(n.getFullYear(),n.getMonth(),n.getDa"
    "te()))/864e5);if(x<0)w.hidden=true;else{var q=w.querySelector('b');if(q)q.textContent=x}}var u=document.queryS"
    "electorAll('[data-until]');for(var j=0;j<u.length;j++){if(new Date()>=new Date(u[j].getAttribute('data-until')"
    "))u[j].hidden=true}var mm=document.querySelector('details.menu');if(mm){var hd=document.querySelector('header'"
    ");var sh=function(){document.documentElement.style.setProperty('--hh',hd.offsetHeight+'px')};sh();addEventList"
    "ener('resize',sh);var ml=mm.querySelectorAll('a');for(var z=0;z<ml.length;z++)ml[z].addEventListener('click',f"
    "unction(){mm.open=false})}document.addEventListener('keydown',function(e){if(e.key==='Escape'&&location.hash.i"
    "ndexOf('#voir-')===0)location.hash='appareils'})"
    # Recherche d'équipe du panneau « Équipes » : la liste des 83 équipes n'est pas dans la page (elle y pèserait sur les 847
    # pages du site), elle est demandée au premier clic dans le champ, une seule fois. Sans elle, le formulaire mène quand même
    # à la page des équipes : la recherche ne casse rien si le fichier manque ou si le script ne tourne pas.
    # Les panneaux (jeux, équipes) se referment dès qu'on clique ailleurs ou qu'on appuie sur Échap, et l'un ferme l'autre :
    # un <details> resté ouvert suivait le visiteur sur toute la page.
    ";var megs=document.querySelectorAll('header details.mega');document.addEventListener('click',function(e){for(var i=0"
    ";i<megs.length;i++){if(megs[i].open&&!megs[i].contains(e.target))megs[i].open=false}});document.addEventListener('ke"
    "ydown',function(e){if(e.key==='Escape')for(var i=0;i<megs.length;i++)megs[i].open=false});for(var q=0;q<megs.length;"
    "q++)megs[q].addEventListener('toggle',function(){if(!this.open)return;for(var i=0;i<megs.length;i++)if(megs[i]!==thi"
    "s)megs[i].open=false});"
    "var tss=document.querySelectorAll('.tsearch'),idx=null,asked=0;var load=function(src){if(asked)return;asked=1;fe"
    "tch(src).then(function(r){return r.json()}).then(function(j){idx=j;for(var k=0;k<tss.length;k++){var e=tss[k].qu"
    "erySelector('datalist');if(!e)continue;e.textContent='';for(var i=0;i<j.length;i++){var o=document.createElement"
    "('option');o.value=j[i].nom;e.appendChild(o)}}}).catch(function(){})};for(var y=0;y<tss.length;y++){(function(ts"
    "){var inp=t"
    "s.querySelector('input');var go=function(){load(ts.getAttribute('data-src'))};inp.addEventListener('focus',go);i"
    "np.addEventListener('input',go);ts.addEventListener('submit',function(e){if(!idx)return;var v=inp.value.trim().t"
    "oLowerCase();if(!v)return;for(var i=0;i<idx.length;i++){if(String(idx[i].nom).toLowerCase()===v||String(idx[i].s"
    "lug).toLowerCase()===v){e.preventDefault();location.href=ts.getAttribute('data-dir')+idx[i].slug+'.html';return}"
    "}})})(tss[y])}"
    "})})();"
)
MENU_HASH = base64.b64encode(hashlib.sha256(MENU_JS.encode("utf-8")).digest()).decode()  # pour script-src
HEADER = re.compile(r"<header>.*?</header>", re.S)
SCRIPT_SRC = re.compile(r"(?<![\w-])script-src(?![\w-])[^;]*")
CSP_META = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"')



# Style du pied de page des accueils, règle pour règle (test_pied_de_page_identique_aux_accueils le vérifie), sauf FOOTER_STYLE_OWN :
# les pages modèles ont leur propre pied de page (.wrap de 960 px, une ligne) ; la largeur de l'en-tête du menu s'applique aussi ici,
# pour que les deux s'alignent.
FOOTER_STYLE_OWN = (
    "footer .wrap{max-width:1440px;padding-left:clamp(16px,5.5vw,80px);padding-right:clamp(16px,5.5vw,80px)}",
)
FOOTER_STYLE = (
    "footer .wrap{display:block;padding-top:56px;padding-bottom:32px}",
    FOOTER_STYLE_OWN[0],
    ".fgrid{display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr;gap:40px}",
    ".fbrand p{margin:14px 0 18px;max-width:34ch;font-size:15px;color:var(--soft)}",
    ".fbrand .brand{font-size:inherit}",
    ".fbeta{display:inline-flex;align-items:center;min-height:44px;padding:0 20px;border-radius:999px;background:var(--or);"
    "color:var(--on-or)!important;font-weight:700;text-decoration:none}",
    "footer h3{margin:0 0 12px;font:700 15px -apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif;letter-spacing:.06em;"
    "text-transform:uppercase;color:var(--text)}",
    "footer ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}",
    "footer ul a{color:var(--muted);text-decoration:none;font-size:15px}",
    "footer ul a:hover{color:var(--text)}",
    ".fbottom{margin-top:44px;padding-top:20px;border-top:1px solid var(--raised);display:flex;flex-wrap:wrap;gap:8px 24px;"
    "justify-content:space-between;font-size:13px;color:var(--muted)}",
    ".fbottom a{color:inherit}",
    "@media (max-width:860px){.fgrid{grid-template-columns:1fr 1fr;gap:32px 20px}.fbrand{grid-column:1/-1}}",
    ".flag{width:22px;height:15px;border-radius:3px;box-shadow:0 0 0 1px rgba(127,127,127,.35);vertical-align:-2px;margin-right:8px}",
    "footer li.fl a{display:inline-flex;align-items:center}",
    "footer li.fl a[aria-current]{color:var(--text)}",
)

# --- Filtre par jeu ---------------------------------------------------------------------------------------------
# Les pages News et l'accueil du Blog portent une rangée de boutons « un jeu » : chaque élément de la liste a data-game="<jeu>", un clic
# sur un bouton mène à l'ancre #f-<jeu> et le CSS (:target + :has) ne laisse voir que ce jeu. Aucun script : la page reste valable sans
# JavaScript, l'adresse (/news#f-valorant) se partage, et « Tous les jeux » (#f-all) remet tout.

GAMES: tuple[str, ...] = (  # les 14 jeux du site, dans l'ordre d'affichage
    "league-of-legends", "counter-strike-2", "valorant", "rocket-league", "dota-2", "overwatch-2", "rainbow-six-siege",
    "call-of-duty", "mobile-legends", "honor-of-kings", "ea-sports-fc", "starcraft-2", "starcraft-brood-war", "wild-rift")
GAME_DIRS = {"en": "games", "fr": "fr/jeux", "es": "es/juegos", "de": "de/spiele", "pt-BR": "pt/jogos"}  # une page par jeu : <dossier>/<jeu>.html
# Le nom affiché de chaque jeu. Il ne se traduit pas : les cinq langues écrivent « League of Legends ». Écrit ici plutôt que relu
# dans les pages (read_game_names) pour que le menu se fabrique sans toucher au disque ; test_noms_de_jeux les compare au site.
GAME_NAMES = {
    "league-of-legends": "League of Legends", "counter-strike-2": "Counter-Strike 2", "valorant": "Valorant",
    "rocket-league": "Rocket League", "dota-2": "Dota 2", "overwatch-2": "Overwatch 2", "rainbow-six-siege": "Rainbow Six Siege",
    "call-of-duty": "Call of Duty", "mobile-legends": "Mobile Legends: Bang Bang", "honor-of-kings": "Honor of Kings",
    "ea-sports-fc": "EA Sports FC", "starcraft-2": "StarCraft II", "starcraft-brood-war": "StarCraft: Brood War",
    "wild-rift": "League of Legends: Wild Rift"}
# Jeux dont le logo est une image blanche : sur fond clair, elle s'inverse (même traitement que les pages du Blog).
MONO_LOGOS = ("call-of-duty", "counter-strike-2", "ea-sports-fc", "honor-of-kings", "overwatch-2", "rocket-league", "starcraft-brood-war")
TEAMS_PAGES = {"en": "teams.html", "fr": "fr/equipes.html", "es": "teams.html", "de": "teams.html", "pt-BR": "teams.html"}
# Libellés du bas du panneau des jeux, par langue : (tous les jeux, toutes les équipes).
MEGA_LINKS = {"en": ("All games", "All teams", "All competitions"), "fr": ("Tous les jeux", "Toutes les équipes", "Toutes les compétitions"),
              "es": ("Todos los juegos", "Todos los equipos", "Todas las competiciones"),
              "de": ("Alle Spiele", "Alle Teams", "Alle Wettbewerbe"),
              "pt-BR": ("Todos os jogos", "Todos os times", "Todas as competições")}
COMP_PAGES = {"en": "competitions.html", "fr": "fr/competitions.html", "es": "es/competiciones.html",
              "de": "de/wettbewerbe.html", "pt-BR": "pt/competicoes.html"}
CHEVRON = ('<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>')


def _game_links(lang: str, up: str) -> str:
    """Les 14 jeux, chacun son logo (le nom en texte de remplacement : les logos sont des logotypes, les répéter en toutes lettres
    ferait doublon pour un lecteur d'écran)."""
    return "".join(f'<li><a href="{up}{GAME_DIRS[lang]}/{game}.html">'
                   f'<img src="{up}logos-jeux/{game}.png" alt="{html.escape(GAME_NAMES[game], quote=True)}" loading="lazy"></a></li>'
                   for game in GAMES)


def games_menu(lang: str, up: str, home: str) -> str:
    """Le menu des jeux de la barre : un panneau (mega menu) qui s'ouvre sur les 14 jeux et mène à leur page. C'est un <details>,
    comme le menu de langue : aucun script, il s'ouvre même sans JavaScript. `up` : ce qui précède un chemin de la racine vu de la
    page ; `home` : l'accueil de la langue (pour l'ancre « tous les jeux » de la page d'accueil)."""
    label, teams = MENU[lang]["bar"][0][1], MEGA_LINKS[lang][1]
    return (f'<details class="mega"><summary>{label}{CHEVRON}</summary>'
            f'<div class="megap"><ul class="megag">{_game_links(lang, up)}</ul>'
            f'<p class="megaf"><a href="{home}#jeux">{MEGA_LINKS[lang][0]} →</a>'
            f'<a href="{up}{TEAMS_PAGES[lang]}">{teams} →</a>'
            f'<a href="{up}{COMP_PAGES[lang]}">{MEGA_LINKS[lang][2]} →</a></p></div></details>')


ROOT = Path(__file__).resolve().parents[2]  # la racine du site, pour les données que le menu affiche
TEAM_DIRS = {"en": "teams", "fr": "fr/equipes", "es": "teams", "de": "teams", "pt-BR": "teams"}
# Le titre des vedettes dit d'où vient la liste : sans cela, dix équipes sans ordre apparent ressemblent à un choix au hasard.
TEAM_LABELS = {
    "en": ("By game", "Most active this season", "Find a team", "Team name", "All teams"),
    "fr": ("Par jeu", "Les plus actives cette saison", "Trouver une équipe", "Nom de l'équipe", "Toutes les équipes"),
    "es": ("Por juego", "Las más activas esta temporada", "Buscar un equipo", "Nombre del equipo", "Todos los equipos"),
    "de": ("Nach Spiel", "Am aktivsten diese Saison", "Team finden", "Name des Teams", "Alle Teams"),
    "pt-BR": ("Por jogo", "Os mais ativos nesta temporada", "Encontrar um time", "Nome do time", "Todos os times"),
}
# Les jeux qui ont des équipes, dans l'ordre de la page « Toutes les équipes ».
TEAM_GAMES = ("league-of-legends", "counter-strike-2", "valorant", "rocket-league", "dota-2", "overwatch-2", "rainbow-six-siege")
STARS = ROOT / "equipes/vedettes.json"  # écrit par matchs.py : les équipes qui jouent le plus, avec leur logo
_stars: list[dict] | None = None


def stars() -> list[dict]:
    """Les équipes mises en avant dans le panneau (equipes/vedettes.json, écrit par matchs.py). Liste vide si le fichier manque :
    le panneau garde ses jeux et sa recherche, il ne casse pas."""
    global _stars
    if _stars is None:
        try:
            found = json.loads(STARS.read_bytes().decode("utf-8"))
            _stars = found if isinstance(found, list) else []
        except (OSError, ValueError):
            _stars = []
    return _stars


def _team_links(lang: str, up: str) -> str:
    """Les deux colonnes du panneau : les jeux à gauche, les équipes à suivre (logo et nom) à droite."""
    by_game, teams = TEAM_LABELS[lang][0], TEAM_LABELS[lang][1]
    names = read_game_names(ROOT).get(lang) or read_game_names(ROOT).get("en", {})
    games = "".join(f'<li><a href="{up}{TEAMS_PAGES[lang]}#{slug}">{html.escape(names.get(slug, slug))}</a></li>'
                    for slug in TEAM_GAMES)
    stars_html = "".join(
        f'<li><a href="{up}{TEAM_DIRS[lang]}/{team["slug"]}.html">'
        + (f'<i class="tl"><img src="{up}logos-equipes/{team["logo"]}" alt="" width="128" height="116" loading="lazy"></i>'
           if team.get("logo") else "")
        + f'<span>{html.escape(team["nom"])}</span></a></li>' for team in stars())
    right = f'<div class="tcol"><p class="tcolh">{html.escape(teams)}</p><ul class="tstars">{stars_html}</ul></div>' if stars_html else ""
    return (f'<div class="tcols"><div class="tcol"><p class="tcolh">{html.escape(by_game)}</p>'
            f'<ul class="tgames">{games}</ul></div>{right}</div>')


def _team_search(lang: str, up: str, ident: str) -> str:
    """Le champ de recherche du bas : il mène à la page d'une équipe quand son nom est reconnu, sinon à la page des équipes.
    La liste des équipes n'est pas écrite ici — le script la demande au premier clic (equipes/index-pages.json).

    `ident` distingue le champ de la barre de celui du burger : les deux sont dans la page, et deux identifiants identiques
    casseraient l'étiquette comme la liste de suggestions."""
    find, placeholder = TEAM_LABELS[lang][2], TEAM_LABELS[lang][3]
    return (f'<form class="tsearch" action="{up}{TEAMS_PAGES[lang]}" data-src="{up}equipes/index-pages.json" '
            f'data-dir="{up}{TEAM_DIRS[lang]}/"><label for="tq-{ident}">{html.escape(find)}</label>'
            f'<input id="tq-{ident}" name="q" type="search" list="eql-{ident}" autocomplete="off" '
            f'placeholder="{html.escape(placeholder, quote=True)}"><datalist id="eql-{ident}"></datalist></form>')


def teams_menu(lang: str, up: str) -> str:
    """Le menu des équipes de la barre : un panneau comme celui des jeux (un <details>, aucun script pour l'ouvrir) avec les
    jeux d'un côté, les équipes à suivre de l'autre, et une recherche en bas pour les 83 autres."""
    label, all_teams = MENU[lang]["bar"][1][1], TEAM_LABELS[lang][4]
    return (f'<details class="mega team"><summary>{label}{CHEVRON}</summary>'
            f'<div class="megap teamp">{_team_links(lang, up)}{_team_search(lang, up, "bar")}'
            f'<p class="megaf"><a href="{up}{TEAMS_PAGES[lang]}">{html.escape(all_teams)} →</a></p></div></details>')


def teams_panel(lang: str, up: str) -> str:
    """Le même menu des équipes dans le panneau du burger : une ligne qui se déplie, sans panneau flottant."""
    label = MENU[lang]["bar"][1][1]
    return (f'<details class="megam team"><summary>{label}{CHEVRON}</summary>'
            f'<div class="teamm">{_team_links(lang, up)}{_team_search(lang, up, "menu")}</div></details>')


def games_panel(lang: str, up: str) -> str:
    """Le même menu des jeux dans le panneau du burger : une ligne « Jeux » qui se déplie sur la liste, sans panneau flottant."""
    label = MENU[lang]["panel"][0][1]
    return f'<details class="megam"><summary>{label}{CHEVRON}</summary><ul>{_game_links(lang, up)}</ul></details>'


MEGA_STYLE = (
    # Le panneau s'ouvre sous SON bouton, aligné à son bord gauche : ancré sur la barre entière, il s'ouvrait sous la marque,
    # loin du mot cliqué, et on ne comprenait plus ce qui avait ouvert quoi. Le débordement à droite est tenu par max-width.
    "header .wrap{position:relative}",
    ".mega{position:relative}",
    ".mega>summary{list-style:none;display:flex;align-items:center;gap:6px;cursor:pointer;color:var(--soft);padding:6px 0}",
    ".mega>summary::-webkit-details-marker{display:none}",
    ".mega>summary:hover{color:var(--text)}",
    ".mega .chev{width:16px;height:16px;transition:transform .2s}",
    ".mega[open] .chev{transform:rotate(180deg)}",
    # Le panneau s'arrête à la largeur de ses jeux : tendu d'un bord à l'autre, il laissait un grand vide à droite.
    ".megap{position:absolute;left:0;right:auto;width:max-content;max-width:min(86vw,860px);top:calc(100% + 8px);z-index:60;"
    "padding:10px;border-radius:20px;"
    "background:var(--surface);border:1px solid var(--border);box-shadow:0 24px 60px rgba(0,0,0,.42)}",
    # Sept colonnes : les 14 jeux tombent en deux rangées pleines, sans case vide. La barre (donc ce panneau) disparaît sous
    # 1150 px au profit du menu burger : pas besoin de largeurs de secours.
    # Une petite pointe sous le mot cliqué : sans elle, le panneau semble flotter et on ne voit pas ce qui l'a ouvert.
    '.megap::before{content:"";position:absolute;top:-7px;left:20px;width:13px;height:13px;transform:rotate(45deg);'
    "background:var(--surface);border-left:1px solid var(--border);border-top:1px solid var(--border);border-radius:3px 0 0 0}",
    ".megag{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(7,minmax(104px,1fr));gap:2px}",
    ".megag a{display:flex;align-items:center;justify-content:center;min-height:42px;padding:0 8px;border-radius:12px}",
    ".megag a:hover{background:var(--raised)}",
    ".megag img{height:21px;width:auto;max-width:90%;object-fit:contain}",
    ".megaf{display:flex;flex-wrap:wrap;gap:14px;margin:8px 4px 0;padding-top:8px;border-top:1px solid var(--border);font-size:14px}",
    # Le panneau des équipes : les jeux d'un côté, les équipes à suivre de l'autre, la recherche en bas.
    ".teamp{width:max-content;max-width:min(94vw,660px);padding:14px}",
    ".mega.team .megaf{margin-top:10px}",
    ".tcols{display:grid;grid-template-columns:168px minmax(0,1fr);gap:18px;align-items:start}",
    ".tcol{min-width:0}",
    ".tcolh{margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}",
    ".tgames,.tstars{list-style:none;margin:0;padding:0;display:grid;gap:2px}",
    ".tstars{grid-template-columns:repeat(2,minmax(158px,1fr))}",
    ".tgames a,.tstars a{display:flex;align-items:center;gap:8px;min-height:34px;padding:0 8px;border-radius:10px;"
    "color:var(--text);text-decoration:none;font-weight:600;font-size:14px}",
    ".tgames a:hover,.tstars a:hover{background:var(--raised)}",
    ".tstars i.tl{width:24px;height:24px;border-radius:7px;background:#fff;display:inline-flex;align-items:center;"
    "justify-content:center;flex-shrink:0;overflow:hidden}",
    ".tstars i.tl img{max-width:19px;max-height:19px;width:auto;height:auto}",
    ".tstars span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".tsearch{display:grid;gap:6px;width:100%;margin:12px 0 0;padding-top:12px;border-top:1px solid var(--border)}",
    ".tsearch label{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}",
    ".tsearch input{width:100%;padding:9px 12px;border-radius:12px;border:1px solid var(--border);background:var(--raised);"
    "color:var(--text);font:inherit;font-size:14px}",
    ".teamm{padding:6px 0 12px}",
    "@media (max-width:560px){.tcols{grid-template-columns:minmax(0,1fr)}}",
    ".megaf a{color:var(--soft);font-weight:600}",
    ".megam>summary{list-style:none;display:flex;align-items:center;justify-content:space-between;min-height:56px;"
    "font:700 28px var(--display);color:var(--text);border-bottom:1px solid var(--raised);cursor:pointer}",
    ".megam>summary::-webkit-details-marker{display:none}",
    ".megam .chev{width:20px;height:20px;transition:transform .2s}",
    ".megam[open] .chev{transform:rotate(180deg)}",
    ".megam ul{list-style:none;margin:0;padding:8px 0 12px;display:grid;gap:2px}",
    ".megam a{display:flex;align-items:center;min-height:48px}",
    ".megam img{height:20px;width:auto;max-width:70%;object-fit:contain}",
    # Logos blancs : sur fond clair, on les inverse, comme sur les pages du Blog.
    ",".join(f'.megag img[src$="/{game}.png"],.megam img[src$="/{game}.png"]' for game in MONO_LOGOS) + "{filter:none}",
    ':root[data-theme="light"] :is(' + ",".join(f'.megag img[src$="/{game}.png"],.megam img[src$="/{game}.png"]' for game in MONO_LOGOS) + "){filter:invert(1)}",
    "@media (prefers-color-scheme:light){:root:not([data-theme]) :is("
    + ",".join(f'.megag img[src$="/{game}.png"],.megam img[src$="/{game}.png"]' for game in MONO_LOGOS) + "){filter:invert(1)}}",
    ':root[data-theme="light"] .megap{box-shadow:0 24px 60px rgba(14,20,36,.18)}',
    "@media (prefers-color-scheme:light){:root:not([data-theme]) .megap{box-shadow:0 24px 60px rgba(14,20,36,.18)}}",
)
FILTER_LABELS = {"fr": ("Filtrer par jeu", "Tous les jeux"), "en": ("Filter by game", "All games"),
                 "es": ("Filtrar por juego", "Todos los juegos"), "de": ("Nach Spiel filtern", "Alle Spiele"),
                 "pt-BR": ("Filtrar por jogo", "Todos os jogos")}
_ITEMS = ".infos li,.matchs li,.cards .card,.posts li"  # ce que le filtre cache : les éléments d'une liste, un jeu à la fois
FILTER_STYLE = (
    ".filter .f{display:block;height:0;scroll-margin-top:96px}",
    ".chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px}",
    ".chips a{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:999px;background:var(--surface);"
    "border:1px solid var(--border);color:var(--text);text-decoration:none;font-weight:600;font-size:15px}",
    ".chips a:hover{border-color:var(--or)}",
    'main:not(:has(.f:target)) .chips a[href="#f-all"],main:has(#f-all:target) .chips a[href="#f-all"]'
    "{background:var(--or);border-color:var(--or);color:var(--on-or)}",
    *(f'main:has(#f-{game}:target) :is({_ITEMS}):not([data-game="{game}"]){{display:none}}' for game in GAMES),
    *(f'main:has(#f-{game}:target) .chips a[href="#f-{game}"]{{background:var(--or);border-color:var(--or);color:var(--on-or)}}'
      for game in GAMES),
)
MENU_STYLE = MENU_STYLE + MEGA_STYLE  # le menu des jeux a besoin de GAMES, défini après MENU_STYLE : on l'ajoute ici, avant tout lecteur
CHROME_STYLE = "\n".join([*MENU_STYLE, *FOOTER_STYLE, *FILTER_STYLE])  # les pages sans autre style du Blog (News) ; BLOG_STYLE les contient aussi
CRUMBS = re.compile(r'<nav class="crumbs"[^>]*>(.*?)</nav>', re.S)


def read_game_names(root: Path) -> dict[str, dict[str, str]]:
    """{langue: {jeu: nom}} : le nom affiché de chaque jeu, lu (et décodé) dans le <span> du fil d'Ariane de sa page.

    Un jeu sans page dans une langue, ou dont la page n'a pas de fil d'Ariane, en est absent : les boutons affichent son identifiant."""
    names: dict[str, dict[str, str]] = {}
    for lang, folder in GAME_DIRS.items():
        names[lang] = {}
        for path in sorted((root / folder).glob("*.html")):
            crumbs = CRUMBS.search(path.read_bytes().decode("utf-8"))
            name = re.search(r"<span>(.*?)</span>", crumbs.group(1), re.S) if crumbs else None
            if name is not None:
                names[lang][path.stem] = html.unescape(name.group(1))
    return names


def render_filter(lang: str, games: list[str], names: dict[str, str]) -> str:
    """Les ancres et les boutons du filtre pour les jeux donnés (dans l'ordre de GAMES) ; rien s'il y a moins de deux jeux."""
    games = [game for game in GAMES if game in games]
    if len(games) < 2:
        return ""
    label, everyone = FILTER_LABELS[lang]
    anchors = "".join(f'<span class="f" id="f-{game}"></span>' for game in ["all", *games])
    chips = "".join(f'<a href="#f-{game}">{html.escape(names.get(game, game) if game != "all" else everyone)}</a>' for game in ["all", *games])
    return f'<div class="filter">{anchors}<nav class="chips" aria-label="{label}">{chips}</nav></div>'


FOOTER = re.compile(r"<footer>.*?</footer>", re.S)
THEME_DIV = re.compile(r'<div class="theme" id="theme" role="group"[^>]*>.*?</div>', re.S)
LANGS_MENU = re.compile(r'<details class="lang langs">.*?</details>', re.S)
LANG_LINK = re.compile(r'<a href="([^"]*)" hreflang="([^"]*)" lang="[^"]*"( aria-current="page")?>')
FOOTER_FLAG = re.compile(r'<li class="fl"><a href="[^"]*" hreflang="([^"]*)" lang="([^"]*)"(?: aria-current="page")?>')
SITE_ATTR = re.compile(r'(\s(?:href|src)=")([^"]*)(")')
VISIT_PATH = re.compile(r"(visite\?p=/)[A-Za-z0-9/_-]+")


def with_css(page: str, css: str) -> str:
    """`css` (une règle par ligne) avant le premier </style> du modèle, avec les fins de ligne de la page, une seule fois : seules les
    règles que la page n'a pas encore s'ajoutent (un modèle qui porte déjà le menu du site, menu_partout.py, ne reçoit pas ses règles
    en double)."""
    end = eol(page)
    missing = [rule for rule in css.split("\n") if rule not in page]
    return page if not missing else page.replace("</style>", end + end.join(missing) + end + "</style>", 1)


def with_script(page: str, script: str, digest: str, what: str) -> str:
    """Un script inline dans une page, une seule fois : l'empreinte 'sha256-<digest>' à la fin de script-src, et <script> sur sa propre
    ligne juste avant </body>. Tout le reste de la CSP reste identique octet pour octet.

    Lève ChromeError sans balise de CSP, sans script-src (l'ajouter changerait ce que default-src autorise) ou sans </body>.
    """
    meta = CSP_META.search(page)
    if meta is None:
        raise ChromeError([f"balise Content-Security-Policy introuvable, impossible d'autoriser le script {what}"])
    policy, token = meta.group(1), f"'sha256-{digest}'"
    scripts = SCRIPT_SRC.search(policy)
    if scripts is None:
        raise ChromeError([f"CSP sans script-src, impossible d'autoriser le script {what}"])
    if token not in scripts.group(0).split():
        kept = scripts.group(0).rstrip()
        policy = policy[:scripts.start()] + f"{kept} {token}" + policy[scripts.start() + len(kept):]
    page = page[:meta.start(1)] + policy + page[meta.end(1):]
    tag = f"<script>{script}</script>"
    if tag in page:
        return page
    body = page.rfind("</body>")
    if body < 0:
        raise ChromeError([f"</body> introuvable, impossible d'ajouter le script {what}"])
    return page[:body] + tag + eol(page) + page[body:]


MENU_SCRIPT = re.compile(r"<script>(\(function\(\)\{var d=document\.documentElement,k='esportly-theme'.*?)</script>", re.S)


def swap_menu_script(page: str) -> str:
    """Le script du menu d'une page déjà publiée remplacé par la version du jour, son ancienne empreinte retirée de la CSP et la
    nouvelle ajoutée. Sans cela, une page gardait son vieux script (with_script n'ajoute que ce qui manque, il ne remplace pas)
    et les ajouts du menu — la recherche d'équipe, par exemple — ne tournaient jamais sur les pages déjà faites.

    Une page sans script de menu, ou déjà à jour, n'est pas touchée."""
    if CSP_META.search(page) is None:
        return page  # page sans CSP (un modèle de test, un fragment) : on n'y greffe pas de script
    found = MENU_SCRIPT.search(page)
    if found is None:  # page fabriquée sans le script du menu : le menu en a besoin (burger, thème, recherche d'équipe)
        return with_script(page, MENU_JS, MENU_HASH, "du menu du site")
    if found.group(1) == MENU_JS:
        return page
    old = base64.b64encode(hashlib.sha256(found.group(1).encode("utf-8")).digest()).decode()
    page = page[:found.start(1)] + MENU_JS + page[found.end(1):]
    meta = CSP_META.search(page)
    if meta is not None:
        policy = meta.group(1).replace(f" 'sha256-{old}'", "")
        page = page[:meta.start(1)] + policy + page[meta.end(1):]
    return with_script(page, MENU_JS, MENU_HASH, "du menu du site")


def theme_switch(lang: str) -> str:
    """Le sélecteur de thème : flottant en bas à droite, discret, après le pied de page. Caché (hidden) tant que MENU_JS ne l'a pas
    montré, donc absent sans JavaScript."""
    group, *names = MENU[lang]["theme"]
    buttons = "".join(f'<button type="button" data-theme-set="{key}" aria-pressed="false" aria-label="{name}" title="{name}">{THEME_ICONS[key]}</button>'
                      for key, name in zip(THEME_ICONS, names))
    return f'<div class="theme" id="theme" role="group" aria-label="{group}" hidden>{buttons}</div>'


def render_menu(lang: str, path: str, brand: str, langs: str, *, home: str, news: str, hub: str, label: str, current: str, live: str,
                up: str = "") -> str:
    """L'en-tête d'une page fabriquée avec le menu des accueils, sur une ligne : la marque, la barre (sections de l'accueil, page News,
    page du Blog, page Live, menu de langue, sélecteur de thème), le bouton de la bêta, puis le menu burger (mêmes liens, bouton de la
    bêta, langues).

    `up` : ce qui précède un chemin de la racine vu de la page (« ../../ »), pour les liens du panneau des jeux ;
    `home` : lien de l'accueil de la langue vu de la page (« ../fr.html », « ./ »), pour les ancres ; `news` et `hub` : adresses de la
    page News et de l'accueil du Blog vues de la page ; `live` : l'adresse de la page Live (LIVE_PAGES) vue de la page ; `label` : le mot
    « Blog » de la langue ; `current` : « news », « hub » ou « live », celui des trois liens marqué aria-current="page". `path` : chemin publié de la page (« blog-fr/valorant »), pour le paramètre p= du bouton de la
    bêta, comme le compteur de visites ; `brand` et `langs` : la marque et le <details class="lang langs"> de la page modèle, gardés tels
    quels (leurs liens de langue mènent déjà aux pages équivalentes). Le panneau reprend ces liens de langue, le drapeau anglais avec
    son propre identifiant (gb-m), comme sur les accueils. `langs` peut aussi être le simple lien de langue des pages d'équipes
    (<a class="lang" …>English</a>), repris tel quel dans la barre et le panneau, ou vide (page sans autre langue, comme 404.html :
    pas de rangée de langues dans le panneau).
    """
    menu, here = MENU[lang], ' aria-current="page"'
    tail = (f'<a href="{news}"{here if current == "news" else ""}>{menu["news"]}</a><a href="{hub}"{here if current == "hub" else ""}>{label}</a>'
            f'<a class="live" href="{live}"{here if current == "live" else ""}>{LIVE_LABEL}</a>')
    # « Jeux » n'est plus une ancre de l'accueil mais le panneau des 14 jeux (games_menu / games_panel) ; le reste ne change pas.
    bar = (games_menu(lang, up, home) + teams_menu(lang, up)
           + "".join(f'<a href="{home}#{anchor}">{text}</a>' for anchor, text in menu["bar"][2:]) + tail)
    panel = (games_panel(lang, up) + teams_panel(lang, up)
             + "".join(f'<a href="{home}#{anchor}">{text}</a>' for anchor, text in menu["panel"][1:]) + tail)
    beta = f"{VISIT}?p=/{path}&amp;go=testflight"
    links = re.findall(r"<li>(<a\b.*?</a>)</li>", langs, re.S) or re.findall(r"<a\b.*?</a>", langs, re.S)
    flags = "".join(links).replace('id="gb-h"', 'id="gb-m"').replace("url(#gb-h)", "url(#gb-m)")
    langsm = f'<div class="langsm">{flags}</div>' if flags else ""
    return (f'<header><div class="wrap">{brand}<nav aria-label="{menu["nav"]}">{bar}{langs}</nav>'
            f'<a class="soon" href="{beta}">{menu["beta"]}</a><details class="menu"><summary aria-label="Menu">{MENU_ICONS}</summary>'
            f'<div class="panel" role="navigation" aria-label="Menu">{panel}<a class="soonm" href="{beta}">{menu["beta"]}</a>'
            f'{langsm}</div></details></div></header>')


def render_footer(home_page: str, home_name: str, prefix: str, path: str, home: str, langs: str) -> str:
    """Le pied de page de l'accueil (`home_page`, le texte du fichier `home_name`), prêt pour une page qui n'est pas à la racine.

    Les adresses relatives se lisent depuis la page : `prefix` (« ../ » dans un dossier, « » à la racine) s'y ajoute ; une ancre
    (#jeux) mène à l'accueil (`home`, comme dans l'en-tête) ; les adresses absolues et mailto: restent telles quelles. Les drapeaux
    des langues mènent à la page équivalente (celle du menu de langue `langs` de la page) et la langue courante porte aria-current.
    Le chemin du bouton de la bêta (p=) devient `path`. Lève ChromeError sans <footer> dans l'accueil, ou sans une langue du menu.
    """
    found = FOOTER.search(home_page)
    if found is None:
        raise ChromeError([f"{home_name} : pied de page (<footer>) introuvable, impossible de le reprendre sur les autres pages"])
    equivalent = {hreflang: (href, current) for href, hreflang, current in LANG_LINK.findall(langs)}

    def address(match: re.Match) -> str:
        value = match.group(2)
        if value.startswith(("https:", "http:", "mailto:", "data:")):
            return match.group(0)
        if value.startswith("#"):
            value = home + value
        else:
            value = (prefix or "./") if value == "./" else prefix + value
        return match.group(1) + value + match.group(3)

    def flag(match: re.Match) -> str:
        hreflang = match.group(1)
        if hreflang not in equivalent:
            raise ChromeError([f"menu de langue sans la langue {hreflang}, impossible d'écrire le pied de page du site"])
        href, current = equivalent[hreflang]
        return f'<li class="fl"><a href="{href}" hreflang="{hreflang}" lang="{match.group(2)}"{current}>'

    footer = FOOTER_FLAG.sub(flag, SITE_ATTR.sub(address, found.group(0)))
    return VISIT_PATH.sub(lambda match: match.group(1) + path, footer)


def with_chrome(page: str, lang: str, home_page: str, home_name: str, prefix: str, path: str, *, home: str, news: str, hub: str,
                label: str, current: str, live: str, css: str = CHROME_STYLE) -> str:
    """Une page habillée du menu et du pied de page des accueils : `css` ajouté (une fois), l'en-tête du modèle remplacé par celui de
    render_menu (la marque et le menu de langue du modèle y sont gardés), le script du menu (MENU_JS, avec son empreinte dans la CSP),
    puis le pied de page du modèle remplacé par celui de l'accueil (render_footer ; `home_name` : le fichier de l'accueil, pour les
    messages). Une page refabriquée ne change pas.

    Lève ChromeError sans <header> contenant la marque (a.brand) et le menu de langue (details.lang.langs), sans <footer>, ou si
    render_footer lève.
    """
    header = HEADER.search(page)
    brand = re.search(r'<a class="brand".*?</a>', header.group(0), re.S) if header else None
    langs = LANGS_MENU.search(header.group(0)) if header else None
    if brand is None or langs is None:
        raise ChromeError(["en-tête (<header> avec la marque et le menu de langue) introuvable, impossible d'ajouter le menu du site"])
    menu = render_menu(lang, path, brand.group(0), langs.group(0), home=home, news=news, hub=hub, label=label, current=current,
                       live=live, up=prefix)
    page = with_script(page[:header.start()] + menu + page[header.end():], MENU_JS, MENU_HASH, "du menu du site")
    footer = FOOTER.search(page)
    if footer is None:
        raise ChromeError(["pied de page (<footer>) introuvable, impossible d'ajouter celui du site"])
    page = THEME_DIV.sub("", page)  # une page refabriquée : le sélecteur de thème est reposé, pas doublé
    footer = FOOTER.search(page)
    page = (page[:footer.start()] + render_footer(home_page, home_name, prefix, path, home, langs.group(0)) + theme_switch(lang)
            + page[footer.end():])
    return with_css(page, css)
