"""Le menu du site dans l'en-tête de toutes les pages publiques, dans la langue de chaque page.

Les accueils, les pages News, Blog et Live portent le menu du site (site_chrome.render_menu : la barre au-dessus de 1150 px, le menu
burger en dessous, le bouton de la bêta). Les autres pages (équipes, jeux, événements, matchs de la semaine, nouveautés, presse,
pages légales, confirmations, 404) n'avaient qu'une marque et, parfois, un sélecteur de langue. Ce script leur met le même en-tête :

- une page avec <header> (marque a.brand, menu de langue details.lang.langs ou simple lien a.lang) : l'en-tête est remplacé par celui
  de render_menu, qui garde la marque et le sélecteur de langue tels quels ; les règles du menu (MENU_STYLE) s'ajoutent au <style> ;
- une page sans <header> (pages légales et de confirmation, au texte simple) : un en-tête avec la marque est posé après <body>, le
  texte passe dans <main class="legal"> et la page reçoit, en plus, les variables de couleur du site (clair par défaut, sombre selon
  le système, comme ces pages le faisaient déjà) et le style de la marque (LEGAL_STYLE).

Aucun script : le menu burger est un <details>, il s'ouvre sans JavaScript et la CSP de la page ne change pas. Les widgets (cadres
intégrés ailleurs), les pages de renvoi (http-equiv="refresh", match.html, tv-equipes.html) et les pages sans langue connue sont
laissés tels quels. Le script est rejouable sans effet : une page qui a déjà le menu (details.menu) n'est pas touchée. Il passe dans
les tâches planifiées (matchs.yml, bascule.yml) après les scripts qui fabriquent des pages à partir de modèles ; ceux-ci repartent de
modèles qui ont le menu (nouveautes.html…) ou remplacent un bloc de la page (prochains matchs), si bien que l'en-tête survit.

Lancé à la main : python3 .github/scripts/menu_partout.py   (ajouter --check pour seulement lister les pages à mettre à jour).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import actualites as an  # noqa: E402
import site_chrome as sc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".github", ".claude", ".superpowers", "docs", "news", "blog-src", "node_modules", ".wrangler", "worker", "widget"}
# Pages que ce script ne touche pas : les renvois vers l'app (sans en-tête ni menu) et les cinq accueils, qui portent leur menu
# à la main (mega_accueils.py leur pose le panneau des jeux ; le menu générique effacerait leur en-tête propre).
SKIP_PAGES = {"match.html", "tv-equipes.html", "index.html", "fr.html", "es.html", "de.html", "pt.html"}
LANG = re.compile(r'<html[^>]*\blang="([A-Za-z-]+)"')
BODY = re.compile(r"<body[^>]*>")
BRAND = re.compile(r'<a class="brand" href="([^"]*)".*?</a>', re.S)
LANG_LINK = re.compile(r'<a class="lang" [^>]*>.*?</a>', re.S)
VISIT_PATH = re.compile(r"visite\?p=/([A-Za-z0-9/_-]*)")
# Où finit le texte d'une page sans <header> : avant le compteur de visites, la mesure d'audience, le QR code ou la fin du corps.
TAIL = ('<img src="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite', '<script src="/analytics.js"',
        '<link rel="stylesheet" href="/qr-flottant.css">', "</body>")
# Sans MENU_JS, rien ne mesure l'en-tête (--hh) : le panneau du burger prend la hauteur réelle de l'en-tête de ces pages, 72 px
# (min-height de leur .wrap) plus la bordure, ou 7vw plus la bordure quand clamp(64px,7vw,88px) dépasse 72 px (au-dessus de 1028 px).
PANEL_STYLE = "\n".join((
    ".menu .panel{height:calc(100dvh - 73px)}",
    "@media (min-width:1029px){.menu .panel{height:calc(100dvh - 7vw - 1px)}}",
))
MENU_STYLE = "\n".join((*sc.MENU_STYLE, PANEL_STYLE))
# Pages sans <header> : les variables des pages modèles (clair par défaut, sombre selon le système, comme leur ancien style), la marque
# (règles des pages modèles), l'en-tête et le texte dans sa colonne de 760 px (celle de leur ancien <body>).
LEGAL_STYLE = "\n".join((
    ":root{--nuit:#F6F7FB;--surface:#FFFFFF;--raised:#ECEFF6;--border:#D5DAE6;--text:#0E1424;--soft:#3A4250;--muted:#485060;--or:#FFC53D;"
    "--on-or:#1A1300;--display:'Rajdhani','Arial Narrow',sans-serif}",
    "@media (prefers-color-scheme:dark){:root{--nuit:#0A0E1A;--surface:#141A2B;--raised:#1D2438;--border:#2C3550;--text:#F4F6FF;"
    "--soft:#C9CEDA;--muted:#A8B1C8}}",
    "@font-face{font-family:'Rajdhani';src:url({prefix}fonts/Rajdhani-Bold.woff2) format('woff2');font-weight:700;font-display:swap}",
    "body{max-width:none;padding:0;background:var(--nuit);color:var(--text)}",
    ".legal{max-width:760px;margin:0 auto;padding:24px}",
    ".wrap{margin:0 auto}",
    "header{border-bottom:1px solid var(--raised)}",
    "header .wrap{display:flex;align-items:center;min-height:72px}",
    ".brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text);font:700 26px var(--display)}",
    ".brand i{color:var(--or);font-style:normal}",
    "@media (prefers-color-scheme:light){.brand i{color:#8A5D00}}",
))


def language(page: str) -> str | None:
    """La langue du menu pour la page (« pt » vaut « pt-BR ») ; None si la page n'en déclare pas une du site."""
    found = LANG.search(page)
    if found is None:
        return None
    lang = found.group(1)
    lang = "pt-BR" if lang.lower().startswith("pt") else lang.lower()
    return lang if lang in sc.MENU else None


