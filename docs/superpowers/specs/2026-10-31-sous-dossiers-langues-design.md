# Sous-dossiers de langue pour esportly.eu : carte des adresses (31/10/2026)

Décision de Johan (31/10) : « j'ai plein d'URL qui sont indexées et qui n'ont pas de sous-dossiers dans les langues. Je veux bien
le FR, le ES, je veux bien que tout soit bien fait. » Proposition acceptée en principe : l'anglais reste à la racine, les quatre autres
langues passent sous `/fr/`, `/es/`, `/de/`, `/pt/` en gardant leurs chemins traduits, chaque ancienne adresse redirige en 301.

Ce document est la carte complète ancienne adresse → nouvelle adresse, à valider avant d'écrire une ligne de code. Elle est produite
depuis l'inventaire réel du dépôt (la langue de chaque page est lue dans son `<html lang>`), au commit de `main` du 31/10 après la
fusion de la PR 26 (menu sur toutes les pages).

## 1. Ce qui ne bouge pas

- **L'anglais** : `/`, `/games/…`, `/teams/…`, `/blog`, `/blog/…`, `/news`, `/live`, `/matches-this-week`, `/whats-new`, `/press`,
  `/privacy`, `/terms`, `/accessibility`, `/thanks`, `/check-email`, `/unsubscribed`, `/signup-error`, `/404`, `whats-new.xml`.
- **Les cinq accueils** : `/`, `/fr`, `/es`, `/de`, `/pt` (fichiers `index.html`, `fr.html`, `es.html`, `de.html`, `pt.html`,
  qui restent à la racine). Voir la décision A.
