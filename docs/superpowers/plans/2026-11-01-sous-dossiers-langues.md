# Sous-dossiers de langue : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servir les pages fr/es/de/pt sous `/fr/`, `/es/`, `/de/`, `/pt/` (chemins traduits conservés), chaque ancienne adresse redirigeant en 301, sans rien casser pour Google, le robot du matin ni l'app.

**Architecture:** Un script rejouable `sous_dossiers.py` déplace les fichiers de la carte et réécrit tous les liens (relatifs résolus puis re-relativisés, absolus mappés), écrit `_redirects`, renomme les clés de `seo/titres.json`. Les générateurs gardent leur logique : leurs tables prennent des chemins depuis la racine (`fr/blog.html`, `fr/jeux`) et le préfixe `../` se calcule depuis la profondeur de la page produite (`site_chrome.prefix_for`) au lieu d'être codé `""` ou `"../"`.

**Tech Stack:** Python 3.12-compatible (unittest, regex, posixpath), fichier `_redirects` des Workers Assets Cloudflare.

**Spec:** `docs/superpowers/specs/2026-10-31-sous-dossiers-langues-design.md`

## Global Constraints

- Python compatible 3.12 (le robot tourne en 3.12) ; tests : `PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 py -3.13 -W error -m unittest discover -s .github/scripts -p "test_*.py"`.
- Fins de ligne de chaque fichier conservées (toutes les pages sont en CRLF) : lire/écrire en octets ou `newline=""`.
- CSP intactes : aucun script ajouté, aucune empreinte à recalculer.
- Adresses publiées sans `.html` (`actualites.public_url`) ; liens de navigation relatifs en `.html`.
- Accueils (`index.html`, `fr.html`, `es.html`, `de.html`, `pt.html`), `en.html`, `match.html`, `tv-equipes.html`, `404.html`, `widget/`, `partage/` ne bougent pas (spec § 1, décisions A et D).
- Dossiers ignorés par les scripts : `.git`, `.github`, `.claude`, `.superpowers`, `docs`, `news`, `blog-src`, `node_modules`, `.wrangler`, `worker`, `seo`.
- Commits : `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`, message terminé par `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` ; jamais de force-push.

## Review Focus

1. Un lien relatif à ancre seule (`#f-valorant`) ou avec requête (`match.html?id=1`) doit rester tel quel : testé en tâche 1.
2. Un lien vers un accueil depuis une page déplacée (`fr.html#jeux` depuis `live-fr.html`) doit devenir `../fr.html#jeux`, et `./` (accueil anglais) `../` : testé en tâche 1.
3. `404.html` est servie à n'importe quelle adresse : ses liens root-absolus (`/mentions-legales.html`) doivent suivre la carte et rester absolus : testé en tâche 1.
4. Rejouer le script sur un dépôt déjà migré doit refuser sans rien écrire (`fr/` existe) : testé en tâche 2.
5. Une page produite par un générateur depuis son propre texte ne doit pas changer (stabilité du robot) : vérifié en tâche 6 sur le vrai site (`--essai` / `--check` vides).

---

### Tâche 1 : carte et réécriture des liens (`sous_dossiers.py`, fonctions pures)

**Files:**
- Create: `.github/scripts/sous_dossiers.py`
- Test: `.github/scripts/test_sous_dossiers.py`

