# Anglais par défaut sur l'accueil d'eSportly — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** `https://esportly.eu/` s'ouvre en anglais, le français passe sur `/fr.html`, et `en.html` devient une page de renvoi vers `/`.

**Architecture :** un script Python jetable et testé échange en une seule substitution les deux cibles d'accueil dans 223 fichiers, renomme les accueils et crée la page de renvoi. Une seconde étape à la main retouche quatre fichiers. Des contrôles hors dépôt prouvent que seuls les liens d'accueil ont changé.

**Tech Stack :** Python 3.13 (bibliothèque standard, `unittest`), git, `http.server`, panneau Navigateur.

**Spec :** `docs/superpowers/specs/2026-10-27-anglais-par-defaut-design.md` (les sections citées « §n » sont les siennes).

## Global Constraints

- Adresse unique : `https://esportly.eu/`. Aucun autre domaine nulle part.
- Python : `py -3.13` (le `python3` du PATH n'est que le raccourci du Store). Préfixer chaque commande Python par `PYTHONDONTWRITEBYTECODE=1` (l'état du shell ne persiste pas d'un appel à l'autre) : aucun `__pycache__` dans le dépôt.
- Script : bibliothèque standard seulement, commentaires en français, docstring avec usage et option `--essai`, comme `.github/scripts/bascule_appstore.py`.
- Octets : l'arbre de travail est en CRLF (`core.autocrlf=true`, index en LF). Lire et écrire avec `encoding="utf-8", newline=""` ; ne jamais réécrire un fichier sans lien à échanger.
- Cibles échangées (valeur entière de l'attribut, ancre conservée) : `./`→`fr.html`, `../`→`../fr.html`, `/`→`/fr.html`, `en.html`→`./`, `../en.html`→`../`, `/en.html`→`/`. Absolu : `https://esportly.eu/`→`https://esportly.eu/fr.html`, `https://esportly.eu/en.html`→`https://esportly.eu/` (précédé de `"` ou `<loc>`, suivi de `"`, `<` ou `#`).
- Profondeur : `./` et `en.html` valent à la racine seulement ; `../` et `../en.html` en sous-dossier d'un niveau seulement ; `/` et `/en.html` partout. Toute autre forme est une variante inconnue (arrêt).
- Jamais touchés : `404.html` (exclu de l'échange), la constante `URL` de `matchs.py`, `neuigkeiten.html`.
- Valeurs attendues sur l'arbre réel (`origin/main` `abea1cb`) : **223 fichiers, 731 liens échangés** (473 relatifs + 258 absolus : les 448 relatifs de la spec, plus les 28 liens `.././` normalisés en `../`, moins les 3 de `404.html`).
- Git : branche locale `anglais-par-defaut`, 5 commits, jamais de push ni de fusion. Messages en français, terminés par `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- `<scratchpad>` : dossier temporaire de la session, pour tout ce qui ne va pas dans le dépôt.

## Review Focus

1. **Fins de ligne :** les HTML et `sitemap.xml` sont en CRLF ; une réécriture en mode texte change des lignes sans bruit. Test d'aller-retour octet par octet (tâches 2 et 4) et `git diff --numstat` du sitemap (tâche 5).
2. **Forme hors profondeur** (`../` à la racine, `./` ou `en.html` en sous-dossier) : ne désigne pas l'accueil, donc signalée et jamais échangée (tâche 2).
3. **Texte non ASCII** (`’`, `·`, `→`, accents) et fichier sans retour final : octets identiques hors liens (tâche 2).
4. **Faux amis :** mention de l'adresse dans un texte courant, `neuigkeiten.html` (finit par `en.html`), `https://esportly.eu/equipes/x.html` : intacts (tâche 2).
5. **Relance** après une migration réussie ou partielle (`fr.html` seul, `index.html` déjà en anglais) : refus, rien n'est écrit (tâches 3 et 4).

## Fichiers

| Fichier | Rôle |
|---|---|
| `.github/scripts/anglais_par_defaut.py` (créé) | échange, garde-fous, page de renvoi, sitemap, contrôles, ligne de commande |
| `.github/scripts/test_anglais_par_defaut.py` (créé) | tests `unittest` du script (jetables avec lui) |
| `.assetsignore` (modifié) | ajoute `docs` |
| `404.html`, `manifest.webmanifest`, `README.md`, `.github/scripts/matchs.py` (modifiés) | retouches §8 |
| `<scratchpad>\verifier.py` (hors dépôt) | contrôles 1 à 5 et 7 de §11 |

---

### Task 1 : Spec, plan et `.assetsignore` (commit 1)

**Files :** Modify `.assetsignore` ; commit `docs/superpowers/specs/2026-10-27-anglais-par-defaut-design.md` et ce plan.

- [ ] **Étape 1 : vérifier le point de départ.** `git fetch origin && git branch --show-current && git rev-parse --short origin/main` → `anglais-par-defaut` puis `abea1cb`. Si `origin/main` a bougé : s'arrêter, `git rebase origin/main` (la branche ne contient que `docs/`), puis refaire le décompte de la tâche 5 étape 1 et mettre à jour les valeurs attendues.
- [ ] **Étape 2 : ajouter la ligne `docs` à la fin de `.assetsignore`.**
- [ ] **Étape 3 : contrôler.** `git status --short` → `M .assetsignore` et `?? docs/`.
- [ ] **Étape 4 : commit** `Spec et plan : anglais par défaut sur l'accueil` (`git add .assetsignore docs`).

### Task 2 : Cœur de l'échange

**Files :** Create `.github/scripts/anglais_par_defaut.py` (partie 1), `.github/scripts/test_anglais_par_defaut.py`.

**Interfaces :**
- Produces : `class Refus(Exception)` ; `SITE = "https://esportly.eu/"` ; `swap_links(text: str, depth: int) -> tuple[str, int]` (nouveau texte, nombre de liens échangés) ; `unswap_links(text: str, depth: int) -> str` (échange inverse : `fr.html→./`, `./→en.html`, etc.) ; `unknown_variants(text: str, depth: int) -> list[str]` (un extrait par variante inconnue). `depth` vaut 0 à la racine, 1 dans un sous-dossier.

- [ ] **Étape 1 : écrire les tests** dans `test_anglais_par_defaut.py` (`import anglais_par_defaut as ap`), classe `EchangeDesLiens` :

```python
def test_cibles_relatives(self):
    for avant, apres, depth in [('./', 'fr.html', 0), ('en.html', './', 0), ('../', '../fr.html', 1),
                                ('../en.html#jeux', '../#jeux', 1), ('/', '/fr.html', 0), ('/en.html', '/', 1)]:
        self.assertEqual(ap.swap_links(f'<a href="{avant}">', depth), (f'<a href="{apres}">', 1))
def test_cibles_absolues(self):
    self.assertEqual(ap.swap_links('<link rel="canonical" href="https://esportly.eu/">', 0)[0], '<link rel="canonical" href="https://esportly.eu/fr.html">')
    self.assertEqual(ap.swap_links('"item": "https://esportly.eu/en.html"', 1)[0], '"item": "https://esportly.eu/"')
    self.assertEqual(ap.swap_links('<loc>https://esportly.eu/en.html</loc>', 0)[0], '<loc>https://esportly.eu/</loc>')
def test_substitution_simultanee(self):
    self.assertEqual(ap.swap_links('<a href="./">a</a><a href="en.html">b</a>', 0),
                     ('<a href="fr.html">a</a><a href="./">b</a>', 2))
def test_faux_amis_intacts(self):
    for t in ['href="neuigkeiten.html"', 'href="../equipes/x.html"', 'href="https://esportly.eu/equipes/x.html"',
              'href="#jeux"', 'Voir https://esportly.eu/ pour plus']:
        self.assertEqual(ap.swap_links(t, 1), (t, 0))
def test_octets_conserves(self):
    t = '<p>Cette page n’existe pas · →</p>\r\n<a href="../">x</a>'
    self.assertEqual(ap.swap_links(t, 1)[0], t.replace('href="../"', 'href="../fr.html"'))
    self.assertEqual(ap.swap_links('é\r\nsans retour final', 0), ('é\r\nsans retour final', 0))
def test_inverse_redonne_l_original(self):
    for depth, t in [(0, '<a href="./">a</a><a href="en.html#x">b</a><a href="/">c</a>https://esportly.eu/'),
                     (1, '<a href="../">a</a><a href="../en.html">b</a>')]:
        self.assertEqual(ap.unswap_links(ap.swap_links(t, depth)[0], depth), t)
def test_variantes_inconnues(self):
    for t, depth in [('href="index.html"', 0), ("href='./'", 0), ('href="/./"', 0), ('href="../../"', 1),
                     ('<a href="../">', 0), ('<a href="./">', 1), ('<a href="en.html">', 1),
                     ('<link href="https://esportly.eu/?x=1">', 0)]:
        self.assertTrue(ap.unknown_variants(t, depth), t)
    self.assertEqual(ap.unknown_variants('<a href="./">x</a><link href="https://esportly.eu/">', 0), [])
```

- [ ] **Étape 2 : lancer.** `py -3.13 -m unittest discover -s .github/scripts -p "test_anglais_par_defaut.py" -v` → échec `ModuleNotFoundError: No module named 'anglais_par_defaut'`.
- [ ] **Étape 3 : implémenter** `Refus`, `SITE`, `swap_links`, `unswap_links`, `unknown_variants` dans `anglais_par_defaut.py`, avec la docstring d'usage (`--essai`). Une seule expression régulière par famille (relative, absolue) avec fonction de rappel, pour que l'échange se fasse en un passage ; la famille relative dépend de `depth` ; l'absolue utilise `(?<=")|(?<=<loc>)` en amont et `(?=["<#])` en aval.
- [ ] **Étape 4 : relancer** la commande de l'étape 2 → `OK` (7 tests). Pas de commit : le script est commité à la fin de la tâche 4.

### Task 3 : Garde-fous, page de renvoi, sitemap, contrôles internes

**Files :** Modify `anglais_par_defaut.py` (partie 2) et `test_anglais_par_defaut.py`.

**Interfaces :**
- Consumes : `Refus`, `SITE`.
- Produces : `check_start_state(root: Path) -> None` (lève `Refus`) ; `renvoi_page() -> str` ; `set_homes_lastmod(sitemap: str, today: str) -> str` ; `check_postconditions(files: dict[str, str]) -> list[str]` (clés = chemins POSIX relatifs sous leur **nom final** : `index.html` anglais, `fr.html`, `en.html` renvoi, `es.html`, `de.html`, `pt.html`, `sitemap.xml` ; messages commençant par `canonical`, `hreflang`, `sitemap` ou `lang`).

- [ ] **Étape 1 : écrire les tests** (classes `GardeFous`, `RenvoiEtSitemap`, `ControlesInternes` ; helper `tree()` qui construit 5 accueils conformes à §5 et un sitemap sans `/en.html`) :

```python
def test_etat_de_depart_ok(self):          # index lang="fr" + en.html lang="en" -> aucune exception
def test_refus_fr_html_existe(self):       # avec fr.html présent -> with self.assertRaises(ap.Refus)
def test_refus_index_deja_en_anglais(self):    # index.html en lang="en" -> Refus
def test_refus_fichier_manquant(self):     # sans en.html -> Refus
def test_renvoi(self):
    p = ap.renvoi_page()
    for s in ['<html lang="en">', '<link rel="canonical" href="https://esportly.eu/">', '<meta http-equiv="refresh" content="0; url=./">', 'href="./"']:
        self.assertIn(s, p)
    for s in ['noindex', 'hreflang']:
        self.assertNotIn(s, p)
def test_lastmod_des_accueils_seulement(self):   # sitemap CRLF : 5 accueils + /equipes/x.html à 2026-10-13
    out = ap.set_homes_lastmod(s, '2026-10-27')
    self.assertEqual(out.count('2026-10-27'), 5); self.assertEqual(out.count('2026-10-13'), 1); self.assertNotIn('\n', out.replace('\r\n', ''))
def test_controles_ok(self):               self.assertEqual(ap.check_postconditions(tree()), [])
def test_controle_canonical(self):         # canonical de fr.html faux -> une ligne commençant par "canonical"
def test_controle_hreflang(self):          # accueil sans auto-référence ou jeu incomplet -> "hreflang"
def test_controle_sitemap(self):           # <loc>…/en.html</loc> présent -> "sitemap"
def test_controle_lang(self):              # index.html en lang="fr" -> "lang"
```

- [ ] **Étape 2 : lancer** → les nouveaux tests échouent (`AttributeError`).
- [ ] **Étape 3 : implémenter** les quatre fonctions. `renvoi_page` : page minimale de §7 (CSP sans script, `img-src 'self'` pour l'icône, retours à la ligne `\n`). `set_homes_lastmod` : ne modifie que le `<lastmod>` qui suit le `<loc>` des 5 accueils (`SITE`, `SITE+"fr.html"`, `es.html`, `de.html`, `pt.html`), en conservant les fins de ligne. `check_postconditions` : contrôles de §9 (canonical, `lang`, jeu hreflang identique sur les 5 accueils avec auto-référence, sitemap sans `/en.html` et avec `/` et `/fr.html`).
- [ ] **Étape 4 : relancer** toute la suite → `OK`.

### Task 4 : Orchestration et ligne de commande (commit 2)

**Files :** Modify `anglais_par_defaut.py`, `test_anglais_par_defaut.py`.

**Interfaces :**
- Consumes : toutes les fonctions des tâches 2 et 3.
- Produces : `migrate(root: Path, today: str, trial: bool) -> tuple[int, int]` (fichiers changés, liens échangés ; lève `Refus`) ; `ROOT: Path` (`Path(__file__).resolve().parents[2]`, comme `bascule_appstore.py`) ; `main(argv: list[str], root: Path = ROOT) -> int` (0 si tout va bien ; 1 sur `Refus`, message sur stderr ; `root` permet aux tests de travailler sur un site temporaire). Sortie : `N fichier(s) à changer, M lien(s) d'accueil échangé(s).` (`changé(s)` hors `--essai`).

Comportement de `migrate` : périmètre = `*.html` (tous niveaux) et `*.xml` de la racine, hors `.git` et `404.html` ; `depth` = nombre de dossiers du chemin ; 1) `check_start_state` ; 2) `unknown_variants` sur tout le périmètre, `Refus` listant `chemin : extrait` ; 3) échange en mémoire, puis `set_homes_lastmod` sur le sitemap ; 4) `check_postconditions` sur les contenus sous leurs noms finaux (`fr.html` = ancien `index.html` échangé, `index.html` = ancien `en.html` échangé, `en.html` = `renvoi_page()`) ; 5) hors `--essai` seulement : écrire les fichiers modifiés à leur chemin d'origine, renommer `index.html`→`fr.html` puis `en.html`→`index.html`, écrire le renvoi dans `en.html`.

