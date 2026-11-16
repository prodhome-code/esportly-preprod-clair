"""Tests du panneau des jeux (mega menu) : son contenu, sa pose sur les accueils, et les noms de jeux qu'il affiche."""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import mega_accueils
import site_chrome as sc

REAL = Path(__file__).resolve().parents[2]
HOME = """<!doctype html>
<html lang="fr">
<head><style>body{margin:0}</style></head>
<body>
<header><div class="wrap"><a class="brand" href="fr.html">eS</a><nav aria-label="Sections de la page"><a href="#jeux">Jeux</a>\
<a href="#equipes">Équipes</a></nav><details class="menu"><summary aria-label="Menu">b</summary>\
<div class="panel" role="navigation" aria-label="Menu"><a href="#jeux">Jeux</a><a href="#fonctions">Fonctions</a>\
<div class="langsm"><a href="fr.html">Français</a></div></div></details></div></header>
</body></html>
"""


class Panneau(unittest.TestCase):
    """games_menu / games_panel : les 14 jeux, leurs logos, et les deux liens du bas."""

    def test_les_14_jeux_dans_les_cinq_langues(self):
        for lang in sc.GAME_DIRS:
            with self.subTest(lang=lang):
                menu = sc.games_menu(lang, "../", "../fr.html")
                for game in sc.GAMES:
                    self.assertIn(f'href="../{sc.GAME_DIRS[lang]}/{game}.html"', menu)
                    self.assertIn(f'src="../logos-jeux/{game}.png"', menu)
                self.assertEqual(menu.count("<li>"), len(sc.GAMES))

    def test_liens_du_bas(self):
        menu = sc.games_menu("fr", "../", "../fr.html")
        self.assertIn('<a href="../fr.html#jeux">Tous les jeux →</a>', menu)
        self.assertIn('<a href="../fr/equipes.html">Toutes les équipes →</a>', menu)
        self.assertIn('<a href="teams.html">All teams →</a>', sc.games_menu("en", "", ""))

    def test_sans_script_et_referme(self):
        """Le panneau est un <details>, comme le menu de langue : il s'ouvre sans JavaScript, et fermé il ne montre rien."""
        menu = sc.games_menu("fr", "", "")
        self.assertTrue(menu.startswith('<details class="mega"><summary>Jeux'))
        self.assertTrue(menu.endswith("</details>"))
        self.assertNotIn("<script", menu)
        self.assertNotIn("onclick", menu)

    def test_le_nom_du_jeu_est_le_texte_de_remplacement_du_logo(self):
        menu = sc.games_menu("fr", "", "")
        self.assertIn('alt="League of Legends"', menu)
        self.assertIn('alt="Mobile Legends: Bang Bang"', menu)

    def test_panneau_du_burger(self):
        panel = sc.games_panel("de", "../../")
        self.assertTrue(panel.startswith('<details class="megam"><summary>Spiele'))
        self.assertIn('href="../../de/spiele/valorant.html"', panel)
        self.assertEqual(panel.count("<li>"), len(sc.GAMES))

    def test_style_livre_avec_le_menu(self):
        css = "\n".join(sc.MENU_STYLE)
        for rule in (".megap{", ".megag{", ".megam>summary{", ".mega[open] .chev{"):
            self.assertIn(rule, css)
        self.assertIn("invert(1)", css)  # les logos blancs s'inversent sur fond clair

    def test_panneau_ancre_sous_son_bouton(self):
        """Le panneau s'ouvre sous SON bouton : ancré sur la barre entière, il s'ouvrait sous la marque, loin du mot cliqué,
        et plus personne ne voyait ce qui avait ouvert quoi. Sa largeur, elle, reste tenue pour qu'il ne sorte pas de l'écran."""
        css = "\n".join(sc.MENU_STYLE)
        self.assertIn(".mega{position:relative}", css)
        megap = [rule for rule in sc.MEGA_STYLE if rule.startswith(".megap{")]
        self.assertEqual(len(megap), 1)
        self.assertIn("left:0;right:auto", megap[0])
        self.assertIn("width:max-content", megap[0])
        self.assertIn("max-width:min(86vw,860px)", megap[0])
        self.assertTrue([rule for rule in sc.MEGA_STYLE if rule.startswith(".megap::before{")], "pas de pointe vers le bouton")