**Interfaces:**
- Produces: `ROOT_MOVES: dict[str, str]` (fichier racine → nouveau chemin, 57 entrées : 18 fr, 12 es, 12 de, 12 pt-BR, 3 en, exactement les tables § 3 de la spec, par exemple `"blog-fr.html": "fr/blog.html"`, `"worlds-2026-en.html": "worlds-2026.html"`), `DIR_MOVES: dict[str, str]` (9 dossiers, `"jeux": "fr/jeux"`…), `XML_MOVES: dict[str, str]` (4 flux), `SKIP_DIRS` (contrainte globale).
- `build_map(root: Path) -> dict[str, str]` : chemin ancien → chemin nouveau (posix, depuis la racine) pour chaque fichier de `ROOT_MOVES`, `XML_MOVES` et chaque `*.html` des `DIR_MOVES` (contenu lu sur disque).
- `rewrite(text: str, old_path: str, new_path: str, mapping: dict[str, str]) -> str` : le texte d'un fichier (HTML, XML, JS) avec ses liens réécrits. `old_path`/`new_path` : chemins du fichier avant/après (égaux si le fichier ne bouge pas).
- `public(path: str) -> str` : `"fr/blog/valorant.html"` → `"/fr/blog/valorant"` (`"index.html"` → `"/"`).

- [ ] **Step 1 : tests de la carte**

```python
def test_carte_racine_et_dossiers(self):  # sur un faux site tmp avec jeux/valorant.html, blog-fr/valorant.html, live-fr.html, nouveautes.xml
    m = sous_dossiers.build_map(root)
    self.assertEqual(m["jeux/valorant.html"], "fr/jeux/valorant.html")
    self.assertEqual(m["live-fr.html"], "fr/live.html")
    self.assertEqual(m["worlds-2026-en.html"], "worlds-2026.html")
    self.assertEqual(m["nouveautes.xml"], "fr/nouveautes.xml")
    self.assertNotIn("fr.html", m); self.assertNotIn("index.html", m); self.assertNotIn("match.html", m)
def test_nombre_de_fichiers_racine(self):
    self.assertEqual(len(sous_dossiers.ROOT_MOVES), 57)
    self.assertEqual(sum(1 for v in sous_dossiers.ROOT_MOVES.values() if v.startswith("fr/")), 18)
```

- [ ] **Step 2 : tests de réécriture** (valeurs exactes ; `mapping` = carte minimale construite à la main)

```python
# page déplacée de la racine vers fr/ : profondeur +1
rewrite('<a href="jeux/valorant.html">', "live-fr.html", "fr/live.html", m) == '<a href="jeux/valorant.html">'      # jeux→fr/jeux : vu de fr/live.html, c'est jeux/valorant.html
rewrite('<a href="fr.html#jeux">', "live-fr.html", "fr/live.html", m) == '<a href="../fr.html#jeux">'
rewrite('<a href="./">', "live-fr.html", "fr/live.html", m) == '<a href="../">'
rewrite('<link rel="icon" href="embleme.svg">', "live-fr.html", "fr/live.html", m) == '<link rel="icon" href="../embleme.svg">'
rewrite("url(fonts/Rajdhani-Bold.woff2)", "live-fr.html", "fr/live.html", m) == "url(../fonts/Rajdhani-Bold.woff2)"
rewrite('<a href="#f-valorant">', "live-fr.html", "fr/live.html", m) inchangé ; href="https://esportly.eu/match.html?id=1" inchangé
# page déplacée de jeux/ vers fr/jeux/ : profondeur +1, cibles déplacées ou non
rewrite('<a href="../games/valorant.html">', "jeux/valorant.html", "fr/jeux/valorant.html", m) == '<a href="../../games/valorant.html">'
rewrite('<a href="../blog-fr/valorant.html">', ..., m) == '<a href="../blog/valorant.html">'
rewrite('<a href="counter-strike-2.html">', ..., m) == '<a href="counter-strike-2.html">'
# page qui ne bouge pas, cible déplacée : lien relatif, root-absolu, absolu
rewrite('<a href="jeux/valorant.html">', "index.html", "index.html", m) == '<a href="fr/jeux/valorant.html">'
rewrite('<a href="/mentions-legales.html">', "404.html", "404.html", m) == '<a href="/fr/mentions-legales.html">'
rewrite('<a href="https://esportly.eu/equipes/t1.html">', "widget/fr/t1.html", "widget/fr/t1.html", m) == '…esportly.eu/fr/equipes/t1.html…'
# adresses publiées (sans .html) : canonical, hreflang, og:url, <loc>, JSON-LD, visite?p=
rewrite('href="https://esportly.eu/jeux/valorant"', ...) == 'href="https://esportly.eu/fr/jeux/valorant"'
rewrite('<loc>https://esportly.eu/blog-fr</loc>', "sitemap.xml", "sitemap.xml", m) == '<loc>https://esportly.eu/fr/blog</loc>'
rewrite('"item": "https://esportly.eu/blog-fr/valorant"', ...) == '"item": "https://esportly.eu/fr/blog/valorant"'
rewrite("visite?p=/jeux/valorant&amp;go=testflight", ...) == "visite?p=/fr/jeux/valorant&amp;go=testflight"
rewrite("visite?p=/live-fr", ...) == "visite?p=/fr/live" ; "visite?p=/" et "visite?p=/news" inchangés
rewrite("https://esportly.eu/worlds-2026", "live-fr.html", "fr/live.html", m) == "https://esportly.eu/fr/worlds-2026"   # ancienne page fr
rewrite("https://esportly.eu/worlds-2026-en", ...) == "https://esportly.eu/worlds-2026"
# page non déplacée, cible non déplacée : octet pour octet (y compris une forme non normalisée comme ".././")
rewrite('<a href="../games/valorant.html">', "games/lol.html", "games/lol.html", m) inchangé
# analytics.js : page: '/confidentialite.html' → '/fr/confidentialite.html'
# fins de ligne CRLF conservées
```