- [ ] **Étape 1 : écrire les tests** (classe `Migration`, helper `site(tmp)` : `index.html` fr, `en.html`, `es/de/pt.html`, `equipes/a.html` (lien `../`), `teams/a.html` (lien `../en.html`), `404.html`, `sitemap.xml` en CRLF) :

```python
def test_essai_n_ecrit_rien(self):          # migrate(root, '2026-10-27', True) -> (n>0, m>0) ; hash de l'arbre inchangé
def test_migration_complete(self):
    # fr.html lang="fr" avec ses liens échangés ; index.html lang="en" ; en.html == ap.renvoi_page()
    # equipes/a.html contient href="../fr.html" ; teams/a.html contient href="../" ; 404.html octet pour octet inchangé
    # sitemap.xml encore en CRLF, 5 lastmod = 2026-10-27
def test_inverse_redonne_l_original(self):  # unswap_links(chaque fichier migré, depth) == original (fr.html<-index, index<-en)
def test_deuxieme_execution_refusee(self):  # second migrate -> Refus ; arbre identique après l'échec
def test_rien_ecrit_si_variante_inconnue(self):  # ajouter href="index.html" -> Refus ; pas de fr.html, arbre inchangé
def test_main(self):                        # main(['--essai'], root) == 0 ; main([], root) == 0 ; main([], root) == 1 (stderr non vide)
```

