# Partie « News » : matchs importants et infos

- Date : 2026-10-27
- Statut : à relire par l'utilisateur
- Base : `origin/main` `af3cb2d` (27 octobre 2026), site sur `https://esportly.eu` (accès protégé par le Worker `esportly-site`)
- Branche de travail : `news` (locale, sans suivi distant)

## 1. Objectif

Ajouter au site une partie **News** qui affiche les matchs importants et les infos importantes, mises à jour au fil de l'eau :

- les **matchs importants** sont repérés automatiquement chaque matin dans les calendriers des grands événements suivis ;
- les **infos** sont écrites à la main : l'utilisateur les dit à Claude, qui les rédige dans les 5 langues et prépare le changement du site.

Le chantier est réussi quand :

1. Les 5 pages News (une par langue) et les 5 blocs « News » des accueils sont en ligne, avec hreflang, canonical et sitemap cohérents.
2. Les matchs importants se mettent à jour tout seuls dans le job du matin, sans bloquer les pages de matchs existantes.
3. Une info passe de « tu me la dis » à « en ligne » par une pull request que l'utilisateur autorise, et se retire de la même façon.
4. Un paragraphe du README explique comment publier une news.

## 2. Décisions validées (2026-10-27)

| Sujet | Décision |
|---|---|
| Alimentation | Automatique (matchs importants) et à la main (infos) |
| Approche | A : fichier de données, générateur dans le job du matin, pages statiques |
| Qu'est-ce qu'un match important | Les matchs d'un événement suivi à partir de la **date de début de ses phases finales**, réglée dans le fichier de news ; un titre qui indique une phase (« Quarterfinal », « Semifinal », « Final ») est retenu aussi. Fenêtre : de maintenant moins 3 h à maintenant plus 14 jours. *Règle corrigée le jour même : les données ne donnent la phase dans le titre que tant que les équipes sont inconnues (§4).* |
| Emplacement | Une page News par langue, un bloc de 3 entrées sur les 5 accueils, un lien « News » dans le menu et dans le pied de page |
| Langues | Les 5 (fr, en, es, de, pt-BR) ; les infos sont rédigées par Claude dans les 5 |
| Script | Autonome (`actualites.py`), séparé de `matchs.py`, lancé par une étape du job du matin avec `continue-on-error` |
| Publication d'une info | Pull request avec le fichier de news et les pages générées ; l'utilisateur autorise la fusion avec la phrase explicite |

## 3. Hors périmètre

- Flux RSS des news, traduction des noms de phase (« Semifinal » reste en anglais), recherche, commentaires.
- Affichage côté navigateur (JavaScript) et stockage dans Supabase.
- Notifications dans l'app.
- Toute modification de `matchs.py` (ses pages de matchs et d'événements ne changent pas).

## 4. État actuel (constaté le 27 octobre)

- **Existant :** « What's new » (notes de version, 5 pages et 5 flux RSS), « matchs de la semaine » (5 pages générées chaque matin par `matchs.py` à partir des pages « What's new » prises comme modèles) et 3 pages d'événements en 5 langues (`worlds-2026`, `vct-champions-2026`, `esl-pro-league`, suffixes `""`, `-en`, `-es`, `-de`, `-pt`). Il n'y a ni page News ni bloc d'actualité sur l'accueil.
- **Les calendriers d'événements** (`…/functions/v1/calendrier/evenement/<slug>.ics`) donnent pour chaque match `SUMMARY`, `DTSTART`, `DESCRIPTION` (« jeu · ligue · série »), `URL` (page `match.html?id=…`) et `STATUS`. **Constat** : la phase ne figure dans le titre que tant que les équipes sont inconnues (« Quarterfinal 1: TBD vs TBD », 7 matchs des Worlds). Dès que les équipes sont connues, le titre devient « Équipe A – Équipe B » sans phase ; VCT Champions et ESL Pro League n'ont jamais de phase dans le titre. Les fichiers de résultats (`game`, `league`, `serie`, `teams`, `score`, `date`, `id`) n'en donnent pas non plus. Les quarts des Worlds commencent le 3 novembre (première date lue dans le calendrier).
- **Job du matin** (`.github/workflows/matchs.yml`) : cron à 4 h 15 UTC (6 h 15 à Paris) et `workflow_dispatch` ; étapes : récupération du dépôt, Python 3.12, « Réveil des calendriers », `python3 .github/scripts/matchs.py`, envoi du commit « Matchs du jour » (`git add -A`, avec réessais). Groupe de concurrence `matchs`, partagé avec la bascule App Store.
- **Accueil** (5 versions) : sections `lancement` (accroche), `etapes`, `jeux`, `equipes`, `fonctions`, `appareils`, `offres`, `questions`. Menu du haut : Games, Teams, Features, Devices, eSportly+, FAQ (et le même menu dans le panneau mobile). Pied de page, liste « L'app » : …, What's new, This week's matches, Press. Style dans un seul bloc `<style>` ; CSP avec `script-src` limité à des empreintes.
- **Sitemap** : les pages de matchs et d'événements ont une entrée d'une ligne avec `<changefreq>daily</changefreq>` et les 5 liens hreflang (`x-default` vers la version anglaise).
- **Bascule App Store** (`bascule_appstore.py`) : parcourt tous les `*.html` et remplace le lien de la bêta ; les pages générées à partir des modèles en bénéficient automatiquement.

