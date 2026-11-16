"""Tests de menu_partout.py : le menu du site arrive une seule fois dans l'en-tête de chaque page publique, dans sa langue, en gardant
la marque et le sélecteur de langue de la page, sans script ni changement de CSP, sans toucher aux redirections ni aux widgets."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import actualites as an  # noqa: E402
import menu_partout as mp  # noqa: E402
import site_chrome as sc  # noqa: E402

REAL = Path(__file__).resolve().parents[2]
CSP = ('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'sha256-abc=\' \'self\'; '
       'style-src \'self\' \'unsafe-inline\'; base-uri \'none\'">')
HEAD = CSP + '<title>Une page – eSportly</title><meta name="description" content="La description.">'
BRAND = '<a class="brand" href="../fr.html"><img src="../embleme.svg" alt="" width="36" height="36"><span><i>e</i>Sportly</span></a>'
LANGS = ('<details class="lang langs"><summary aria-label="Langue : Français"><svg class="flag" viewBox="0 0 3 2"><path d="M0 0"/></svg>'
         '<span>FR</span></summary><ul><li><a href="valorant.html" hreflang="fr" lang="fr" aria-current="page">Français</a></li>'
         '<li><a href="../games/valorant.html" hreflang="en" lang="en"><svg class="flag"><clipPath id="gb-h"><path d="M0 0"/></clipPath>'
         '<path clip-path="url(#gb-h)"/></svg>English</a></li></ul></details>')
LANG_LINK = '<a class="lang" href="../teams/t1.html" hreflang="en">English</a>'
VISIT = '<img src="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/{p}" alt="" width="1" height="1">'
TAIL = '<script src="/analytics.js" defer></script>{eol}<link rel="stylesheet" href="/qr-flottant.css"><div class="qrfix"></div>'


def model(lang: str = "fr", header: str = BRAND + LANGS, p: str = "jeux/valorant", eol: str = "\n", head: str = HEAD) -> str:
    """Une page modèle (jeu, équipe, événement…) : en-tête avec la marque et un sélecteur de langue, un style, le compteur de visites."""
    lines = ["<!doctype html>", f'<html lang="{lang}">', f"<head>{head}", "<style>", ":root{--nuit:#0A0E1A}", ".wrap{max-width:960px}",
             "header .wrap{display:flex}", "</style></head>", "<body>", f'<header><div class="wrap">{header}</div></header>',
             '<main class="wrap"><h1>Valorant</h1></main>', '<footer><div class="wrap">eSportly</div></footer>', VISIT.format(p=p),
             TAIL.format(eol=eol), "</body>", "</html>", ""]
    return eol.join(lines)


def legal(lang: str = "fr", p: str = "mentions-legales", eol: str = "\n", with_main: bool = False, head: str = HEAD) -> str:
    """Une page légale ou de confirmation : pas d'en-tête, le texte directement dans <body> (ou dans un <main> nu)."""
    text = ["<h1>Mentions légales<br><span class=\"muted\">eSportly</span></h1>", "<p class=\"muted\">Dernière mise à jour</p>", "",
            "<h2>Éditeur</h2>", "<p>ProtoJo Digital. <a href=\"fr.html\">Accueil</a></p>"]
    if with_main:
        text = ["<main>", *text, "</main>"]
    lines = ["<!doctype html>", f'<html lang="{lang}">', f"<head>{head}", "<style>", "  :root { color-scheme: light dark; }",
             "  body { max-width: 760px; margin: 0 auto; padding: 24px; }", "</style>", "</head>", "<body>", *text, VISIT.format(p=p),
             TAIL.format(eol=eol), "</body>", "</html>", ""]
    return eol.join(lines)


def header_of(page: str) -> str:
    found = re.findall(r"<header>.*?</header>", page, re.S)
    assert len(found) == 1, found
    return found[0]