- [ ] **Étape 2 : lancer** → échec (`AttributeError: module 'anglais_par_defaut' has no attribute 'migrate'`).
- [ ] **Étape 3 : implémenter** `migrate` et `main` (`main` lit `--essai` dans `argv`, `today = date.today().isoformat()`, racine = `ROOT` comme dans `bascule_appstore.py`).
- [ ] **Étape 4 : relancer** toute la suite → `OK`.
- [ ] **Étape 5 : commit 2** `Script de migration : anglais par défaut sur l'accueil (jetable après fusion)` avec `git add .github/scripts/anglais_par_defaut.py .github/scripts/test_anglais_par_defaut.py` (chemins explicites).

### Task 5 : Exécution sur le site réel (commit 3)

**Files :** modifie 223 fichiers existants, crée `fr.html`.

- [ ] **Étape 1 : répétition.** `git status --short` (vide) puis `py -3.13 .github/scripts/anglais_par_defaut.py --essai` → `223 fichier(s) à changer, 731 lien(s) d'accueil échangé(s).` et `git status --short` toujours vide. Un autre nombre ou un `Refus` : s'arrêter et comprendre (le dépôt a bougé, ou une variante inconnue est apparue) avant de continuer.
- [ ] **Étape 2 : exécution réelle** (même commande sans `--essai`) → `223 fichier(s) changé(s), 731 lien(s) d'accueil échangé(s).`
- [ ] **Étape 3 : contrôles :**
  - `git status --short | wc -l` → `224` (223 modifiés + `fr.html`) ;
  - `git diff --numstat -- sitemap.xml` → `22	22	sitemap.xml` (aucune réécriture complète du fichier) ;
  - `grep -c '<html lang="en"' index.html`, `grep -c '<html lang="fr"' fr.html` → `1` chacun ;
  - `git diff --quiet -- 404.html` → code de sortie 0 ;
  - `head -c 600 en.html` montre la page de renvoi.