def prefix_of(rel: str, page: str) -> str:
    """Ce qui précède une adresse de la racine vue de la page : « ../ » par dossier, ou « / » si la marque est déjà absolue (404.html,
    servie à n'importe quelle adresse)."""
    brand = BRAND.search(page)
    if brand is not None and brand.group(1).startswith("/"):
        return "/"
    return "../" * (rel.count("/"))


def home_of(lang: str, prefix: str) -> str:
    """L'accueil de la langue vu de la page : « fr.html », « ../../pt.html », « ./ » ou « ../ » pour l'anglais (index.html), « / » en absolu."""
    return sc.home_link(lang, prefix)


def brand_of(home: str, prefix: str) -> str:
    """La marque des pages modèles, pour une page qui n'en avait pas."""
    return f'<a class="brand" href="{home}"><img src="{prefix}embleme.svg" alt="" width="36" height="36"><span><i>e</i>Sportly</span></a>'


CURRENT = {"news": "news", "hub": "hub", "live": "live"}
SOON = re.compile(r'<a class="soon" href="([^"]*)">([^<]*)</a>')
SOONM = re.compile(r'<a class="soonm" href="([^"]*)">([^<]*)</a>')


def keep_beta(menu: str, header: str) -> str:
    """Garde le bouton de la bêta tel qu'il est déjà sur la page. Après la sortie sur l'App Store, bascule_appstore.py a remplacé
    son adresse et son libellé : refabriquer l'en-tête les remettrait à la bêta, et le site se contredirait d'une page à l'autre.
    Les deux boutons (barre et menu burger) sont traités, et un en-tête qui n'en a pas laisse le menu tel quel."""
    for pattern in (SOON, SOONM):
        old = pattern.search(header)
        if old is not None:
            menu = pattern.sub(lambda m: m.group(0).replace(m.group(1), old.group(1)).replace(f">{m.group(2)}<", f">{old.group(2)}<"),
                               menu, count=1)
    return menu