- [ ] **Step 3 : lancer les tests, vérifier l'échec** (`ModuleNotFoundError`)

- [ ] **Step 4 : implémenter**

Règles de `rewrite` : (a) adresses absolues `https://esportly.eu/<chemin>` suivies de `"`, `<`, `#`, `?`, `'` ou fin : `<chemin>` avec ou sans `.html` cherché dans la carte (`mapping` et sa version `public`), `.html` conservé s'il y était ; (b) `visite?p=/<chemin>` idem (sans `.html`) ; (c) valeurs d'attributs `href="…"`, `src="…"`, `content="…"` (seulement si elles commencent par `/` ou sont relatives sans schéma) et `url(…)` du CSS : root-absolu → carte ; relatif → `posixpath.normpath(join(dirname(old_path), cible))` puis carte puis `posixpath.relpath(nouvelle cible, dirname(new_path))` ; requête et fragment conservés ; cible vide/`./`/`../` = racine → `./` à la racine, `../` × profondeur sinon ; **le lien n'est réécrit que si la page ou la cible bouge** (sinon le texte original reste). Ne pas toucher aux `data:`, `mailto:`, `webcal:`, `http(s):` autres que le site, ni aux attributs `content` qui ne sont pas une adresse (test : commence par `/`, `../`, `./`, ou se termine par `.html`/`.xml`/`.svg`/`.png`/`.jpg`/`.webp`/`.css`/`.js`/`.woff2`/`.webmanifest`).

- [ ] **Step 5 : tests verts ; commit** `Script sous_dossiers.py : carte des adresses et réécriture des liens (fonctions pures)`

### Tâche 2 : application du script (déplacements, `_redirects`, sitemap, titres.json, essai, refus)

**Files:**
- Modify: `.github/scripts/sous_dossiers.py`
- Test: `.github/scripts/test_sous_dossiers.py`