- [ ] **Étape 4 : commit 3** `Accueil : anglais par défaut sur /, français sur /fr.html` avec `git add -u && git add fr.html` ; corps : 223 fichiers, 731 liens échangés, `index.html` ↔ `fr.html`, `en.html` devient un renvoi vers `/`.

### Task 6 : Retouches hors échange (commit 4)

**Files :** Modify `404.html`, `manifest.webmanifest`, `README.md`, `.github/scripts/matchs.py:70`.

- [ ] **Étape 1 : contrôles qui échouent.** `grep -c "Page not found" 404.html` → `0` ; `grep -c '"lang": "en"' manifest.webmanifest` → `0` ; `grep -c '"fr": "fr.html"' .github/scripts/matchs.py` → `0`.
- [ ] **Étape 2 : `404.html`.** Remplacer `<html lang="fr">` par `<html lang="en">` ; le titre par `Page not found – eSportly` ; les trois `content="Cette page n’existe pas."` / `content="Page introuvable – eSportly"` (description, `og:title`, `og:description`) par `This page doesn’t exist.` / `Page not found – eSportly` ; le lien de la marque `href="/./"` par `href="/"` ; puis remplacer la ligne `<main …>` (ligne 43) et la ligne `<footer …>` (ligne 44), chacune d'un seul tenant, par (texte fixé par §8). Le fichier est en CRLF : remplacer ligne par ligne, sans jamais inclure le retour à la ligne dans le texte cherché.