def current_of(header: str, links: dict) -> str:
    """Celui des trois liens (News, Blog, Live) que l'en-tête marque déjà comme la page courante, « » sinon. Sans cela, refabriquer
    l'en-tête d'une page du Blog, des News ou du Live lui ferait perdre son aria-current, posé par le script qui l'a fabriquée."""
    for key in CURRENT:
        if re.search(r'<a[^>]*href="' + re.escape(links[key]) + r'"[^>]*aria-current="page"', header):
            return key
    return ""


def render(page: str, rel: str) -> str:
    """La page `rel` (chemin depuis la racine, « equipes/t1.html ») avec le menu du site ; inchangée si c'est une page de renvoi,
    un accueil, une page sans corps ou sans langue du site.

    Une page qui a déjà le menu le reçoit à nouveau : refabriquer l'en-tête depuis sa marque et son menu de langue redonne le même
    texte quand rien n'a changé, et met à jour les pages fabriquées une seule fois (équipes, pages légales) quand le menu évolue."""
    lang = language(page)
    if ('http-equiv="refresh"' in page or lang is None or "</body>" not in page
            or rel.rsplit("/", 1)[-1] in SKIP_PAGES):
        return page
    prefix = prefix_of(rel, page)
    found = VISIT_PATH.search(page)
    path = found.group(1) if found else rel[:-len(".html")]
    links = dict(news=prefix + an.PAGES[lang], hub=prefix + sc.HUBS[lang], live=prefix + sc.LIVE_PAGES[lang], label=sc.BLOG_LABEL, current="")
    header = sc.HEADER.search(page)
    end = sc.eol(page)
    if header is not None:
        links["current"] = current_of(header.group(0), links)  # une page fabriquée marque déjà News, Blog ou Live : on le garde
        brand = BRAND.search(header.group(0))
        langs = sc.LANGS_MENU.search(header.group(0)) or LANG_LINK.search(header.group(0))
        home = brand.group(1) if brand else home_of(lang, prefix)
        menu = sc.render_menu(lang, path, brand.group(0) if brand else brand_of(home, prefix), langs.group(0) if langs else "",
                              home=home, up=prefix, **links)
        page = page[:header.start()] + keep_beta(menu, header.group(0)) + page[header.end():]
        return sc.swap_menu_script(sc.with_css(page, MENU_STYLE))
    body = BODY.search(page)
    if body is None:
        return page
    home = home_of(lang, prefix)
    menu = sc.render_menu(lang, path, brand_of(home, prefix), "", home=home, up=prefix, **links)
    rest = page[body.end():]
    if re.match(r"\s*<main>", rest):
        rest = rest.replace("<main>", '<main class="legal">', 1)
    else:
        stops = [rest.find(stop) for stop in TAIL if stop in rest]
        stop = min(stops)
        rest = rest[:stop].rstrip() + end + "</main>" + end + rest[stop:]
        rest = end + '<main class="legal">' + rest
    page = page[:body.end()] + end + menu + rest
    # Le script du menu dès la première pose : sans lui, la page le recevrait au passage suivant et ne serait pas rejouable.
    return sc.swap_menu_script(sc.with_css(page, LEGAL_STYLE.replace("{prefix}", prefix) + "\n" + MENU_STYLE))


def pages(root: Path = ROOT):
    for path in sorted(root.rglob("*.html")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def main(argv: list[str], root: Path = ROOT) -> int:
    changed = []
    for path in pages(root):
        rel = path.relative_to(root).as_posix()
        before = path.read_bytes().decode("utf-8")
        after = render(before, rel)
        if after != before:
            changed.append(rel)
            if "--check" not in argv:
                path.write_text(after, encoding="utf-8", newline="")
    print(f"{len(changed)} page(s) {'à mettre à jour' if '--check' in argv else 'mise(s) à jour'}")
    return 1 if changed and "--check" in argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