class MenuPartout(unittest.TestCase):
    def test_page_modele_avec_menu_de_langue(self):
        """Une page de jeu : l'en-tête devient celui des pages Blog (marque et menu de langue gardés), les règles du menu s'ajoutent au
        style, la CSP, le title et la description ne bougent pas, aucun script n'arrive."""
        before = model("es", p="juegos/valorant")
        after = mp.render(before, "juegos/valorant.html")
        header = header_of(after)
        self.assertEqual(after.count("<header>"), 1)
        self.assertIn('<details class="menu"><summary aria-label="Menu">', header)
        # « Juegos » n'est plus une ancre : c'est le panneau des jeux (mega menu), suivi des autres ancres de l'accueil.
        self.assertIn(f'<nav aria-label="{sc.MENU["es"]["nav"]}"><details class="mega"><summary>Juegos', header)
        self.assertIn('<a href="../es/juegos/valorant.html"><img src="../logos-jeux/valorant.png" alt="Valorant" loading="lazy"></a>', header)
        self.assertIn('<details class="mega team">', header)  # « Équipes » est un panneau, plus une ancre de l'accueil
        self.assertNotIn('#equipes"', header)
        self.assertIn('<a href="../es/noticias.html">Noticias</a><a href="../es/blog.html">Blog</a><a class="live" href="../es/live.html">Live</a>', header)
        self.assertNotIn('aria-current="page">Live', header)  # aucun des trois liens n'est la page courante
        self.assertIn(BRAND, header)  # la marque de la page, telle quelle
        self.assertIn(LANGS + "</nav>", header)  # le menu de langue de la page, tel quel, à la fin de la barre
        self.assertIn(f'<a class="soon" href="{sc.VISIT}?p=/juegos/valorant&amp;go=testflight">Únete a la beta</a>', header)
        self.assertIn('<div class="langsm"><a href="valorant.html" hreflang="fr" lang="fr" aria-current="page">Français</a>'
                      '<a href="../games/valorant.html" hreflang="en" lang="en"><svg class="flag"><clipPath id="gb-m">', header)
        self.assertEqual(header.count("gb-h"), 2)  # le drapeau de la barre garde son identifiant, celui du panneau a le sien
        for rule in (*sc.MENU_STYLE, *mp.PANEL_STYLE.split("\n")):
            self.assertEqual(after.count(rule), 1, rule)
        self.assertTrue(after.index(sc.MENU_STYLE[0]) < after.index(mp.PANEL_STYLE) < after.index("</style>"))  # le panneau après le menu
        # La CSP ne gagne que l'empreinte du script du menu (que la page reçoit) ; titre et description restent intacts.
        self.assertIn(HEAD.replace("'sha256-abc=' 'self';", f"'sha256-abc=' 'self' 'sha256-{sc.MENU_HASH}';", 1), after)
        self.assertEqual(after.count("<script"), before.count("<script") + 1)
        # Après l'en-tête, seule l'arrivée du script du menu change la page (juste avant </body>).
        self.assertEqual(after.split("</header>", 1)[1].replace(f"<script>{sc.MENU_JS}</script>\n", ""),
                         before.split("</header>", 1)[1])

    def test_page_equipe_avec_lien_de_langue(self):
        """Une page d'équipe n'a qu'un lien « English » : il finit la barre et devient la rangée de langues du panneau."""
        after = mp.render(model("fr", header=BRAND + LANG_LINK, p="equipes/t1"), "equipes/t1.html")
        header = header_of(after)
        self.assertIn(f'<a class="live" href="../fr/live.html">Live</a>{LANG_LINK}</nav>', header)
        self.assertIn(f'<div class="langsm">{LANG_LINK}</div></div></details>', header)
        self.assertIn('<a class="soon" href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/equipes/t1&amp;go=testflight">Rejoindre la bêta</a>', header)
        self.assertIn('<nav aria-label="Sections de la page"><details class="mega"><summary>Jeux', header)

    def test_page_sans_autre_langue_et_marque_absolue(self):
        """404.html : marque en « / » (la page est servie à n'importe quelle adresse), pas de sélecteur de langue : liens absolus, pas de
        rangée de langues dans le panneau."""
        brand = '<a class="brand" href="/"><img src="/embleme.svg" alt="" width="36" height="36"><span><i>e</i>Sportly</span></a>'
        after = mp.render(model("en", header=brand, p="404"), "404.html")
        header = header_of(after)
        self.assertIn('<nav aria-label="Sections"><details class="mega"><summary>Games', header)
        self.assertIn('<a href="/games/valorant.html">', header)  # marque absolue : les liens des jeux le sont aussi
        self.assertIn('<a href="/news.html">News</a><a href="/blog.html">Blog</a><a class="live" href="/live.html">Live</a></nav>', header)
        self.assertNotIn("langsm", header)
        self.assertIn("p=/404&amp;go=testflight", header)

    def test_page_sans_en_tete(self):
        """Une page légale : un en-tête avec la marque après <body>, le texte dans <main class="legal"> jusqu'au compteur de visites,
        les variables de couleur, la police et le style de la marque ajoutés une fois, title et description intacts."""
        before = legal("fr")
        after = mp.render(before, "mentions-legales.html")
        header = header_of(after)
        self.assertTrue(after.startswith("<!doctype html>\n<html lang=\"fr\">"))
        self.assertIn('<body>\n<header><div class="wrap"><a class="brand" href="fr.html"><img src="embleme.svg" alt="" width="36" height="36">'
                      '<span><i>e</i>Sportly</span></a><nav aria-label="Sections de la page"><details class="mega"><summary>Jeux', after)
        self.assertIn('<a href="fr/actualites.html">Actualités</a><a href="fr/blog.html">Blog</a><a class="live" href="fr/live.html">Live</a></nav>', header)
        self.assertIn("p=/mentions-legales&amp;go=testflight", header)
        self.assertIn('</header>\n<main class="legal">\n<h1>Mentions légales', after)
        self.assertIn('<p>ProtoJo Digital. <a href="fr.html">Accueil</a></p>\n</main>\n<img src="https://lmavqchwevcvvneblqld', after)
        self.assertEqual(after.count("<main"), 1)
        for rule in (*mp.LEGAL_STYLE.replace("{prefix}", "").split("\n"), *sc.MENU_STYLE):
            self.assertEqual(after.count(rule), 1, rule)
        self.assertIn("url(fonts/Rajdhani-Bold.woff2)", after)
        self.assertIn("  body { max-width: 760px; margin: 0 auto; padding: 24px; }", after)  # l'ancien style reste, le nouveau le corrige après
        self.assertTrue(after.index("body { max-width: 760px") < after.index("body{max-width:none;padding:0"))
        self.assertIn(HEAD.replace("'sha256-abc=' 'self';", f"'sha256-abc=' 'self' 'sha256-{sc.MENU_HASH}';", 1), after)
        self.assertEqual(after.count("<script"), before.count("<script") + 1)

    def test_page_sans_en_tete_avec_main_et_en_anglais(self):
        after = mp.render(legal("en", p="privacy", with_main=True), "privacy.html")
        self.assertIn('</header>\n<main class="legal">\n<h1>', after)
        self.assertEqual(after.count("</main>"), 1)
        self.assertIn('<a class="brand" href="./"><img src="embleme.svg"', after)
        self.assertIn('<nav aria-label="Sections"><details class="mega"><summary>Games', after)
        self.assertIn('<a href="news.html">News</a><a href="blog.html">Blog</a><a class="live" href="live.html">Live</a></nav>', after)

    def test_langue_de_la_page(self):
        for lang, key in (("fr", "fr"), ("en", "en"), ("es", "es"), ("de", "de"), ("pt-BR", "pt-BR"), ("pt", "pt-BR"), ("EN", "en")):
            with self.subTest(lang=lang):
                header = header_of(mp.render(model(lang), "jeux/valorant.html"))
                self.assertIn(f'<nav aria-label="{sc.MENU[key]["nav"]}">', header)
                self.assertIn(f'>{sc.MENU[key]["beta"]}</a>', header)
                self.assertIn(f'<a href="../{an.PAGES[key]}">{sc.MENU[key]["news"]}</a>', header)
                self.assertIn(f'<a class="live" href="../{sc.LIVE_PAGES[key]}">Live</a>', header)

    def test_rejouable_et_fins_de_ligne(self):
        for build in (model, legal):
            for eol in ("\n", "\r\n"):
                with self.subTest(page=build.__name__, eol=repr(eol)):
                    once = mp.render(build(eol=eol), "x.html")
                    self.assertNotEqual(once, build(eol=eol))
                    self.assertEqual(mp.render(once, "x.html"), once)
                    self.assertEqual(once.count("\n") - once.count("\r\n") if eol == "\r\n" else once.count("\r"), 0)

    def test_pages_laissees_telles_quelles(self):
        redirect = model(head=HEAD + '<meta http-equiv="refresh" content="0; url=/">')
        self.assertEqual(mp.render(redirect, "en.html"), redirect)
        for name in mp.SKIP_PAGES:
            self.assertEqual(mp.render(legal(), name), legal())
        self.assertEqual(mp.render(model("ja"), "jeux/x.html"), model("ja"))  # langue inconnue du menu
        fragment = '<html lang="fr"><p>fragment</p></html>'
        self.assertEqual(mp.render(fragment, "x.html"), fragment)
        no_lang = model().replace(' lang="fr"', "")
        self.assertEqual(mp.render(no_lang, "x.html"), no_lang)

    def test_widgets_et_dossiers_techniques_ignores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.html", "equipes/b.html", "widget/fr/c.html", "docs/d.html", "news/e.html", "match.html"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(model(), encoding="utf-8")
            self.assertEqual(mp.main(["--check"], root), 1)
            self.assertEqual(mp.main([], root), 0)
            changed = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.html") if 'details class="menu"' in p.read_text(encoding="utf-8"))
            self.assertEqual(changed, ["a.html", "equipes/b.html"])
            self.assertEqual(mp.main(["--check"], root), 0)

    def test_with_css_ajoute_seulement_les_regles_manquantes(self):
        page = "<style>\na{x}\n</style><body></body>"
        self.assertEqual(sc.with_css(page, "a{x}\nb{y}"), "<style>\na{x}\n\nb{y}\n</style><body></body>")
        self.assertEqual(sc.with_css(page, "a{x}"), page)

    @unittest.skipUnless((REAL / "fr.html").is_file(), "pages du site absentes")
    def test_toutes_les_pages_du_site_l_ont(self):
        """Dans l'arbre de travail, chaque page publique (hors widgets et renvois) a un en-tête avec le menu du site dans sa langue, et
        chaque lien relatif du menu mène à un fichier existant (une ancre à une section de l'accueil visé)."""
        count = 0
        for path in mp.pages(REAL):
            rel = path.relative_to(REAL).as_posix()
            text = path.read_bytes().decode("utf-8")
            if 'http-equiv="refresh"' in text or "</body>" not in text or path.name in mp.SKIP_PAGES:
                continue
            count += 1
            with self.subTest(page=rel):
                self.assertEqual(mp.render(text, rel), text)  # rien à faire
                header = header_of(text)
                lang = mp.language(text)
                self.assertIsNotNone(lang)
                self.assertEqual(text.count('<details class="menu">'), 1)
                self.assertIn(f'<nav aria-label="{sc.MENU[lang]["nav"]}">', header)
                for href in re.findall(r'<a[^>]* href="([^"]*)"', header):
                    if href.startswith(("https:", "http:", "mailto:")):
                        continue
                    target, _, anchor = href.partition("#")
                    base = REAL if target.startswith("/") else path.parent
                    file = (base / (target.lstrip("/") or "index.html"))
                    file = file / "index.html" if file.is_dir() else file
                    self.assertTrue(file.is_file(), f"{href} → {file}")
                    if anchor:
                        self.assertIn(f'id="{anchor}"', file.read_text(encoding="utf-8"), href)
        self.assertGreater(count, 300)


if __name__ == "__main__":
    unittest.main()