## 5. Les données : `news/news.json`

Le dossier `news/` est ajouté à `.assetsignore` : le fichier source n'est pas servi par Cloudflare.

```json
{
  "events": {
    "worlds-2026": {"knockout_from": "2026-11-03"},
    "vct-champions-2026": {"knockout_from": null},
    "esl-pro-league": {"knockout_from": null}
  },
  "items": [
    {"id": "2026-11-02-sortie-app-store", "date": "2026-11-02", "until": "2026-11-30", "pin": false,
     "link": {"page": "worlds-2026"},
     "fr": {"title": "…", "text": "…"}, "en": {…}, "es": {…}, "de": {…}, "pt-BR": {…}}
  ]
}
```

**Règles de validation** (toute violation arrête le script avec la liste des problèmes, avant d'écrire quoi que ce soit) :

- Seules les clés `events` et `items` existent au premier niveau, et aucun champ inconnu n'est toléré (cela attrape les fautes de frappe).
- `events` : la clé est le nom d'une page d'événement qui existe (`<slug>.html` à la racine) ; la valeur n'a qu'un champ, `knockout_from`, une date `AAAA-MM-JJ` ou `null`. Le nom, le jeu et la série viennent du calendrier lui-même (champ `DESCRIPTION`).
- `items[].id` : unique, `^[a-z0-9][a-z0-9-]*$`.
- `date` : `AAAA-MM-JJ` (jour de Paris). `until` (facultatif) : une date, au plus tôt égale à `date`. `pin` (facultatif) : booléen, faux par défaut.
- `link` (facultatif) : `{"page": clé}` où la clé est un slug d'événement de `events`, `weekly` ou `whats-new` ; ou `{"url": "https://…"}` sans espace. Une page est résolue dans la langue de la page qui l'affiche (événement : `<slug>` + suffixe de la langue ; `weekly` : `matchs-de-la-semaine`, `matches-this-week`, `partidos-de-la-semana`, `spiele-der-woche`, `partidas-da-semana` ; `whats-new` : `nouveautes`, `whats-new`, `novedades`, `neuigkeiten`, `novidades`, tous en `.html`). Une adresse externe porte `rel="noopener"`.
- Les 5 langues sont obligatoires, avec `title` (1 à 80 caractères) et `text` (1 à 280 caractères) ; texte simple sur une ligne, sans `<`.

**Quelles infos s'affichent.** Une info est visible si sa `date` est au plus égale à aujourd'hui (une `date` future programme la publication) et si elle n'a pas de `until` ou que `until` n'est pas dépassé (le jour `until` est inclus). Ordre : épinglées d'abord, puis `date` décroissante, puis `id`. La page en montre 20 au plus, l'accueil 3.

## 6. Les matchs importants (automatique)

Pour chaque événement de `events`, le script lit le calendrier (`read_events`), ignore les matchs annulés (`STATUS:CANCELLED`) et retient un match quand **l'une des deux conditions A ou B** est vraie **et** que la condition C l'est aussi :

- **A.** sa date de début (jour de Paris) est au moins égale à `knockout_from`, quand cette date est renseignée ;
- **B.** son titre contient `quarterfinal`, `semifinal` ou `final` (expression `\b(?:quarter|semi)?-?finals?\b`, sans tenir compte de la casse) ;
- **C.** il commence entre maintenant moins 3 h et maintenant plus 14 jours.

Les matchs retenus sont triés par heure. Un événement dont `knockout_from` est `null` n'est mis en avant que par ses titres de phase : c'est le cas de VCT Champions et d'ESL Pro League tant que l'utilisateur n'a pas donné la date.

Chaque ligne affiche le jour et l'heure de Paris, l'heure du visiteur à côté quand elle diffère (même petit script que les pages de matchs), le titre fourni (« Semifinal 2: TBD vs TBD » ou « Équipe A – Équipe B »), la description et un lien vers le match. Les titres restent donc en anglais dans toutes les langues, comme sur « matchs de la semaine ». La liste porte aussi les données structurées `SportsEvent` de ces matchs, dans la même forme que les pages de matchs.

**Calendrier indisponible.** Si la lecture d'au moins un événement échoue, la partie « matchs importants » des pages et la ligne de l'accueil gardent leur contenu de la veille (elles sont encadrées de marqueurs pour pouvoir être reprises telles quelles). Les infos manuelles sont toujours régénérées.

## 7. Les pages News

| Langue | Fichier | Titre court | Modèle |
|---|---|---|---|
| en (défaut, `x-default`) | `news.html` | News | `whats-new.html` |
| fr | `actualites.html` | Actualités | `nouveautes.html` |
| es | `noticias.html` | Noticias | `novedades.html` |
| de | `nachrichten.html` | Nachrichten | `neuigkeiten.html` |
| pt-BR | `ultimas-noticias.html` | Notícias | `novidades.html` |

**Fabrication** (même méthode que `matchs.py` pour les pages de la semaine) : la page « What's new » de la langue sert de modèle ; ses liens de langue, canonical et hreflang sont redirigés vers les 5 pages News ; le lien RSS est retiré ; `<title>`, description, `og:title` et `og:description` sont remplacés (l'image `og:image` du modèle est gardée) ; le paramètre `visite?p=/` du lien de la bêta devient le nom de la page ; le contenu de `<main class="wrap">` est remplacé ; le style des listes de matchs est ajouté si absent ; le petit script d'heure locale, son style et son empreinte CSP sont ajoutés comme sur les pages de matchs.