```html
<main class="wrap"><section class="hero"><span class="big" aria-hidden="true">404</span><div class="kicker">404</div><h1>Page not found</h1><p class="lead">This page doesn’t exist or no longer exists. <span lang="fr">Cette page n’existe pas ou plus.</span></p><a class="cta" href="/">Back to home</a><a class="cta2" href="/fr.html" lang="fr">Retour à l’accueil</a></section><h2>Shortcuts</h2><nav class="others"><a href="/#jeux">The 14 games</a><a href="/teams.html">All teams</a><a href="https://lmavqchwevcvvneblqld.supabase.co/functions/v1/visite?p=/404&amp;go=testflight">Join the beta</a><a href="/press.html">Press</a></nav></main>
<footer><div class="wrap">eSportly is not affiliated with any game publisher, league or team. Published by ProtoJo Digital. · <a href="/privacy.html">Privacy</a> · <a href="/mentions-legales.html">Legal notice</a></div></footer>
```

- [ ] **Étape 3 : `manifest.webmanifest`** : `"lang": "en"` et `"description": "Your esports team, every match, right on time."`.
- [ ] **Étape 4 : `README.md`** : ajouter après les deux puces existantes `- \`index.html\` : accueil en anglais (langue par défaut) ; \`fr.html\` : accueil en français ; \`en.html\` : renvoi vers \`/\` (ancienne adresse de l'accueil anglais)`.
- [ ] **Étape 5 : `matchs.py` ligne 70** : `HOME = {"fr": "fr.html", "en": "./", "es": "es.html", "de": "de.html", "pt-BR": "pt.html"}` ; `URL` inchangée.
- [ ] **Étape 6 : contrôles qui passent :** les trois `grep` de l'étape 1 donnent `1` ou plus ; `py -3.13 -c "import json;json.load(open('manifest.webmanifest',encoding='utf-8'))"` sans erreur ; `py -3.13 -c "import ast;ast.parse(open('.github/scripts/matchs.py',encoding='utf-8').read())"` sans erreur ; `git diff --stat` ne liste que ces 4 fichiers.
- [ ] **Étape 7 : commit 4** `Retouches : 404 en anglais d'abord, manifeste, README, HOME de matchs.py` (chemins explicites).