**Interfaces:**
- `plan(root: Path) -> dict[str, bytes]` : chemin nouveau → contenu nouveau de **tous** les fichiers à écrire (déplacés ou réécrits : `*.html` hors `SKIP_DIRS`, `widget/` compris, `sitemap.xml`, les 5 `*.xml`, `analytics.js`, `seo/titres.json`, `_redirects`), plus la liste des anciens chemins à supprimer ; signature exacte : `plan(root, today: date) -> tuple[dict[str, bytes], list[str]]`.
- `redirects(mapping: dict[str, str]) -> str` : le texte de `_redirects` (LF) : une ligne `/<ancien> /<nouveau> 301` et une `/<ancien>.html /<nouveau> 301` par page (`/live-fr /fr/live 301`, `/live-fr.html /fr/live 301` ; dossiers : `/jeux/valorant /fr/jeux/valorant 301` + `.html`), `/<ancien>.xml /<nouveau>.xml 301` par flux, puis les 8 jokers `/jeux/* /fr/jeux/:splat 301`… en dernier (pas de joker pour `equipes` : ses fiches `*.json` y restent, décision G de la spec) ; commentaire d'en-tête ; jamais de ligne dont la source égale la destination.
- `main(argv, root=ROOT) -> int` : `--essai` imprime le compte (fichiers déplacés, réécrits, règles) sans écrire ; sinon écrit, supprime les anciens fichiers (`os.remove`, dossiers vidés supprimés), crée les dossiers.
- `check_start_state(root)` lève `Refus` si `root/"fr"` est un dossier ou si `live-fr.html` manque.

- [ ] **Step 1 : tests** (faux site complet en tmp : accueil `fr.html` avec liens, `live-fr.html`, `jeux/valorant.html`, `blog-fr/valorant.html`, `equipes/t1.html`, `widget/fr/t1.html`, `404.html`, `sitemap.xml` à 2 entrées avec lastmod, `nouveautes.xml`, `analytics.js`, `seo/titres.json` à 3 clés, tous en CRLF sauf sitemap/json en LF)

```python
def test_plan_deplace_et_reecrit(self): files, removed = plan(root, date(2026,11,1))
    self.assertIn("fr/live.html", files); self.assertIn("live-fr.html", removed); self.assertNotIn("fr.html", removed)
    self.assertIn(b'href="../fr.html#jeux"', files["fr/live.html"]); self.assertIn(b"\r\n", files["fr/live.html"])
    self.assertIn(b'href="fr/jeux/valorant.html"', files["fr.html"])  # accueil réécrit, pas déplacé
def test_sitemap(self): <loc> réécrits, lastmod des entrées déplacées = 2026-11-01, entrée non déplacée intacte
def test_titres_json(self): clés renommées (/jeux/valorant → /fr/jeux/valorant), ordre et indent=1 conservés, clé /news intacte
def test_redirects(self): lignes exactes ci-dessus, jokers en dernier, aucune ligne source == destination, compte = 2*pages + xml + 8
def test_refus_si_deja_fait(self): fr/ existe → Refus, rien n'est écrit (mtime inchangés)
def test_essai_n_ecrit_rien(self); def test_main_ecrit_et_supprime(self): après main, old absents, nouveaux présents, dossiers vides supprimés, rejouer → Refus
```

- [ ] **Step 2 : échec, implémenter, vert**

- [ ] **Step 3 : commit** `sous_dossiers.py : déplacements, _redirects, sitemap, titres.json, --essai`

### Tâche 3 : `site_chrome.py`, tables et préfixe