**Contenu de `<main>`** : l'accroche (`hero` : kicker, titre, phrase d'introduction, bouton), la partie « Matchs importants » (liste, ou message s'il n'y en a pas, puis la mention du fuseau), la partie « Dernières infos » (liste ou message), les données structurées. Chaque info a un `id` HTML (lien direct), sa date, son titre, son texte et, si elle a un lien, « En savoir plus ».

| | en | fr | es | de | pt-BR |
|---|---|---|---|---|---|
| Kicker | News | Actualités | Noticias | Nachrichten | Notícias |
| Titre | News and big matches | Actualités et grands matchs | Noticias y grandes partidos | Nachrichten und große Matches | Notícias e grandes partidas |
| Phrase | The matches you can't miss and the news that matters, updated as they happen. | Les matchs à ne pas manquer et les infos qui comptent, mises à jour au fil de l'eau. | Los partidos que no te puedes perder y las noticias que importan, al momento. | Die Matches, die du nicht verpassen solltest, und die Neuigkeiten, die zählen, laufend aktualisiert. | As partidas imperdíveis e as notícias que importam, em tempo real. |
| Bouton | Get alerted before every match | Être prévenu avant chaque match | Recibe un aviso antes de cada partido | Vor jedem Match benachrichtigt werden | Seja avisado antes de cada partida |
| Partie matchs | Important matches | Matchs importants | Partidos importantes | Wichtige Matches | Partidas importantes |
| Partie infos | Latest news | Dernières infos | Últimas noticias | Aktuelle Meldungen | Últimas notícias |
| Aucun match | No important match in the next 14 days. | Aucun match important dans les 14 prochains jours. | Ningún partido importante en los próximos 14 días. | Keine wichtigen Matches in den nächsten 14 Tagen. | Nenhuma partida importante nos próximos 14 dias. |
| Aucune info | No news for now. | Aucune info pour l'instant. | Sin noticias por ahora. | Derzeit keine Meldungen. | Nenhuma notícia por enquanto. |
| En savoir plus | Learn more | En savoir plus | Saber más | Mehr erfahren | Saiba mais |
| Fuseau | Paris time | heure de Paris | hora de París | Pariser Zeit | horário de Paris |

Les jours et les mois sont écrits dans la langue de la page (mêmes listes que `matchs.py`, recopiées). Aucune ligne « mis à jour le » : une page dont le contenu n'a pas changé n'est pas réécrite.

**Sitemap** : 5 entrées ajoutées une seule fois par le script d'application des accueils (§8), de la même forme que celles de `matches-this-week.html` (`<changefreq>daily</changefreq>`, 5 liens hreflang, `x-default` vers `news.html`). Le générateur met à jour leur `lastmod` (jour de Paris) quand le contenu de la page change, en conservant les fins de ligne.

