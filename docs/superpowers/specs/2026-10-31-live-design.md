# Onglet « Live » : les matchs du jour, en direct selon l'horloge

Demande du 31 octobre 2026 : un onglet « Live » dans le menu du site qui montre les matchs en direct « selon l'application ».
Choix retenu (réponse de l'utilisateur) : **horloge + calendriers**. Le relais eSportly ne publie que des calendriers ICS
(début et fin prévus, pas de score ni d'état « en cours »), sans en-tête CORS, et ce dépôt n'a pas de code serveur : la page
est fabriquée chaque matin avec les matchs du jour, et un petit script compare les horaires à l'heure du visiteur.

## Ce que voit le visiteur

- Un lien **Live** (même mot dans les 5 langues, précédé d'une pastille rouge) à la fin de la barre du menu et du panneau
  mobile, sur les 5 accueils et toutes les pages habillées du menu du site (News, Blog, Live) ; une entrée « Live » dans la
  liste des pages du pied de page des accueils (reprise partout par `render_footer`).
- Une page par langue : `live.html` (anglais, `x-default`), `live-fr.html`, `live-es.html`, `live-de.html`, `live-pt.html`,
  publiées sans extension (`/live`, `/live-fr`…), avec canonical, hreflang, og:*, JSON-LD `SportsEvent` et une entrée dans
  `sitemap.xml` (`changefreq` daily). Fabriquée depuis la page « Nouveautés » de la langue (comme les pages de la semaine),
  puis habillée par `site_chrome.with_chrome` (menu avec « Live » marqué `aria-current="page"`, pied de page de l'accueil).
- Contenu de `<main>` : héros (kicker, h1, lead, bouton de la bêta), un paragraphe d'état `<p class="live-now" id="live-now">`
  (sans JavaScript : « Heures de Paris » ; avec : « 3 matchs en direct » ou « Aucun match en direct pour l'instant · Prochain
  match à 18:00 »), la rangée de filtres par jeu (`site_chrome.render_filter`, seulement les jeux présents), puis les matchs
  groupés par jour (« Aujourd'hui », « Demain », sinon la date) dans des `<ul class="matchs">`, chaque `<li>` portant
  `data-start` / `data-end` (ISO 8601 UTC), `data-game="<jeu>"` quand le jeu est connu du site, et dans le lien
  `<span class="etat"></span>` (vide sans JavaScript, caché par `.etat:empty`), l'heure de Paris, « A – B », la compétition.
  Une note explique que l'état vient des horaires du calendrier et que le score est dans l'app, puis « Mis à jour le … ».
- Fenêtre des matchs : début entre `now − 6 h` et `now + 30 h` (la page est fabriquée vers 6 h 15, heure de Paris : elle couvre
  la nuit passée et la matinée du lendemain), toutes équipes (`everything`) et grands événements (`EVENTS`) confondus,
  dédoublonnés par UID, triés par début. Sans match : « Aucun match aujourd'hui. ».
- Le script `LIVE_JS` (en ligne, empreinte dans `script-src`) : pour chaque `li[data-start]`, `s = début`, `e = fin` (au moins
  `s + 1 h`, puis `+ 30 min` de marge : la fin du calendrier est une estimation), état `soon` si `now < s`, `live` si `s ≤ now < e`,
  sinon `done`, écrit dans `data-state` et le texte de `.etat` ; compte les directs et le prochain début pour `#live-now` ;
  recalcule chaque minute. Heure du prochain match en heure de Paris (`Intl.DateTimeFormat`, `timeZone: 'Europe/Paris'`).
  L'heure locale du visiteur s'ajoute comme ailleurs (`with_local_times`).
- Style (`LIVE_STYLE`) : `.etat` en petites capitales, point rouge animé (`@keyframes`) devant « En direct », désactivé avec
  `prefers-reduced-motion` ; carte d'un direct bordée d'or ; carte terminée atténuée. Menu : `a.live::before` pastille rouge
  (règle identique dans les 5 accueils et `MENU_STYLE`).

## Code

- `site_chrome.py` : `LIVE_LABEL = "Live"`, `LIVE_PAGES = {"en": "live.html", "fr": "live-fr.html", …}` ; `MENU[lang]` inchangé ;
  `render_menu(…, live: str, current)` ajoute `<a class="live" href="{live}"{here si current == "live"}>Live</a>` après « Blog »
  dans la barre et le panneau ; `with_chrome(…, live=…)` le transmet. `MENU_STYLE` reçoit la règle `a.live::before`.
  Appelants (`actualites.render_page`, `blog`) passent `live=prefix + LIVE_PAGES[lang]`.
- Nouveau module `.github/scripts/live.py` (importé par `matchs.py`, testé par `test_live.py`) : `LABELS` (5 langues, mêmes
  clés), `LIVE_JS` / `LIVE_HASH` / `LIVE_STYLE`, `select(events, now)` (fenêtre), `game_slug(description, names_en)`,
  `render_main(lang, events, now, t, names)` (le `<main>`), `render_page(lang, template, events, now, t, home_page, names)`
  (titre, meta, og, liens de langue via `rename_page`, main, `with_chrome`, `with_script(LIVE_JS)`, style), et les textes SEO :
  titre ≤ 60 caractères avec « – eSportly », meta ≤ 155.
- `matchs.py` : section 4 « Live » après les grands événements : réunit `everything` et les matchs des événements, écrit les
  5 pages avec `live.render_page`, puis `with_local_times`.
- Accueils (5) : lien « Live » (barre, panneau, pied de page) et la règle CSS ; `sitemap.xml` : 5 entrées ; `README.md`.

## Tests

- `test_live.py` : labels complets ; fenêtre ; attributs `data-*` et échappement ; groupement par jour ; vide ; script et
  empreinte ajoutés une fois (page refabriquée identique) ; `#live-now` présent ; filtre par jeu ; JSON-LD ; titre/meta.
- `test_blog.py` : `MENUS` finit par « Live », `LINK` tolère `class="live"`, règle `a.live::before` dans les accueils ;
  `test_actualites.py` : le menu de la page News contient « Live » après « Blog ».

## Hors périmètre (suites possibles)

- Vrai flux « live » avec scores : un point d'accès côté serveur de l'app (autre dépôt) ; la page garde ses `data-*` pour l'accueillir.
- Fabrication plus fréquente que le matin (le relais rafraîchit ses calendriers toutes les heures).