### Task 7 : Contrôles statiques (contrôles 1 à 5 de §11, hors dépôt)

**Files :** Create `<scratchpad>\verifier.py`.

**Interfaces :**
- Consumes : `unswap_links` de `.github/scripts/anglais_par_defaut.py` (import par `sys.path`).
- Produces : `check_exactitude(avant: Path, apres: Path) -> list[str]` ; `check_liens(avant: Path, apres: Path) -> list[str]` ; `check_hreflang(root: Path) -> list[str]` ; `check_sitemap(root: Path) -> list[str]` ; `check_accueils(root: Path) -> list[str]` ; `main(avant, apres)` affiche `OK <n°>` ou les lignes de problème, code 1 s'il y en a.

- [ ] **Étape 1 : exporter les deux arbres** sans métadonnées git : `git archive origin/main | tar -x -C <scratchpad>\avant` et `git archive HEAD | tar -x -C <scratchpad>\apres` (dossiers créés vides avant).
- [ ] **Étape 2 : écrire `verifier.py`** avec ces critères :
  - exactitude : pour chaque fichier `.html` et `.xml` d'`avant` (`index.html`→`fr.html`, `en.html`→`index.html` côté `apres` ; `depth` = nombre de dossiers du chemin), `unswap_links(apres, depth) == avant` ; tous les autres fichiers (images, JSON, workflows…) sont comparés octet pour octet ; exceptions : `404.html`, `manifest.webmanifest`, `README.md`, `.github/scripts/matchs.py`, le script, son test, `.assetsignore`, `docs/`, le nouveau `en.html`, et les `<lastmod>` du sitemap (masqués avant comparaison) ;
  - liens : chaque `href`/`src` relatif ou en `/…` (hors `http(s):`, `mailto:`, `webcal:`, `tel:`, `data:`, `#`) est résolu sur le disque (dossier de la page, ou racine pour `/`) ; pour chaque cible introuvable, son nombre d'occurrences dans `apres` ne dépasse pas celui de `avant` ;
  - hreflang : pour toute page qui en porte, son canonical figure dans son jeu (auto-référence) ; chaque URL du jeu mène à un fichier existant dont le canonical est cette URL ; la cible contient en retour un hreflang vers cette page ; pour les 5 accueils, `x-default` = `https://esportly.eu/` ;
  - sitemap : XML valide, 175 `<url>`, chaque `<loc>` = canonical du fichier qu'il désigne, `/` et `/fr.html` présents, aucun `/en.html` ;
  - accueils : `index.html` (`lang="en"`, canonical `/`), `fr.html` (`lang="fr"`, canonical `/fr.html`), `en.html` (canonical `/`, `refresh` vers `./`).
- [ ] **Étape 3 : lancer** `py -3.13 <scratchpad>\verifier.py <scratchpad>\avant <scratchpad>\apres` → cinq lignes `OK` et code 0. Toute ligne de problème : relancer la même vérification sur `avant` ; seul un problème absent d'`avant` est une régression à corriger (puis refaire les tâches concernées).

### Task 8 : Exécutions jumelles (contrôle 7 de §11)