## 8. Les accueils (5 langues)

Modification faite **une seule fois** par un script d'application jetable (comme pour la barre de langue), avec contrôle que chaque point d'insertion existe exactement une fois :

- **Bloc.** Juste après la fin de la section `lancement` et avant la section `etapes`, entre les marqueurs `<!-- news-accueil -->` et `<!-- /news-accueil -->` :
  `<section class="block news" id="news"><div class="wrap"><h2>…</h2><ul class="infos">…</ul><p class="more"><a href="…">…</a></p></div></section>`.
  Le contenu est régénéré chaque matin : jusqu'à 3 infos (épinglées d'abord), puis, s'il y en a un, une ligne « prochain match important » (libellé : Next big match, Prochain match important, Próximo partido importante, Nächstes wichtiges Match, Próxima partida importante) avec l'heure de Paris, puis le lien « Toutes les actualités → » (All news →, Todas las noticias →, Alle Nachrichten →, Todas as notícias →). Quand il n'y a rien à montrer, l'espace entre les marqueurs est vide : aucune section.
- **Menu.** Un lien « News » (libellé de la colonne « Kicker » du tableau §7), qui mène à la page et non à une ancre, après « FAQ » dans le menu du haut, et après « Questions » (dernier lien de section) dans le panneau mobile.
- **Pied de page.** Un lien « News » dans la liste « L'app », après « What's new ».
- **Style.** Quelques règles ajoutées au `<style>` existant (`.news`, `.infos`, `.infos li`, `.more`), avec les variables de thème du site. Aucun script ajouté : la CSP des accueils ne change pas.

## 9. Le générateur `.github/scripts/actualites.py`

Bibliothèque standard seulement, commentaires en français, identifiants en anglais, docstring d'usage comme `bascule_appstore.py`. Tests : `.github/scripts/test_actualites.py` (`unittest`), qui reste dans le dépôt.