class PanneauEquipes(unittest.TestCase):
    """Le panneau « Équipes » : les jeux d'un côté, les équipes à suivre de l'autre, la recherche en bas (option C de d0m)."""

    def test_les_deux_colonnes(self):
        for lang in sc.MENU:
            with self.subTest(lang=lang):
                panel = sc.teams_menu(lang, "../")
                self.assertIn('<details class="mega team">', panel)
                self.assertIn('<ul class="tgames">', panel)
                for game in sc.TEAM_GAMES:
                    self.assertIn(f"{sc.TEAMS_PAGES[lang]}#{game}", panel)

    def test_les_equipes_a_suivre_viennent_du_calendrier(self):
        """Les vedettes sont choisies par matchs.py (equipes/vedettes.json), pas écrites à la main."""
        if not sc.stars():
            self.skipTest("equipes/vedettes.json absent")
        panel = sc.teams_menu("fr", "../")
        for team in sc.stars():
            with self.subTest(team=team["slug"]):
                self.assertIn(f'{sc.TEAM_DIRS["fr"]}/{team["slug"]}.html', panel)
                self.assertIn(team["nom"], panel)
                if team.get("logo"):
                    self.assertIn(f'logos-equipes/{team["logo"]}', panel)

    def test_la_recherche_ne_porte_pas_la_liste_des_equipes(self):
        """Le menu est recopié dans les centaines de pages du site : les 83 équipes ne peuvent pas y être, le champ va les
        chercher dans un fichier à part, au premier clic."""
        panel = sc.teams_menu("fr", "../")
        self.assertIn('<form class="tsearch"', panel)
        self.assertIn('data-src="../equipes/index-pages.json"', panel)
        self.assertIn('data-dir="../fr/equipes/"', panel)
        self.assertLess(len(panel), 4000)

    def test_les_deux_champs_ont_des_identifiants_distincts(self):
        """Celui de la barre et celui du burger sont dans la même page : deux identifiants identiques casseraient l'étiquette."""
        both = sc.teams_menu("fr", "") + sc.teams_panel("fr", "")
        ids = re.findall(r'id="([^"]+)"', both)
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_le_script_cherche_un_seul_fichier_du_site(self):
        self.assertEqual(sc.MENU_JS.count("fetch("), 1)
        self.assertNotIn("http", sc.MENU_JS)  # jamais une adresse extérieure
        self.assertNotIn("innerHTML", sc.MENU_JS)  # les suggestions se posent avec createElement

    def test_le_panneau_du_burger_n_a_pas_de_panneau_flottant(self):
        panel = sc.teams_panel("fr", "")
        # « team » dans la classe : c'est à cela que mega_accueils reconnaît son propre panneau. Le chercher par le mot « team »
        # n'allait pas — « teams.html » apparaît déjà dans le panneau des jeux des quatre langues non françaises.
        self.assertIn('<details class="megam team">', panel)
        self.assertNotIn("megap", panel)

    def test_les_panneaux_se_referment(self):
        """Un <details> laissé ouvert suivait le visiteur sur toute la page : clic ailleurs, Échap, ou l'autre panneau le ferment."""
        self.assertIn("header details.mega", sc.MENU_JS)
        self.assertIn("e.key==='Escape'", sc.MENU_JS)
        self.assertIn("contains(e.target)", sc.MENU_JS)
        self.assertIn("'toggle'", sc.MENU_JS)


class Noms(unittest.TestCase):
    @unittest.skipUnless((REAL / "fr.html").is_file(), "pages du site absentes")
    def test_noms_de_jeux(self):
        """GAME_NAMES doit dire la même chose que les pages du site (read_game_names), pour les 14 jeux et les 5 langues."""
        read = sc.read_game_names(REAL)
        for lang, names in read.items():
            for game in sc.GAMES:
                if game in names:
                    with self.subTest(lang=lang, game=game):
                        self.assertEqual(names[game], sc.GAME_NAMES[game])

    def test_un_nom_par_jeu(self):
        self.assertEqual(sorted(sc.GAME_NAMES), sorted(sc.GAMES))

    @unittest.skipUnless((REAL / "logos-jeux").is_dir(), "logos absents")
    def test_un_logo_par_jeu(self):
        for game in sc.GAMES:
            self.assertTrue((REAL / "logos-jeux" / f"{game}.png").is_file(), game)