- **Les pages de renvoi vers l'app** : `match.html` (liens de match partagés, `?id=`), `tv-equipes.html`, `en.html` (renvoi vers `/`).
- **Les widgets** `widget/en/…` et `widget/fr/…` (cadres intégrés ailleurs ; leurs liens absolus vers les pages d'équipes sont réécrits).
- **Les fichiers communs** : `fonts/`, `logos-equipes/`, `logos-jeux/`, `couvertures/`, `ecrans/`, `appareils/`, `fonctions/`,
  `partage/` (images de partage, décision D), `analytics.js`, `qr-flottant.css`, `manifest.webmanifest`, `robots.txt`,
  `sitemap.xml` (même adresse, contenu mis à jour), `version.json`, icônes.

## 2. Décisions à confirmer

- **A. Accueils.** `/fr`, `/es`, `/de`, `/pt` restent tels quels (déjà indexés, canonical en place) : pas de passage à `/fr/` avec
  barre finale, donc aucune redirection sur les accueils. Le fichier `fr.html` reste à la racine à côté du dossier `fr/`
  (le Worker sert `/fr` depuis `fr.html` et renvoie `/fr/` vers `/fr`, comme aujourd'hui).
- **B. Événements en anglais.** Les pages anglaises prennent l'adresse nue : `/worlds-2026-en` → `/worlds-2026`,
  `/vct-champions-2026-en` → `/vct-champions-2026`, `/esl-pro-league-en` → `/esl-pro-league`. Conséquence : l'adresse `/worlds-2026`,
  aujourd'hui française, devient anglaise et **ne peut pas rediriger** vers `/fr/worlds-2026` (même adresse, nouvelle page) ; un
  visiteur venu de Google sur l'ancienne page française voit la page anglaise, avec le sélecteur de langue. C'est le même choix que
  pour `/` le 27/10. Alternative : garder `-en` sur les trois pages anglaises (adresses moins propres, aucune perte).
- **C. Flux RSS.** `nouveautes.xml`, `novedades.xml`, `neuigkeiten.xml`, `novidades.xml` passent sous leur langue
  (`/fr/nouveautes.xml`…) avec 301 ; `whats-new.xml` reste.
- **D. Images de partage.** `partage/jeux/…`, `partage/equipes/…`, `partage/semaine-*.jpg` restent où elles sont : adresses
  d'images sans valeur de référencement, et les déplacer casserait les aperçus déjà en cache sur les réseaux.
- **E. Pages de confirmation françaises.** `/merci`, `/verifie`, `/desinscrit`, `/inscription-erreur` passent sous `/fr/` avec 301.
  Si une fonction Supabase (inscription à la bêta, désinscription) renvoie vers ces adresses, elle continue de marcher par la
  redirection ; à mettre à jour hors dépôt (§ 6).
- **G. Fiches JSON des équipes.** Les 91 fichiers `equipes/<slug>.json` (données des équipes, lues par `matchs.py`, peut-être
  par l'app ; aucune page ne les référence) restent dans `equipes/` : seules les 83 pages HTML passent sous `fr/equipes/`.
  Pour ce dossier, `_redirects` n'a donc pas de règle à joker, seulement les 83 règles explicites (plus leurs formes `.html`).
- **F. Chaîne `.html`.** Les anciennes adresses en `.html` (`/live-fr.html`) ont chacune leur règle 301 directe vers la nouvelle
  adresse (sans passer par le renvoi 307 actuel du Worker). Les nouvelles adresses en `.html` (`/fr/live.html`) continuent d'être
  renvoyées vers la forme sans `.html` par le Worker, comme aujourd'hui.

## 3. Carte des pages déplacées (256 adresses)

Adresses publiées sans `.html` (le Worker sert les `.html`). Fichiers : `/fr/jeux/valorant` = `fr/jeux/valorant.html`.

### Français (18 pages à la racine + 111 dans des dossiers)

| Aujourd'hui | Demain |
|---|---|
| `/accessibilite` | `/fr/accessibilite` |
| `/actualites` | `/fr/actualites` |
| `/blog-fr` | `/fr/blog` |
| `/cgu` | `/fr/cgu` |
| `/confidentialite` | `/fr/confidentialite` |
| `/desinscrit` | `/fr/desinscrit` |
| `/equipes` | `/fr/equipes` |
| `/esl-pro-league` | `/fr/esl-pro-league` |
| `/inscription-erreur` | `/fr/inscription-erreur` |
| `/live-fr` | `/fr/live` |
| `/matchs-de-la-semaine` | `/fr/matchs-de-la-semaine` |
| `/mentions-legales` | `/fr/mentions-legales` |
| `/merci` | `/fr/merci` |
| `/nouveautes` | `/fr/nouveautes` |
| `/presse` | `/fr/presse` |
| `/vct-champions-2026` | `/fr/vct-champions-2026` |
| `/verifie` | `/fr/verifie` |
| `/worlds-2026` | `/fr/worlds-2026` |

### Espagnol (12 pages à la racine + 28 dans des dossiers)

| Aujourd'hui | Demain |
|---|---|
| `/accesibilidad` | `/es/accesibilidad` |
| `/blog-es` | `/es/blog` |
| `/esl-pro-league-es` | `/es/esl-pro-league` |
| `/live-es` | `/es/live` |
| `/noticias` | `/es/noticias` |
| `/novedades` | `/es/novedades` |
| `/partidos-de-la-semana` | `/es/partidos-de-la-semana` |
| `/prensa` | `/es/prensa` |
| `/privacidad` | `/es/privacidad` |
| `/terminos` | `/es/terminos` |
| `/vct-champions-2026-es` | `/es/vct-champions-2026` |
| `/worlds-2026-es` | `/es/worlds-2026` |

### Allemand (12 pages à la racine + 28 dans des dossiers)

| Aujourd'hui | Demain |
|---|---|
| `/barrierefreiheit` | `/de/barrierefreiheit` |
| `/blog-de` | `/de/blog` |
| `/datenschutz` | `/de/datenschutz` |
| `/esl-pro-league-de` | `/de/esl-pro-league` |
| `/live-de` | `/de/live` |
| `/nachrichten` | `/de/nachrichten` |
| `/neuigkeiten` | `/de/neuigkeiten` |
| `/nutzungsbedingungen` | `/de/nutzungsbedingungen` |
| `/pressebereich` | `/de/pressebereich` |
| `/spiele-der-woche` | `/de/spiele-der-woche` |
| `/vct-champions-2026-de` | `/de/vct-champions-2026` |
| `/worlds-2026-de` | `/de/worlds-2026` |

### Portugais du Brésil (12 pages à la racine + 28 dans des dossiers)

| Aujourd'hui | Demain |
|---|---|
| `/acessibilidade` | `/pt/acessibilidade` |
| `/blog-pt` | `/pt/blog` |
| `/esl-pro-league-pt` | `/pt/esl-pro-league` |
| `/imprensa` | `/pt/imprensa` |
| `/live-pt` | `/pt/live` |
| `/novidades` | `/pt/novidades` |
| `/partidas-da-semana` | `/pt/partidas-da-semana` |
| `/privacidade` | `/pt/privacidade` |
| `/termos` | `/pt/termos` |
| `/ultimas-noticias` | `/pt/ultimas-noticias` |
| `/vct-champions-2026-pt` | `/pt/vct-champions-2026` |
| `/worlds-2026-pt` | `/pt/worlds-2026` |

### Anglais (décision B, 3 pages)

| Aujourd'hui | Demain |
|---|---|
| `/esl-pro-league-en` | `/esl-pro-league` |
| `/vct-champions-2026-en` | `/vct-champions-2026` |
| `/worlds-2026-en` | `/worlds-2026` |

### Dossiers (chaque page du dossier suit, même nom de fichier)

| Aujourd'hui | Demain | Pages |
|---|---|---|
| `/jeux/<page>` | `/fr/jeux/<page>` | 14 |
| `/equipes/<page>` | `/fr/equipes/<page>` | 83 |
| `/blog-fr/<page>` | `/fr/blog/<page>` | 14 |
| `/juegos/<page>` | `/es/juegos/<page>` | 14 |
| `/blog-es/<page>` | `/es/blog/<page>` | 14 |
| `/spiele/<page>` | `/de/spiele/<page>` | 14 |
| `/blog-de/<page>` | `/de/blog/<page>` | 14 |
| `/jogos/<page>` | `/pt/jogos/<page>` | 14 |
| `/blog-pt/<page>` | `/pt/blog/<page>` | 14 |

### Flux RSS (décision C)

| Aujourd'hui | Demain |
|---|---|
| `/nouveautes.xml` | `/fr/nouveautes.xml` |
| `/novedades.xml` | `/es/novedades.xml` |
| `/neuigkeiten.xml` | `/de/neuigkeiten.xml` |
| `/novidades.xml` | `/pt/novidades.xml` |

## 4. Redirections

Fichier `_redirects` à la racine du dépôt (format des Workers Assets de Cloudflare : `source destination 301`, lu par le Worker
et jamais servi ; limite 2 000 règles fixes et 100 règles à joker ; nous en aurons environ 512 fixes et 8 à joker).
Pour chaque adresse de la carte : une règle pour l'adresse publiée (`/live-fr /fr/live 301`) et une pour sa forme `.html`
(`/live-fr.html /fr/live 301`). À la fin, huit règles à joker de secours pour les dossiers (pas `equipes`, décision G) (`/jeux/* /fr/jeux/:splat 301`…),
pour une page qui n'existerait pas encore au moment de la carte. Les redirections sont appliquées avant toute autre réponse.
`wrangler.jsonc` ne change pas (pas de code de Worker).

## 5. Ce qui change dans le dépôt

1. Script rejouable `.github/scripts/sous_dossiers.py` (+ `test_sous_dossiers.py`) : déplace les fichiers de la carte, réécrit dans
   toutes les pages (y compris anglaises, accueils, widgets, 404) chaque lien relatif ou absolu vers une adresse déplacée (`href`,
   `src`, `url()` du CSS en ligne, `canonical`, `hreflang`, `og:url`, `"url"`/`"item"` des données JSON-LD, `visite?p=`, RSS,
   `sitemap.xml`), recalcule la profondeur des liens relatifs des pages déplacées (`../fonts/` → `../../fonts/`), écrit `_redirects`,
   renomme les clés de `seo/titres.json`. Fins de ligne CRLF conservées, CSP inchangées (aucun script ajouté). `--essai` montre ce
   qui changerait ; refuse de tourner deux fois.
2. Générateurs et leurs tables : `site_chrome.py` (HUBS, LIVE_PAGES, BLOG_DIRS, GAME_DIRS, préfixes), `blog.py`, `actualites.py`
   (PAGES, TEMPLATES, WEEKLY, EVENT_SUFFIX), `matchs.py` (LANGS file/news, EXTRA ev_suffix, pages d'équipes `equipes/` → `fr/equipes/`),
   `live.py`, `menu_partout.py`, `titres_seo.py`, `analytics.js` (lien « Confidentialité » des 4 langues), `qr_ordinateur.py`,
   `bascule_appstore.py`, le skill `titres-seo` (FOLDERS de l'inventaire), les workflows (`ls equipes/*.html` du réveil des
   calendriers), le README.
3. Après le script : `blog.py`, `actualites.py`, `titres_seo.py --check`, `menu_partout.py` ne changent plus rien ; tests verts.

## 6. Hors dépôt (à faire par Johan après la mise en ligne)

- **App iOS** (dépôt de l'app, dossier `Site/` et liens vers le site) : nouvelles adresses des pages fr/es/de/pt ; les anciennes
  redirigent en 301 en attendant.
- **Supabase** : fonctions qui renvoient vers `/merci`, `/verifie`, `/desinscrit`, `/inscription-erreur` (décision E) ; le compteur
  `visite?p=` reçoit désormais `/fr/jeux/valorant` au lieu de `/jeux/valorant` (nouvelles clés dans les statistiques).
- **Search Console** : renvoyer le sitemap (même adresse) ; pas d'outil « changement d'adresse » (même domaine) ; surveiller les
  rapports de couverture pendant quelques semaines.
- **Réseaux et fiches** (App Store, réseaux sociaux, signatures) : liens vers les pages de langue.

## 7. Vérification

Tests unitaires, générateurs stables, navigateur intégré (menu, liens de langue, Blog, News, Live en deux langues), puis après la fusion
`curl -I` sur un échantillon de 20 adresses par langue (nouvelles en 200, anciennes en 301 vers la bonne cible, anciennes `.html`
aussi), sitemap valide, hreflang croisés cohérents.

## 8. Révision du 1er novembre 2026

Johan a répondu « Oui, sauf B et E » après la mise en ligne (PR 30 et 31). Les deux décisions sont annulées par une troisième PR :

- **B annulée** : les pages d'événements anglaises gardent leur suffixe (`/worlds-2026-en`, `/vct-champions-2026-en`,
  `/esl-pro-league-en`) ; les adresses nues `/worlds-2026`, `/vct-champions-2026`, `/esl-pro-league` (les anciennes adresses
  françaises, indexées) redirigent en 301 vers `/fr/…`, comme les autres pages françaises.
- **E annulée** : `/merci`, `/verifie`, `/desinscrit`, `/inscription-erreur` restent à la racine, sans redirection (ce sont les
  adresses des fonctions Supabase, qui ne doivent pas changer) ; les adresses `/fr/merci`… servies entre le 1er et le 2 novembre
  redirigent en 301 vers la racine.
