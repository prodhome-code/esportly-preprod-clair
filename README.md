# Site de eSportly

Pages publiques de l'application eSportly (ProtoJo Digital), servies par le Worker Cloudflare `esportly-site`
(`wrangler.jsonc`, sans contrôle d'accès depuis l'ouverture publique du 28 octobre 2026) sur
<https://esportly.eu> (depuis le 26 octobre 2026 ; GitHub Pages et esportly.protojo.fr sont arrêtés).

- `privacy.html` : politique de confidentialité (anglais) ; `fr/confidentialite.html` : la même en français
- **Adresses** : l'anglais est à la racine (`/games/valorant`, `/teams/t1`, `/blog`, `/news`, `/live`) ; les quatre autres langues sont
  sous leur sous-dossier avec leurs chemins traduits, depuis le 1er novembre 2026 : `/fr/jeux/valorant`, `/fr/equipes/t1`, `/fr/blog`,
  `/fr/actualites`, `/fr/live`, `/es/juegos/…`, `/de/spiele/…`, `/pt/jogos/…`. Les accueils restent `/`, `/fr`, `/es`, `/de`, `/pt`.
  Les pages d'événements anglaises gardent leur suffixe (`/worlds-2026-en`) et les pages de confirmation françaises (`/merci`,
  `/verifie`, `/desinscrit`, `/inscription-erreur`, adresses des fonctions Supabase) restent à la racine.
  Chaque ancienne adresse (`/jeux/valorant`, `/live-fr`, `/blog-es/valorant`, `/worlds-2026`…) redirige en 301 par le fichier
  `_redirects` de la racine (Workers Assets, jamais servi). Le passage a été fait par `.github/scripts/sous_dossiers.py` (rejouable :
  il refuse de tourner deux fois ; `--essai` montre ce qu'il ferait), spec `docs/superpowers/specs/2026-10-31-sous-dossiers-langues-design.md`.
  Les fiches JSON des équipes restent dans `equipes/` (données lues par `matchs.py`).
- `index.html` : accueil en anglais (langue par défaut) ; `fr.html` : accueil en français ; `en.html` : renvoi vers `/` (ancienne adresse de l'accueil anglais)
- Les 5 accueils portent une barre de suggestion de langue (`#langbar`, script en ligne `#langbar-script`). Ce script est autorisé par son empreinte SHA-256 dans la CSP de chaque accueil : si on le modifie, recalculer l'empreinte (base64 du SHA-256 du contenu exact du script) et la mettre à jour dans les 5 pages.

Ces pages sont rédigées dans le dépôt de l'application (dossier `Site/`), puis copiées ici.

## Publier une news

La partie News (`news.html`, `fr/actualites.html`, `es/noticias.html`, `de/nachrichten.html`, `pt/ultimas-noticias.html` et le bloc « News » des 5 accueils) est générée par `.github/scripts/actualites.py` à partir de `news/news.json` : ne pas modifier ces pages à la main.

- **Une info** : ajouter une entrée à `items` avec `id` (minuscules, chiffres, tirets), `date` (AAAA-MM-JJ, jour de publication), le texte dans les 5 langues (`fr`, `en`, `es`, `de`, `pt-BR`, chacune avec `title` de 80 caractères au plus et `text` de 280 au plus, sans `<` ni retour à la ligne) et, facultatifs, `until` (dernier jour d'affichage), `pin` (`true` : en tête de liste) et `link` (`{"blog": "<id>"}` : l'article de la news, une page du Blog de genre `news` dans `blog-src/pages/<id>.json` ; `{"page": "worlds-2026"}`, `{"page": "weekly"}`, `{"page": "whats-new"}` ou `{"url": "https://…"}`).
- **Une news importante a son article** : la carte garde ses 280 caractères et son lien « Lire l'article → » mène à `blog-src/pages/<id>.json` (`"kind": "news"`, `game` facultatif), écrit comme une fiche du Blog (sections sourcées, tableau d'affirmations, couverture). Les routines du dimanche et du lundi préparent ces articles avec les news.
- **Vérifier puis générer** : `py -3.13 .github/scripts/actualites.py --verifier`, puis `py -3.13 .github/scripts/actualites.py` (`--essai` dit ce qui changerait sans rien écrire). Sous Windows, la génération a besoin de la base des fuseaux horaires (`py -3.13 -m pip install tzdata` une fois, ou `PYTHONTZPATH` vers un dossier `zoneinfo`) ; `--verifier` n'en a pas besoin. Ouvrir ensuite une pull request vers `main`.
- **Matchs importants** : les phases finales des grands événements se mettent à jour seules chaque matin, dans le job « Matchs du jour » (étape « Mise à jour des news », dont l'échec n'empêche pas l'envoi des pages de matchs). La date de début des phases finales d'un événement se renseigne dans `events` (`"knockout_from": "AAAA-MM-JJ"`, ou `null` tant qu'elle est inconnue : seuls les matchs dont le titre nomme une phase décisive, comme quart, demi ou finale, sont alors mis en avant).
- **Résultats du soir** : une carte par événement dont des matchs de phase finale ont été joués dans la journée est écrite chaque
  soir par `.github/scripts/resultats.py` (job « Résultats du soir », `.github/workflows/resultats.yml`, à 23 h 40 heure de Paris,
  puis `actualites.py` et l'envoi ; tests `test_resultats.py`). Elle dit combien de matchs ont été joués et quelle est la prochaine
  étape, **jamais un score ni un nom d'équipe** : le calendrier du relais nomme pourtant les qualifiés dans les titres des matchs à
  venir (« Semifinal 2: IG vs TBD »), et un seul de ces noms dirait qui a gagné son quart ; le robot ne lit donc de ces titres que
  l'étape (`resultats.stage_of`). Son identifiant est `<événement>-<jour>` : deux passages dans la même soirée remplacent la carte
  au lieu de la dupliquer, et elle s'efface au bout de 3 jours (`until`). Sans match de phase finale dans la journée, rien n'est
  écrit ni commité. Le nom affiché d'un événement vient de `resultats.NAMES`, qui doit rester d'accord avec `EVENTS` de
  `matchs.py` (`test_noms_comme_dans_matchs`). À la main : `py -3.13 .github/scripts/resultats.py --essai` dit ce qu'il écrirait.

## Le panneau « Équipes » du menu

« Équipes » n'est plus un simple lien : c'est un panneau, comme « Jeux ». Il tient en trois morceaux (`site_chrome.teams_menu`
pour la barre, `teams_panel` pour le burger) :

- **les 7 jeux qui ont des équipes** à gauche, chacun menant à sa section de la page « Toutes les équipes » ;
- **les 10 équipes qui jouent le plus**, logo et nom, à droite. Elles ne sont pas choisies à la main : `matchs.py` écrit
  `equipes/vedettes.json` d'après la taille des calendriers (`write_stars`), donc la liste suit la saison toute seule ;
- **un champ de recherche** en bas pour les 83 autres.

**Le menu est recopié dans les centaines de pages du site** : il ne peut pas porter les 83 équipes (≈ 12 Ko par page, ~10 Mo au
total, et autant de liens répétés partout, ce que le référencement n'aime pas). La recherche demande donc la liste
(`equipes/index-pages.json`) **au premier clic dans le champ**, une seule fois, et remplit un `<datalist>` ; valider un nom
reconnu mène à la fiche de l'équipe, sinon le formulaire mène à la page des équipes. Sans JavaScript, le champ reste un
formulaire qui mène à la page des équipes : rien n'est cassé.

Les suggestions se posent avec `createElement`, jamais avec `innerHTML` : un nom d'équipe ne peut pas injecter de balise. Le
script du menu ne demande que ce fichier du site, jamais une adresse extérieure (un test le vérifie).

Le panneau s'ouvre **sous son propre bouton** (`.mega{position:relative}`), avec une petite pointe vers lui : ancré sur la barre
entière, il s'ouvrait sous la marque, loin du mot cliqué, et plus personne ne voyait ce qui avait ouvert quoi. Sa largeur reste
tenue (`max-width:min(86vw,860px)`) pour qu'il ne sorte jamais de l'écran — c'était le bug d'avant.

Le titre des vedettes dit **d'où vient la liste** (« Les plus actives cette saison ») : dix équipes sans ordre apparent
ressemblaient à un choix au hasard.

`mega_accueils.py` **remplace** un panneau déjà posé par celui du jour, au lieu de le laisser tel quel : sans cela un accueil
gardait les libellés de la veille pendant que les pages fabriquées, elles, suivaient. Et `body{overflow-x:clip}` supprime la
barre de défilement horizontale que le bandeau défilant des accueils provoquait (ses marges négatives dépassent de 4 px) —
« clip » plutôt que « hidden », qui casserait les éléments collants.

Les panneaux **se referment** dès qu'on clique ailleurs, avec Échap, et ouvrir l'un ferme l'autre : un `<details>` laissé
ouvert suivait le visiteur sur toute la page.

Sur les accueils, `mega_accueils.py` reconnaît son propre panneau à la **classe** `mega team` / `megam team`, jamais au mot
« team » : « teams.html » apparaît déjà dans le panneau des jeux des quatre langues non françaises, et le script croyait avoir
fini — l'anglais, l'espagnol, l'allemand et le portugais sont restés sans panneau des équipes jusqu'à ce que d0m le signale.
Le panneau du burger se cherche **dans l'en-tête et jusqu'à sa propre fin** : non gourmande, l'expression s'arrêtait au premier
`</div></details>`, c'est-à-dire au milieu du panneau des équipes, et laissait un doublon derrière elle.

**`swap_menu_script`** remplace le script du menu des pages déjà publiées par la version du jour, retire l'ancienne empreinte de
la CSP et ajoute la nouvelle. Sans lui, une page gardait son vieux script — `with_script` n'ajoute que ce qui manque, il ne
remplace pas — et les ajouts du menu ne tournaient jamais sur les pages déjà faites.

## La page Live sur ordinateur

Sur ordinateur, la page Live était une liste à plat : le héros prenait l'écran, puis un filtre, puis « Aujourd'hui » où un match
en cours ressemblait à tous les autres. Elle est maintenant **en deux colonnes** (`live.py`) :

- **Les directs d'abord**, avant même le filtre par jeu : c'est ce qu'on vient chercher. Le reste suit (jours, puis terminés).
- **Un encart à droite qui suit le défilement** (`render_side`) : ce que l'application apporte (être prévenu avant un match),
  le bouton de téléchargement, et où regarder un direct. Les gens sur ordinateur n'ont pas l'app : c'est là qu'on leur parle.
- Sous 1000 px, une seule colonne et l'encart passe sous les matchs ; le bouton du héros ne s'efface que sur grand écran, pour
  ne pas faire doublon avec celui de l'encart.

## Où regarder un match

Le calendrier ne dit pas où un match est diffusé. `diffusions.py` tient **à la main** le tableau « compétition → chaînes
officielles » (`CHANNELS`, chaque chaîne vérifiée une par une), sur **Twitch, YouTube et Kick**. La page du match montre le
lecteur de la première chaîne, **tout en haut**, et propose les autres à côté en liens.

- **YouTube veut l'identifiant « UC… » de la chaîne** : son lecteur de direct ne connaît pas les noms en @ (un test le vérifie).
- Quand une compétition a **plusieurs chaînes en parallèle** (EPL diffuse deux matchs à la fois sur deux chaînes Kick),
  `live_first` demande à Kick laquelle diffuse et lui donne le lecteur : sans cela, la moitié des matchs montrerait un lecteur
  éteint. Une question par chaîne et par exécution, et rien ne bouge si elle échoue.

- **Replié par défaut** (`<details class="mwatch">`) : rien n'est chargé depuis Twitch ou YouTube avant le clic, et le texte
  prévient qu'**un direct montre le score en cours** — c'est le contraire de la promesse du site.
- **Jamais sur un match fini** : la chaîne y diffuserait autre chose.
- **Aucun lecteur pour une compétition absente du tableau** : mieux vaut rien qu'un lecteur qui diffuse un autre match.
- Le jeu départage les mots-clés partagés : « PGL » de Counter-Strike et « PGL » de Dota 2 ne sont pas la même chaîne.
- La plateforme entre dans `frame-src` de la CSP (`_with_frames`), en complétant la directive si le lecteur de temps forts l'a
  déjà posée — une page refabriquée ne change pas.

Tests : `test_diffusions.py`.

## Les logos sur les cartes de match

Une carte de match ne montrait que « Yellow Submarine – GamerLegion » en texte. `logos_matchs.py` met devant chaque équipe
**son logo** quand le site l'a, et **ses initiales sur une pastille** sinon : toutes les cartes se ressemblent, aucune n'a de
trou. Partout où il y a des cartes (semaine, live, pages de jeux, de compétitions, d'équipes).

- **Aucune requête réseau** : les noms du calendrier sont rapprochés des fiches de `equipes/*.json`, de leurs autres noms et de
  leurs **sigles** (« KC » mène au logo de Karmine Corp). 174 noms reconnus, soit **6 cartes sur 10** avec un vrai logo.
- Le calendrier ne donne que le **titre** du match : `teams_of` en déduit les deux camps (`–`, `-`, `vs`, `VS`, `v`) et garde
  l'étape du début (« Grand Final: »). **Un titre inhabituel est laissé tel quel** plutôt que mal coupé.
- Un adversaire **pas encore connu** (TBD, TBA) affiche « ? », jamais des initiales inventées.
- Rejouable, lancé après `logos_equipes.py` dans les quatre workflows qui fabriquent des pages.

**Pour monter à 10 sur 10**, il faudrait que le calendrier donne l'**identifiant PandaScore de chaque équipe** (ou l'adresse de
son logo) dans ses événements : aujourd'hui il ne donne que des noms, et une équipe sans fiche n'a pas de logo dans le dépôt.

Tests : `test_logos_matchs.py`.

## Les logos des équipes

Partout où le site liste des équipes, chaque entrée montre **son logo, et son nom en dessous**. La page « Toutes les équipes »
le faisait déjà (logo à gauche, nom à droite) ; les pages de jeux (« Les équipes à suivre ») et les pages d'équipes
(« D'autres équipes ») n'avaient que des liens en texte.

`logos_equipes.py` transforme ces listes (`<nav class="others">` → `<ul class="teams">`, les classes de la page « Toutes les
équipes ») et pose le style qui met le nom sous le logo sur **toute page qui liste des équipes**, l'index compris.

- **Aucune image à aller chercher** : les 136 logos sont déjà dans `logos-equipes/` (`<identifiant PandaScore>.webp`), le lien
  entre une fiche et son logo vient de `equipes/<slug>.json` (`equipes[].id`).
- Il ne touche **qu'une liste dont tous les liens mènent à une fiche d'équipe connue** : « Les autres jeux », « Pour aller plus
  loin » et les fils d'Ariane gardent leur forme. Une liste d'un seul lien reste un lien.
- Les **7 organisations sans logo local** gardent leur nom seul : rien ne casse, aucune image manquante.
- Rejouable : il tourne après `menu_partout.py` dans tous les workflows qui fabriquent des pages.

Tests : `test_logos_equipes.py`, dont un qui vérifie qu'**aucune page du site ne garde une liste d'équipes en texte**.

## Les compétitions

Le site n'avait de page que pour trois grands événements (`EVENTS` de `matchs.py` : Worlds, VCT Champions, ESL Pro League) alors
qu'il affiche des matchs d'une quarantaine de compétitions : « IEM · Beijing 2026 » n'avait rien derrière. `matchs.py` découvre
donc les compétitions **dans les matchs eux-mêmes** (leur description dit « jeu · ligue · série », `comp_label`) et dans le
calendrier de chaque jeu (`/calendrier/jeu/<jeu>.ics`, 14 requêtes : 400 matchs contre 25 par les seuls calendriers d'équipes).

- Une page par compétition dans les 5 langues (`competitions/<slug>.html`, `fr/competitions/<slug>.html`, `es/competiciones/`,
  `de/wettbewerbe/`, `pt/competicoes/`) : programme groupé par jour, résultats (scores floutés), comment regarder, et deux liens
  vers la page du jeu et l'index. Mêmes libellés que les pages d'événements : **aucun texte nouveau à traduire**, sauf ceux de
  l'index (`comp_title`, `comp_lead`, `comp_all`, `comp_n`).
- **Pas de bouton de calendrier** : une compétition découverte dans les matchs n'a pas d'adresse `.ics` (`ics_slug` vaut None).
- **Pas de page pour une compétition au nom d'un site de paris** (règle « aucun pari », `BETTING`), ni en dessous de `COMP_MIN`
  matchs, ni pour les trois événements configurés (ils gardent leur page à la racine).
- Les pages des compétitions finies sont **supprimées** au passage suivant (`prune_competitions`).
- L'index (`competitions.html`, `fr/competitions.html`…) groupe les compétitions par jeu, avec leur nombre de matchs suivis.
- Les pages et l'index entrent dans `sitemap.xml` entre `<!-- competitions -->` et `<!-- /competitions -->`
  (`write_competitions_sitemap`) ; le reste du sitemap, écrit à la main, n'est pas touché.
- La liste « Compétitions suivies » des pages de jeux était du texte mort (« Majors », « IEM ») : `write_game_comps` la remplace
  par les liens des compétitions réellement suivies pour ce jeu. Le panneau des jeux du menu mène à l'index.
- Le modèle de ces pages est une page des nouveautés, qui vit un dossier plus haut : `deeper` ajoute un `../` à ses adresses
  relatives (`in_folder=True`), sans quoi la marque d'une page anglaise mènerait à `competitions/` au lieu de la racine.

Tests : `test_competitions.py`.

**Les matchs sur les pages de jeux.** Chaque page de jeu porte ses prochains matchs (groupés par jour, 8 au plus) et ses derniers
résultats (8 au plus, scores floutés), entre `<!-- jeu-matchs -->` et `<!-- /jeu-matchs -->`, posés juste avant le calendrier du
jeu (`<!-- calendrier-jeu -->`) ou, pour les pages qui n'en ont pas, avant le lien du guide (`<!-- blog-guide -->`). Écrits par
`matchs.py` (`game_block`, `write_game_blocks`) **sans une seule requête de plus** : les matchs viennent des calendriers d'équipes
déjà lus pour les autres pages, les résultats du flux de la semaine déjà lu, et les deux titres sont ceux des pages d'événements
(aucun texte nouveau à traduire). Une page que le bloc ne change pas n'est pas réécrite. Tests : `test_jeux_matchs.py`.

## La page Live

`live.html` (anglais), `fr/live.html`, `es/live.html`, `de/live.html` et `pt/live.html` (lien « Live » du menu) listent les matchs du
jour de toutes les équipes et des grands événements, fabriqués chaque matin par `matchs.py` à partir des mêmes calendriers que les
pages de matchs (`.github/scripts/live.py`, tests `test_live.py`) : ne pas les modifier à la main. Le relais ne publie ni score ni
état « en cours » : chaque match porte ses horaires prévus (`data-start`, `data-end`) et un petit script de la page (empreinte dans la
CSP) marque « En direct », « Terminé » ou « À venir » selon l'heure du visiteur, chaque minute, sans réseau. Sans JavaScript, la page
reste la liste des matchs du jour en heure de Paris.

**Ordre et fin des matchs.** Le même script range la page selon l'état : les matchs en direct tout en haut (`#l-live`), puis les matchs à
venir par jour, puis les terminés tout en bas (`#l-done`, « Terminé » dans les 5 langues, le plus récent d'abord). Un robot note la fin
des matchs : `.github/workflows/live.yml` (toutes les heures, à :40) lance `matchs.py --live`, qui relit le flux de résultats du relais
(`/calendrier/resultats/semaine.json`, un `id` de match et un `score`) ; quand un match du jour y a son résultat, `live_suivi.py` le note
dans `suivi/live.json` (hors site, `.assetsignore` ; les matchs du jour y sont écrits chaque matin par `matchs.py`), le match reçoit
`data-final` (le script le met en « terminé » même si l'horloge le croit en direct) et la page du match montre son score **écrit en clair mais
flouté** (`filter:blur`, posé en style en ligne : il tient même sans feuille de style), qu'un clic sur « Voir le score » révèle ;
jamais sur la liste Live : pas de spoiler. Un match terminé montre aussi ses **temps forts** quand `blog-src/topplays.json` a, pour
son jeu, une vidéo publiée le jour du match ou le lendemain (`live_match.video_for`) : la carte de lecture au clic du Blog, rangée
derrière « Voir les temps forts » parce qu'un titre de vidéo peut nommer le vainqueur. Rien n'est chargé depuis YouTube avant le
clic ; la page gagne alors le script du lecteur et `frame-src https://www.youtube-nocookie.com` dans sa CSP. Rien n'est deviné : sans résultat du flux, l'horloge seule décide, et
le robot ne commite rien s'il n'y a rien de nouveau. Le flux donne le coup d'envoi, pas l'heure de fin : le robot note seulement quand il
l'a constatée (`vu`). Pour le lancer à la main : onglet Actions, « Fins de matchs (Live) », Run workflow. Spec :
`docs/superpowers/specs/2026-11-01-live-fins-design.md`, tests `test_live_suivi.py`.

**Le changement de jour.** Les matchs du jour sont choisis une fois par jour et gardés dans `suivi/live.json`, qui dit maintenant
quel jour il décrit (`jour`, jour de Paris ; `live_suivi.day_of`). Au premier passage où ce jour n'est plus celui de Paris, le
robot de l'heure **refait la journée entière** au lieu de seulement noter les fins (`matchs.py` remet `LIVE_ONLY` à faux, sans
aucun appel réseau pour s'en rendre compte). Sans cela, la page Live, les matchs de la semaine et les pages d'événements
montraient la veille jusqu'au passage du job du matin : son cron est à 4 h 15 UTC, mais **GitHub le lance avec sept à huit heures
de retard** (passages constatés vers 12 h), donc la page « Matchs du jour » affichait hier pendant toute la matinée.

**Résultats des pages de compétition.** Le même robot de l'heure remet à jour le bloc des résultats des pages des grands
événements (`worlds-2026-en.html`, `fr/worlds-2026.html`…) : ces pages ne sont refabriquées que le matin, un résultat y restait
donc invisible jusqu'à 24 heures. Il ne les refabrique pas — `matchs.refresh_results` remplace seulement ce bloc, délimité par
`<!-- resultats -->` et `<!-- /resultats -->` (une page faite avant ces repères est reconnue par son titre `id="resultats"` et les
reçoit au passage), avec le flux `/calendrier/resultats/<événement>.json` : une requête par événement. Un flux vide ne touche à
rien (on n'efface jamais un résultat déjà publié), et une page inchangée n'est pas réécrite — le robot ne commite alors pas.
Les scores y sont **écrits en clair mais floutés** comme sur la page d'un match (`matchs.BLUR` en style en ligne) ; la règle qui
les révèle (`matchs.REVEAL_STYLE`) est posée sur une page qui ne l'a pas encore, sans quoi son score resterait flouté.

**Une page par match.** Cliquer un match de la page Live mène à sa propre page (`live/<id>.html`, `fr/live/<id>.html`, `es/live/`,
`de/live/`, `pt/live/`, fabriquées par `.github/scripts/live_match.py`, tests `test_live_match.py`), pas à `match.html`, la page de
renvoi vers l'app, qui n'a aucun sens sur ordinateur. La page dit ce que le calendrier sait (équipes avec leur fiche, jeu, compétition,
coup d'envoi, état en direct, terminé ou à venir), explique comment suivre le match avec eSportly et renvoie vers le jeu, son guide du
Blog, le grand événement et les matchs de la semaine. Le bouton « Ouvrir ce match dans l'app » (vers `match.html?id=…`) n'apparaît que
sur les écrans tactiles ; il n'y a aucune redirection automatique vers l'app. Ces pages sont en noindex, hors du sitemap, et `matchs.py`
supprime celles dont le coup d'envoi date de plus de 3 jours. Ne pas les modifier à la main.

## Le menu du site sur toutes les pages

**Le panneau des jeux (mega menu).** Dans la barre, « Jeux » n'est plus une ancre de l'accueil : c'est un panneau qui s'ouvre sur
les 14 jeux, chacun son logo, vers sa page (`site_chrome.games_menu` ; `games_panel` pour la version dépliante du menu burger),
avec « Tous les jeux → » et « Toutes les équipes → » en bas. C'est un `<details>`, comme le menu de langue : **aucun script**, il
s'ouvre sans JavaScript et la CSP ne change pas. Les noms affichés viennent de `site_chrome.GAME_NAMES` (ils ne se traduisent
pas ; `test_noms_de_jeux` les compare aux pages du site) et les logos blancs s'inversent sur fond clair, comme sur le Blog.
Les pages fabriquées le reçoivent de `render_menu` ; les cinq accueils, qui portent leur menu à la main, de
`.github/scripts/mega_accueils.py` (rejouable, `--essai`, étape « Panneau des jeux sur les accueils » du job « Matchs du jour »).
**Ils sont rédigés dans le dépôt de l'application puis recopiés ici : après une recopie, le panneau est à reposer** — c'est pour
cela que le script tourne chaque matin. Tests : `test_mega_menu.py`.

Depuis le panneau des jeux, `menu_partout.py` ne se contente plus d'ajouter le menu aux pages qui ne l'ont pas : il le
**refabrique** sur celles qui l'ont déjà (équipes, pages légales : elles ne sont fabriquées qu'une fois, sans quoi leur menu ne
suivrait jamais). Le lien marqué comme page courante est relu dans l'en-tête avant d'être refait (`current_of`), et les cinq
accueils sont exclus (`SKIP_PAGES`) : leur en-tête propre ne doit pas être remplacé par le menu générique.

`menu_partout.py` **refabrique** le menu des pages qui l'ont déjà (voir plus bas) : il garde au passage le bouton de la bêta tel
qu'il est sur la page (`keep_beta`), car `bascule_appstore.py` en a changé l'adresse et le libellé après la sortie sur l'App
Store — le refaire remettrait « Rejoindre la bêta » et le site se contredirait d'une page à l'autre.

Toutes les pages publiques portent le menu des accueils (barre au-dessus de 1150 px, menu burger en dessous, bouton de la bêta),
dans leur langue. Les pages News, Blog et Live le reçoivent de leurs scripts (`site_chrome.render_menu`) ; les autres (équipes,
jeux, événements, matchs de la semaine, nouveautés, presse, pages légales et de confirmation, 404) le reçoivent de
`.github/scripts/menu_partout.py` (tests `test_menu_partout.py`), qui remplace l'en-tête de la page par celui du menu en gardant
sa marque et son sélecteur de langue (liste à drapeaux, ou simple lien « English » des pages d'équipes), ajoute les règles du menu
au style et, sur les pages sans en-tête (légales, confirmations), pose la marque et met le texte dans `<main class="legal">`. Sans
script : le burger est un `<details>`, la CSP ne change pas. Rejouable sans effet (`--check` liste ce qui manque) ; il passe dans
les jobs « Matchs du jour » et « Bascule App Store » après les scripts qui fabriquent des pages, et les modèles dont elles
repartent (`fr/nouveautes.html`…) ont déjà le menu. Les widgets (`widget/`) et les pages de renvoi (`en.html`, `match.html`,
`tv-equipes.html`) n'en ont pas.

## Depuis la sortie sur l'App Store (2 novembre 2026)

`version.json` porte le `storeURL` : le site parle de l'App Store, plus de la bêta TestFlight. Les scripts qui refabriquent des pages
(`actualites.py`, `live.py`, `menu_partout.py`) repartent de libellés de bêta : après eux, lancer `bascule_appstore.py` (sans effet
sur ce qui est déjà basculé ; « Matchs du jour » et « Fins de matchs (Live) » le font en dernier). `blog.py` repasse seul par la bascule.

## Mettre à jour le Blog

Le Blog (`blog.html`, `fr/blog.html`, `es/blog.html`, `de/blog.html`, `pt/blog.html`, les fiches `blog/`, `fr/blog/`, `es/blog/`, `de/blog/`, `pt/blog/` et le bloc « Guide » des pages de jeux) est généré par `.github/scripts/blog.py` à partir de `blog-src/` : ne pas modifier ces pages à la main.

- **Données** : une fiche par jeu dans `blog-src/pages/<jeu>.json` (4 sections, 5 langues, 3 à 5 sources dont une officielle), avec son tableau d'affirmations `blog-src/claims/<jeu>.md` (chaque fait relié à un extrait exact de sa source). Les chaînes YouTube officielles du bloc « Top plays » sont dans `blog-src/channels.json`.
- **Page d'article** : couverture, titre, texte en sections (ancres `#s1`, `#s2`…) et sommaire latéral (collant à droite sur ordinateur, avant le texte sur téléphone), sources numérotées. La couverture est `couvertures/<id>.webp` (1600×900, 200 Ko au plus), déclarée par `"image": {"kind": "ia"}` (illustration générée dans la charte du site : fond nuit, accents dorés, sans texte ni logo ni visage) ou `"image": {"kind": "officielle", "credit": "<éditeur>", "url": "https://…"}` (visuel de presse dont la licence autorise la reprise, crédité et relié à sa source). `"file": "<id d'une autre page>"` réutilise la couverture de cette page (un article de news sur Valorant écrit sans nouvelle illustration : `{"kind": "ia", "file": "valorant"}`). Sans `image`, la page n'a pas de couverture et garde l'image de partage de son jeu.
- **Vérifier puis générer** : `py -3.13 .github/scripts/blog.py --verifier`, puis `py -3.13 .github/scripts/blog.py` (`--essai` dit ce qui changerait). `blog.py --sources` relit les pages sources sur Internet et contrôle les extraits (un site peut répondre 403 ou 500 de temps en temps : relancer).
- **Top plays** : `topplays.py` choisit chaque matin, dans le job « Matchs du jour », les temps forts des chaînes officielles ; les vidéos ne se chargent depuis YouTube qu'au clic.
- **Contrôle hebdomadaire** : une fois par semaine, relire `blog.py --sources` et les actualités du site pour les faits qui bougent (formats, dates d'événements).
- **Titles et métadescriptions** : le skill `.claude/skills/titres-seo/` (règles par langue dans `regles.md`, inventaire des pages par `scripts/inventaire.py` → `docs/seo/inventaire-titres.csv`, contrôle par `scripts/controle.py`) refait les balises title (55 à 63 caractères, sans marque en suffixe) et les descriptions (120 à 155) avec les mots-clés SEMrush de chaque langue. La source est `seo/titres.json` (chemin public → title, description ; jamais servi, `.assetsignore`) : les scripts qui fabriquent des pages (Blog, News, semaine, événements, Live) y lisent le `<title>`, la description et les og:* (`site_chrome.seo`), le H1 restant le titre de la page ; `.github/scripts/titres_seo.py` (rejouable, lancé par `matchs.yml` après le Blog) l'applique aux pages de jeux et d'équipes et au nom WebPage de leurs données structurées. Les accueils et les pages légales gardent leur title. Tests : `py -3.13 -m unittest discover -s .claude/skills/titres-seo/scripts` et `test_titres_seo.py`.
- **Site de référence pour Counter-Strike 2** : [hltv.org](https://www.hltv.org/news/archive) (actualités, calendrier, résultats). On s'en sert pour repérer ce qui bouge (tournois, formats, changements de règles) et pour alimenter les News ; on n'en copie aucun texte (reformuler). Un fait publié dans une fiche doit toujours être confirmé par une source officielle (Valve, ESL, PGL…), car la règle « sources officielles » du Blog ne change pas et HLTV refuse parfois les scripts (403) : il ne s'ajoute donc pas aux sources vérifiées de `blog.py --sources`.

## La veille : des articles écrits chaque jour

La veille (`.github/scripts/veille.py`, workflows `veille-gate.yml` et `veille-publier.yml`, consignes dans `docs/veille/`)
cherche chaque matin des nouveautés sur une **liste fermée de sources officielles** (`blog-src/veille/sources.json`), fait
écrire par des sous-agents jusqu'à 3 articles originaux en 5 langues (rien les jours sans actualité) et les propose par une
pull request `veille/AAAA-MM-JJ` étiquetée `veille`. Le contrôle est du code, pas un agent : `veille.py gate` vérifie les
chemins autorisés (contenu seul), le format du Blog, la liste blanche des sources, les extraits retrouvés, l'originalité
(6 mots identiques au plus, 15 % de recouvrement au plus par source) et le volume. Pendant 2 semaines l'utilisateur fusionne
lui-même ; ensuite `mode.json` (`auto_from`) laisse `veille-publier.yml` fusionner les pull requests conformes et régénérer
les pages. `blog-src/veille/STOP` arrête tout. Détail, commandes et sécurité : [`docs/veille/README.md`](docs/veille/README.md).