class Accueils(unittest.TestCase):
    """mega_accueils : la pose du panneau sur un accueil, sans toucher au reste de son en-tête."""

    def test_barre_et_burger(self):
        done = mega_accueils.apply(HOME, "fr")
        self.assertIsNotNone(done)
        self.assertIn('<nav aria-label="Sections de la page"><details class="mega"><summary>Jeux', done)
        self.assertIn('<details class="megam"><summary>Jeux', done)
        self.assertNotIn('<a href="#jeux">Jeux</a>', done)  # l'ancre a disparu des deux endroits
        self.assertNotIn('<a href="#equipes">', done)  # « Équipes » devient un panneau, comme « Jeux »
        self.assertIn('<details class="mega team">', done)
        self.assertNotIn('<a href="#fonctions">Fonctions</a>', done)  # « Fonctions » et « Appareils » sont retirés du menu
        self.assertIn('<div class="langsm">', done)  # le reste du panneau est intact
        self.assertIn(".megap{", done)  # le style arrive avec

    def test_fonctions_et_appareils_retires(self):
        """« Fonctions » et « Appareils » quittent la barre et le burger ; leurs sections restent sur la page et dans le pied de page."""
        done = mega_accueils.apply(HOME, "fr")
        for anchor in ("#fonctions", "#appareils"):
            self.assertNotIn(f'<a href="{anchor}">', done)
        self.assertIsNone(mega_accueils.apply(done, "fr"))  # rejouable : plus rien à retirer

    def test_les_jeux_remplissent_la_grille(self):
        """Sept colonnes pour quatorze jeux : deux rangées pleines, aucune case vide à côté du dernier logo."""
        grille = [rule for rule in sc.MEGA_STYLE if rule.startswith(".megag{")]
        self.assertEqual(len(grille), 1)
        self.assertIn("repeat(7,", grille[0])
        self.assertEqual(len(sc.GAMES) % 7, 0, "le nombre de jeux ne tombe plus juste sur sept colonnes")

    def test_liens_depuis_la_racine(self):
        done = mega_accueils.apply(HOME, "fr")
        self.assertIn('<a href="fr/jeux/valorant.html">', done)
        self.assertIn('<a href="#jeux">Tous les jeux →</a>', done)

    def test_rejouable(self):
        once = mega_accueils.apply(HOME, "fr")
        self.assertIsNone(mega_accueils.apply(once, "fr"))

    def test_page_sans_barre_laissee_telle_quelle(self):
        self.assertIsNone(mega_accueils.apply("<html><body><p>rien</p></body></html>", "fr"))

    def test_main_ecrit_et_rejoue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in mega_accueils.HOMES.values():
                (root / name).write_text(HOME, encoding="utf-8")
            self.assertEqual(mega_accueils.main([], root), 0)
            posed = (root / "fr.html").read_text(encoding="utf-8")
            self.assertIn('<details class="mega">', posed)
            self.assertEqual(mega_accueils.main([], root), 0)
            self.assertEqual((root / "fr.html").read_text(encoding="utf-8"), posed)  # second passage : rien ne bouge

    def test_essai_n_ecrit_rien(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "fr.html").write_text(HOME, encoding="utf-8")
            self.assertEqual(mega_accueils.main(["--essai"], root), 0)
            self.assertEqual((root / "fr.html").read_text(encoding="utf-8"), HOME)


@unittest.skipUnless((REAL / "fr.html").is_file(), "pages du site absentes")
class SurLeSite(unittest.TestCase):
    def test_les_cinq_accueils_ont_le_panneau(self):
        for lang, name in mega_accueils.HOMES.items():
            with self.subTest(page=name):
                page = (REAL / name).read_text(encoding="utf-8")
                header = re.search(r"<header>.*?</header>", page, re.S).group(0)
                self.assertIn('<details class="mega">', header)
                self.assertIn('<details class="megam">', header)
                self.assertEqual(header.count(f"{sc.GAME_DIRS[lang]}/valorant.html"), 2)  # barre et burger

    def test_une_page_fabriquee_l_a_aussi(self):
        page = (REAL / "fr/blog.html").read_text(encoding="utf-8")
        header = re.search(r"<header>.*?</header>", page, re.S).group(0)
        self.assertIn('<details class="mega">', header)
        self.assertIn('href="../fr/jeux/valorant.html"', header)


if __name__ == "__main__":
    unittest.main()