- **Interfaces** (signatures exactes dans le plan) : `load_news(path, site)` valide et lit le fichier ; `read_events(slug)` lit un calendrier d'événement (rend `None` s'il est indisponible, après un second essai) ; `is_important(event, knockout_from)` et `select_matches(events, config, now)` ; `visible_items(items, today)` ; `render_page(lang, matches, items, template)` et `render_home_block(lang, matches, items)` ; `update_home(page, block)` ; `set_lastmod(sitemap, loc, day)` ; `main(argv, root)`.
- **Ligne de commande** : `python3 .github/scripts/actualites.py` génère ; `--essai` dit ce qui changerait sans rien écrire ; `--verifier` ne fait que valider `news/news.json`.
- **Écriture** : tout est calculé en mémoire, puis seuls les fichiers dont le contenu change sont écrits, avec `encoding="utf-8", newline=""` (les fichiers de l'arbre de travail sont en CRLF). Deux exécutions d'affilée donnent le même résultat.
- **Erreurs** : `NewsError` (liste de problèmes) arrête le script avant toute écriture, avec un message par problème et le code de sortie 1.
- **Duplication assumée** avec `matchs.py` (à garder cohérente, signalée par un commentaire) : le lecteur de calendrier, le petit script d'heure locale (recopié à l'identique, donc la même empreinte CSP), les noms de jours et de mois.
- **Job du matin** : une étape « Mise à jour des news » (`python3 .github/scripts/actualites.py`, `continue-on-error: true`) est ajoutée à `matchs.yml` après `matchs.py` et avant l'envoi. Pas de déclenchement à chaque fusion : la pull request contient déjà les pages générées.
- **Outils locaux** : Python 3.13 avec `PYTHONTZPATH` (fuseaux de pytz présents dans l'Anaconda, rien à installer) pour que `zoneinfo` fonctionne sous Windows.

## 10. Publier une info

1. L'utilisateur donne l'info dans le chat. Claude rédige l'entrée (id, date, `until`, `pin`, lien éventuel, 5 langues) et montre le français et l'anglais.
2. Claude valide le fichier, lance le générateur en local et regarde le résultat dans un navigateur.
3. Claude ouvre une pull request avec `news/news.json` et les pages générées ; sa description présente les 5 textes dans un tableau.
4. L'utilisateur écrit « J'autorise la fusion de la PR #N dans main… » ; Claude fusionne ; la mise en ligne est immédiate. Le job du matin continue de rafraîchir les matchs.
5. Retrait ou correction : même chemin. Plusieurs infos peuvent être regroupées dans une pull request.
6. Un match non détecté devient une info manuelle avec un lien vers le match. Une date de début des phases finales donnée par l'utilisateur est inscrite dans `events` (même chemin).
7. Si le robot du matin modifie les pages générées avant la fusion, Claude régénère les pages depuis `news/news.json` sur le `main` à jour (aucune résolution à la main) ; mettre la pull request à jour par force-push demande l'accord explicite de l'utilisateur, sinon une nouvelle pull request est ouverte.

Les textes sont du texte simple, échappé dans la page ; les adresses `javascript:` sont refusées.

## 11. Vérification

**Tests unitaires** (`test_actualites.py`) : la règle des matchs (« Grand Final », « Semifinal 2 », « Quarterfinal 4 », « Upper Final » retenus ; « Round 1 », « Group Stage » non ; match après `knockout_from` retenu sans mot de phase ; fenêtre de 3 h avant à 14 jours après ; tri ; match annulé écarté) ; chaque erreur de validation ; les infos visibles (expirées, programmées, épinglées d'abord, limites de 20 et de 3) ; le rendu (pages vides, `&` et `<` dans un titre, liens par langue, canonical, hreflang, adresse externe avec `rel="noopener"`) ; l'insertion du bloc de l'accueil (deux passages identiques, rien d'écrit sans changement) ; le `lastmod` du sitemap avec fins de ligne conservées ; l'empreinte CSP des pages égale à celle du script ; la reprise de la veille quand un calendrier est indisponible.

**Contrôles sur le vrai site** avant chaque pull request (hors dépôt, dérivés du vérificateur déjà utilisé) : maillage hreflang complet avec les 5 nouvelles pages ; canonical égal à l'entrée du sitemap ; aucun lien cassé de plus ; exécutions jumelles avant/après de `matchs.py` (mêmes pages de matchs) ; `bascule_appstore.py --essai` sans nouveau « reste » ; navigateur : les 5 pages News, le bloc de l'accueil, le lien du menu (ordinateur et mobile), aucune erreur CSP.

**Retour arrière** : `git revert` de la pull request ; le fichier de news garde l'historique.

## 12. Livraison

Branche `news` depuis `origin/main`, avec `--no-track`, en 5 commits : (1) spec et plan, et la ligne `news` dans `.assetsignore` ; (2) le générateur, ses tests et l'étape du job ; (3) les modifications uniques des accueils et du sitemap, faites par le script d'application jetable ; (4) la première génération (les 5 pages News, les blocs, `news/news.json` avec `events` et sans info inventée) ; (5) le paragraphe du README. Rien n'est poussé ni fusionné sans l'accord de l'utilisateur.

**Terminé quand** les 5 pages et les 5 blocs sont en ligne, le job du matin a tourné avec la nouvelle étape, et une première info (ou une entrée d'essai, retirée ensuite par une seconde pull request) a fait le tour complet : rédaction, pull request, fusion.

## 13. Risques et points ouverts

| Risque ou point | Traitement |
|---|---|
| **Dates des phases finales inconnues** pour VCT Champions et ESL Pro League : ces événements ne sont pas mis en avant tant que `knockout_from` vaut `null`. | L'utilisateur donne les dates ; Claude les inscrit. Les Worlds sont réglés dès le départ (3 novembre). |
| Une date de phases finales fausse ou qui change met en avant de mauvais matchs. | Rien d'automatique ne la corrige ; elle se corrige par une pull request. |
| Titres de matchs en anglais dans les 5 langues, y compris « TBD vs TBD ». | Comme « matchs de la semaine » ; traduction des phases hors périmètre. |
| Traductions es, de et pt relues seulement dans le tableau de la pull request. | L'autorisation de fusion vaut relecture ; correction par une nouvelle pull request. |
| Duplication avec `matchs.py` (lecteur de calendrier, script d'heure locale, noms de mois). | Signalée par un commentaire ; une divergence ne casse pas les pages. |
| Chaque publication demande une fusion explicitement autorisée. | Regroupement possible ; édition directe du fichier sur GitHub envisageable plus tard (les pages se régénèrent au matin ou à la demande). |
| Conflit avec le robot du matin avant la fusion. | Régénération depuis le fichier de news ; force-push seulement sur demande. |
| Liste des événements suivis en double (`EVENTS` dans `matchs.py` et `events` dans `news/news.json`). | Le fichier de news n'accepte que des événements dont la page existe ; en ajouter un demande de toucher aux deux. |
| Pages protégées par identifiant tant que le site est en préproduction. | Le Worker les protège comme le reste ; aucun changement. |