**Files:**
- Modify: `.github/scripts/site_chrome.py` (HUBS, LIVE_PAGES, BLOG_DIRS, GAME_DIRS)
- Test: `.github/scripts/test_blog.py` ou nouveau `test_site_chrome.py` (suivre où sont testés HUBS aujourd'hui)

**Interfaces:**
- Produces: `HUBS = {"en": "blog.html", "fr": "fr/blog.html", "es": "es/blog.html", "de": "de/blog.html", "pt-BR": "pt/blog.html"}`, `LIVE_PAGES` (`fr/live.html`…), `BLOG_DIRS = {"en": "blog", "fr": "fr/blog", …}`, `GAME_DIRS = {"en": "games", "fr": "fr/jeux", "es": "es/juegos", "de": "de/spiele", "pt-BR": "pt/jogos"}`, `LANG_DIRS = {"en": "", "fr": "fr/", "es": "es/", "de": "de/", "pt-BR": "pt/"}`.
- `prefix_for(path: str) -> str` : `"../" * path.count("/")` (`"fr/blog/valorant.html"` → `"../../"`, `"blog.html"` → `""`).
- `home_link(lang: str, prefix: str) -> str` : `(prefix or "./")` pour `en`, sinon `prefix + HOMES[lang]` (déplacé de `blog._home_link` / `menu_partout.home_of`, qui l'appellent). HOMES reste dans `actualites` ; `site_chrome` reçoit sa propre copie `HOMES` (identique, testée égale à `actualites.HOMES`).

- [ ] **Step 1 : tests** `prefix_for`, `home_link("fr", "../../") == "../../fr.html"`, `home_link("en", "") == "./"`, tables exactes
- [ ] **Step 2 : implémenter ; vert ; commit** `site_chrome : tables des sous-dossiers de langue, prefix_for et home_link`

### Tâche 4 : générateurs (`actualites.py`, `live.py`, `blog.py`, `matchs.py`, `menu_partout.py`, `titres_seo.py`)

**Files:**
- Modify: `.github/scripts/actualites.py:31-38` (PAGES `fr/actualites.html`…, TEMPLATES `fr/nouveautes.html`…, WEEKLY `fr/matchs-de-la-semaine.html`…, `EVENT_SUFFIX` → `EVENT_DIRS = site_chrome.LANG_DIRS` : la page d'événement est `f"{EVENT_DIRS[lang]}{slug}.html"` ; `page_for`, `_check_events` (cherche `site / f"{slug}.html"` : garder la page anglaise), `_info_li` (lien blog vu d'une page News : `prefix_for(PAGES[lang]) + BLOG_DIRS[lang]/…`), `_home_block` (lien `PAGES[lang]` vu de l'accueil, à la racine : inchangé), `render_page` (prefix = `prefix_for(PAGES[lang])`, `home=home_link`, `news=prefix+PAGES`, `hub=prefix+HUBS`, `live=prefix+LIVE_PAGES`, regex `visite\?p=/[a-z-]+` → `[a-z/-]+`), `set_lastmod` inchangé.
- Modify: `.github/scripts/live.py:198-208` (même schéma : prefix, home_link, regex `visite`, `slug = PAGES[lang][:-5]` donne `fr/live`).
- Modify: `.github/scripts/blog.py` : `_home_link` → `site_chrome.home_link` ; `render_guide_page` prefix `"../"` → `prefix_for(f"{BLOG_DIRS[lang]}/{target}.html")` ; `render_hub_page` prefix `""` → `prefix_for(HUBS[lang])` ; `render_main` crumbs `../{HUBS[lang]}`, logo `../logos-jeux/`, `../{GAME_DIRS[lang]}/` → via `prefix` (nouveau paramètre ou calcul local depuis `BLOG_DIRS[lang]`) ; `render_hub_main` cartes `folder/<id>.html` et `logos-jeux/` vus de `HUBS[lang]` (`fr/blog.html` → `blog/<id>.html` et `../logos-jeux/`) : utiliser `posixpath.relpath` depuis le dossier du hub ; `render_guide_link` (lien inséré dans la page de jeu `fr/jeux/x.html` vers `fr/blog/y.html` : `../blog/y.html`) ; `_orphans`, `sitemap_block` (chemins déjà via tables) ; `_missing_templates`.
- Modify: `.github/scripts/matchs.py` : `LANGS[*]["file"]`, `["news"]`, `["teams"]` (`fr/equipes`), `HOME` (`"fr": "../fr.html"` si utilisé comme lien, vérifier l'usage réel : il sert à lire l'accueil → garder le fichier `fr.html` et utiliser `home_link` pour les liens), `EXTRA[*]["ev_suffix"]` → supprimé, pages d'événements `f"{site_chrome.LANG_DIRS[code]}{slug}.html"`, lien `<a href="{slug}.html">` (même dossier), boucle des équipes `(("fr/equipes", "fr"), ("teams", "en"))`, widgets `link=f"{URL}{t['teams']}/{slug}.html"`, fiche `SITE / "equipes" / f"{slug}.json"` inchangée (les fiches JSON restent dans `equipes/`, décision G), regex `visite\?p=/[a-z-]+` → `[a-z/-]+`.
- Modify: `.github/scripts/menu_partout.py` : `home_of` → `sc.home_link` ; `prefix_of` inchangé (profondeur réelle) ; `links` déjà `prefix + tables`.
- Modify: `.github/scripts/titres_seo.py` : rien (clé `/fr/jeux/valorant` → `fr/jeux/valorant.html`) ; vérifier par test.
- Modify: `.github/scripts/topplays.py`, `analytics.py`, `qr_ordinateur.py`, `bascule_appstore.py` : grep `equipes|jeux|blog-fr|live-fr|-en.html` → adapter ce qui reste.
- Test: `test_actualites.py`, `test_live.py`, `test_blog.py`, `test_menu_partout.py`, `test_titres_seo.py` : les fixtures qui nomment `actualites.html`, `blog-fr/…`, `jeux/…`, `live-fr.html` passent aux nouveaux chemins ; nouveaux tests ciblés ci-dessous.

- [ ] **Step 1 : tests nouveaux (exacts)**

```python
# actualites : page News fr fabriquée → menu : href="../fr.html#jeux", news "../fr/actualites.html"?  NON : depuis fr/actualites.html, PAGES["fr"] vu avec prefix "../" donne "../fr/actualites.html" (valide) ; canonical https://esportly.eu/fr/actualites ; visite?p=/fr/actualites ; lien "Lire l'article" "../fr/blog/<id>.html"
# live : page fr → canonical /fr/live, hreflang en /live, es /es/live ; visite?p=/fr/live ; home "../fr.html"
# blog : article fr → crumbs "../blog.html"? NON : prefix "../../" + HUBS["fr"] = "../../fr/blog.html" ; logo "../../logos-jeux/x.png" ; hub fr : cartes "blog/<id>.html", logos "../logos-jeux/" ; guide link dans fr/jeux/x.html : "../../fr/blog/<id>.html" ; sitemap : <loc>https://esportly.eu/fr/blog/valorant</loc> et hreflang
# matchs (si testé) : page d'événement fr "fr/worlds-2026.html", en "worlds-2026.html" ; lien événement depuis la semaine "worlds-2026.html"
# menu_partout : page fr/equipes/t1.html → prefix "../../", home "../../fr.html", live "../../fr/live.html"
```

Note : les liens `prefix + table` ne sont pas minimaux (`../../fr/blog.html` au lieu de `../blog.html`) mais justes ; c'est accepté (moins de code, même convention partout).

- [ ] **Step 2 : adapter les fixtures et le code jusqu'au vert complet** (`-W error`)
- [ ] **Step 3 : commit** `Générateurs : chemins des sous-dossiers de langue, préfixe calculé depuis la profondeur`

### Tâche 5 : le reste du dépôt

**Files:**
- Modify: `.github/workflows/matchs.yml` (`ls equipes/*.html` → `ls fr/equipes/*.html`)
- Modify: `.claude/skills/titres-seo/scripts/inventaire.py` (FOLDERS : `fr/blog`, `es/blog`, `de/blog`, `pt/blog`, `fr/equipes`, `fr/jeux`, `es/juegos`, `de/spiele`, `pt/jogos`, et `fr`, `es`, `de`, `pt` pour les pages racine déplacées ; SKIP avec `fr/merci.html`…), `controle.py` si des chemins y sont ; régénérer `docs/seo/inventaire-titres.csv` après la tâche 6.
- Modify: `README.md` (noms des pages News/Live/Blog, paragraphe « Adresses » : schéma des sous-dossiers, `_redirects`, `sous_dossiers.py` rejouable)
- Modify: `.assetsignore` : rien à ajouter (`_redirects` doit être envoyé) ; vérifier que `docs` y est.

- [ ] **Step 1 : faire les modifications ; `py -3.13 -m unittest discover -s .claude/skills/titres-seo/scripts` vert ; commit** `Workflow, skill titres-seo et README : sous-dossiers de langue`

### Tâche 6 : migration du vrai site et stabilité des générateurs

- [ ] **Step 1 :** `py -3.13 .github/scripts/sous_dossiers.py --essai` : attendu 260 fichiers déplacés (256 pages + 4 flux), ~N réécrits, règles : 2×252 pages + 4 flux + 8 jokers = 516 (noter le vrai compte).
- [ ] **Step 2 :** `py -3.13 .github/scripts/sous_dossiers.py` ; `git status` : plus aucun `jeux/`, `equipes/`, `blog-*/`, `live-*.html`… ; `git add -A`.
- [ ] **Step 3 : stabilité** (chacun doit ne rien changer) : `py -3.13 .github/scripts/blog.py --essai`, `py -3.13 .github/scripts/actualites.py --essai` (avec `PYTHONTZPATH=C:\Users\horny\anaconda3\Lib\site-packages\pytz\zoneinfo`), `py -3.13 .github/scripts/titres_seo.py --check`, `py -3.13 .github/scripts/menu_partout.py --check`, `py -3.13 .github/scripts/analytics.py` et `qr_ordinateur.py` (0 page). Si un générateur veut changer quelque chose : c'est un écart entre le script de migration et le générateur ; corriger le générateur ou le script (pas la page à la main), puis rejouer depuis `git checkout -- . && git clean -fd` de la tâche 6.
- [ ] **Step 4 : contrôles globaux** : aucun `href`/`src` relatif cassé (script de vérification jetable dans le scratchpad : résoudre chaque lien relatif de chaque page et vérifier que le fichier existe) ; `grep -r "esportly.eu/jeux/\|esportly.eu/blog-fr\|esportly.eu/live-fr\|/equipes/" --include=*.html --include=*.xml` ne trouve rien hors `_redirects` ; canonical de chaque page déplacée = sa nouvelle adresse ; hreflang de chaque page pointe vers des fichiers existants ; `sitemap.xml` : 260 `<loc>` tous existants.
- [ ] **Step 5 : navigateur intégré** (serveur statique local du dépôt, `py -3.13 -m http.server` depuis la racine, avec `.html` dans les adresses) : `/fr/live.html`, `/es/juegos/valorant.html`, `/fr/blog/valorant.html`, `/fr/actualites.html`, `/de/nachrichten.html`, `/fr.html` : menu, liens de langue, polices et logos chargés, aucun 404 dans la console.
- [ ] **Step 6 : tests complets verts ; commit** `Sous-dossiers de langue : migration des 256 pages, _redirects, sitemap, titres.json`
- [ ] **Step 7 :** régénérer `docs/seo/inventaire-titres.csv` ; commit.

### Tâche 7 : PR

- [ ] `git push -u origin sous-dossiers-langues` ; `gh pr create` vers `main` : titre « Sous-dossiers de langue /fr/, /es/, /de/, /pt/ avec redirections 301 », corps : résumé, la carte (lien vers la spec + tables des dossiers et des pages racine), le compte des règles `_redirects`, ce qui est vérifié, ce qui reste hors dépôt (§ 6 de la spec), ligne `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- [ ] Après fusion (sur accord de Johan) : `curl -s -o /dev/null -w "%{http_code} %{redirect_url}"` sur 20 adresses par langue (anciennes et `.html`), sitemap valide ; lister à Johan les actions hors dépôt.