- [ ] **Étape 1 : `zoneinfo`.** `py -3.13 -c "import zoneinfo;zoneinfo.ZoneInfo('Europe/Paris')"`. Si cela échoue : demander l'accord à l'utilisateur, puis `py -3.13 -m venv <scratchpad>\venv` et `<scratchpad>\venv\Scripts\python -m pip install tzdata` (rien d'installé hors de ce dossier). Dans la suite, `PY` = cet interpréteur ou `py -3.13`.
- [ ] **Étape 2 : copies fraîches** (même méthode `git archive`) dans `<scratchpad>\jumeau-avant` (`origin/main`) et `<scratchpad>\jumeau-apres` (`HEAD`).
- [ ] **Étape 3 : `matchs.py`.** Dans chaque copie, l'un juste après l'autre, en arrière-plan avec journal : `PY .github/scripts/matchs.py`. Il lit les calendriers publics du serveur d'eSportly (requêtes en lecture seule). Dernière ligne attendue dans les deux journaux : `83 équipes, <N> matchs cette semaine, <M> résultats` avec les mêmes N et M. Si N ou M diffèrent (match commencé entre les deux), relancer les deux.
- [ ] **Étape 4 : comparer.** `check_exactitude(jumeau-avant, jumeau-apres)` de `verifier.py` → liste vide.
- [ ] **Étape 5 : bascule.** `PY .github/scripts/bascule_appstore.py --essai` dans chaque copie (aucune écriture, aucun réseau), sorties dans deux fichiers. Dans la sortie d'`avant`, remplacer `index.html`→`fr.html` puis `en.html`→`index.html` **sur mots entiers** (`\bindex\.html`, `\ben\.html`, jamais en sous-chaîne : `neuigkeiten.html` finit par `en.html`), puis comparer : identiques, dont la ligne `N fichier(s) à changer.`

### Task 9 : Rendu local et bilan (contrôle 8 de §11)

- [ ] **Étape 1 : serveur.** `py -3.13 -m http.server 8123 --directory <scratchpad>\apres` en arrière-plan.
- [ ] **Étape 2 : panneau Navigateur.**
  - `http://localhost:8123/` : `document.documentElement.lang` → `en`, `document.title` → `eSportly · Your esports team, every match, right on time`.
  - `http://localhost:8123/fr.html` : `lang` → `fr`, titre français. Cliquer « English » dans le menu de langue → l'adresse devient `http://localhost:8123/`. Cliquer « Français » → `/fr.html`.
  - `http://localhost:8123/en.html` : finit sur `/`.
  - `http://localhost:8123/404.html` : anglais d'abord, avec la phrase française.
  - Gabarit mobile (`resize_window` `mobile`) sur `/` et `/fr.html` : `document.documentElement.scrollWidth <= window.innerWidth`.
  - `read_console_messages` en erreurs seulement : aucune.
  - Remettre le gabarit `desktop`.
- [ ] **Étape 3 : arrêter le serveur** (`TaskStop`), puis `git status --short` → vide et `git log --oneline origin/main..HEAD` → 5 commits.
- [ ] **Étape 4 : bilan à l'utilisateur** : résultats des 8 contrôles ; les trois adresses à ouvrir après déploiement (`/`, `/fr`, `/en`) ; les suites : supprimer le script et son test après la fusion, traiter les URL `.html` redirigées par Cloudflare, confirmer la source des pages avec le propriétaire, choisir la date de fusion (pas le 2 novembre), décider du push ou de la pull request. Mettre à jour la mémoire du projet (`esportly-site-anglais-par-defaut`) : implémenté en local, 4 commits, rien de poussé.

---

**Si `origin/main` avance avant la livraison** (robot du matin, travail de l'équipe) : `git fetch origin`, recréer `anglais-par-defaut-2` depuis `origin/main` avec `--no-track`, y reprendre les commits 1 et 2 (`git cherry-pick`), relancer le script (tâche 5) pour refaire le commit 3, puis reprendre le commit 4 (`git cherry-pick`, conflits possibles seulement dans `404.html`, `manifest.webmanifest`, `README.md` et `matchs.py`). Refaire ensuite les tâches 7 à 9.

---

## Addendum après la revue fraîche (27 octobre)

Le relecteur a trouvé trois défauts (journal d'exécution, lignes `Final:`), corrigés par un rejeu complet sur une nouvelle branche, selon la procédure de relance ci-dessus (l'ancienne branche reste sous `anglais-par-defaut-v1`) :

1. **Critique, `.././` :** 14 pages `jeux/` portaient `href=".././"` et `href=".././#jeux"` (28 liens), ni échangés ni signalés. Corrigé par une règle générique de résolution dans `unknown_variants` (§9) et par un commit préalable qui normalise ces liens en `../` et `../#jeux`.
2. **Important, `"url"` JSON-LD des accueils :** `own_url(text, canonical)` remet le `"url"` d'un accueil à son propre canonical dans `migrate` ; `check_postconditions` le vérifie.
3. **Important, écriture partielle :** tout lien vers `fr.html` avant la migration est une forme inconnue (`Refus`).

Ordre des 5 commits : spec et plan, normalisation `.././`, script et tests, résultat mécanique, retouches. Valeurs attendues : 223 fichiers, 731 liens. Vérificateur : contrôle 9 ajouté (langue des liens d'accueil) et exception du `"url"` pour l'exactitude ; les jumeaux sont rejoués sur les nouveaux arbres.
