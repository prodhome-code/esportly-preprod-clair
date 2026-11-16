# Partie « Blog » : une fiche par jeu, sources citées et top plays

- Date : 2026-10-27
- Statut : à relire par l'utilisateur
- Base : branche `news` `20a57fb` (qui part de `origin/main` `af3cb2d`), site sur `https://esportly.eu` (accès protégé par le Worker `esportly-site`)
- Branche de travail : `blog` (locale, sans suivi distant), créée depuis `news`
- Dépend de : la [PR n°10](https://github.com/ProtoJo-Digital/esportly-site/pull/10) (partie News), non fusionnée

## 1. Objectif

Ajouter au site un **Blog** dont les catégories sont les jeux. Au lancement, chaque jeu a une **fiche** (le jeu, sa scène pro, ses grandes compétitions, comment la suivre), rédigée d'après des sources web citées, dans les 5 langues. Chaque fiche affiche aussi les **top plays du moment**, tirés des chaînes YouTube officielles du jeu. Le but est d'être trouvé sur Google par des contenus durables, avec un chemin vers l'app.

Le chantier est réussi quand :

1. Les 5 accueils du Blog et les fiches des jeux en 5 langues sont en ligne (14 fiches prévues, soit 75 pages et 255 adresses au sitemap ; moins si un jeu n'a pas de source officielle, §10), avec hreflang, canonical et sitemap cohérents.
2. Chaque affirmation d'une fiche est rattachée à une source citée, et le contrôle des sources (adresses et extraits) passe.
3. Le job du matin met à jour les top plays et les pages sans bloquer les pages de matchs ni la News.
4. L'utilisateur a relu et approuvé les 14 fiches avant la pull request.
5. Un paragraphe du README explique comment ajouter ou corriger une page du Blog.

## 2. Décisions validées (2026-10-27)

| Sujet | Décision |
|---|---|
| Mise en ligne | News et Blog ensemble (la News ne dépend pas du Blog et peut être fusionnée avant si l'utilisateur change d'avis) |
| But | Être trouvé sur Google ; contenus durables |
| Catégories | Les 14 jeux déjà suivis par le site ; une page par jeu qui sert de catégorie et de fiche |
| Approche | A : fichiers de données, générateur, pages statiques, comme la News |
| Contenu | Une fiche par jeu rédigée d'après des sources citées, relue par l'utilisateur |
| Langues | Les 5 (fr, en, es, de, pt-BR) |
| Top plays | **Vidéos YouTube lues dans la page, au clic** (carte avec bouton de lecture ; le lecteur renforcé `youtube-nocookie.com` n'est chargé qu'après le clic), **temps forts seulement**, choisies chaque matin par un script dans les chaînes officielles d'une liste validée à la main ; amendé le 27 octobre au soir (§14) : liens, puis lecteurs visibles, puis lecteur au clic par recommandation |
| Agent | La collecte est un script ; l'agent (Claude) établit la liste des chaînes et rédige ; l'agent qui publie seul est un chantier à part |
| Transparence | Chaque fiche porte la ligne « Rédigé avec l'aide de l'IA et vérifié par rapport aux sources citées » |

## 3. Hors périmètre

- L'agent qui cherche et publie seul, et son format de vérification automatique.
- La publication de guides ou de notes de version : le format les accepte (`kind` `guide` et `release`), mais aucun n'est publié au lancement.
- La vérification mensuelle planifiée des sources ; les vignettes personnalisées et tout lecteur autre que le lecteur intégré de YouTube ; la recherche, les commentaires, un flux RSS du Blog.
- D'autres jeux ou d'autres langues ; toute modification de `matchs.py`, et de `actualites.py` hors le renommage d'une fonction interne signalé en §9 (avec l'extension du test du job, §11).
- Le problème des adresses en `.html` redirigées par Cloudflare (traité à part).

## 4. État actuel (constaté le 27 octobre)

- **Les jeux** : 14, chacun avec une page par langue, dans `games/` (en), `jeux/` (fr), `juegos/` (es), `spiele/` (de) et `jogos/` (pt-BR), de même nom partout (`league-of-legends.html`, `counter-strike-2.html`, `valorant.html`, `rocket-league.html`, `dota-2.html`, `overwatch-2.html`, `rainbow-six-siege.html`, `call-of-duty.html`, `mobile-legends.html`, `honor-of-kings.html`, `ea-sports-fc.html`, `starcraft-2.html`, `starcraft-brood-war.html`, `wild-rift.html`) ; logos dans `logos-jeux/<jeu>.png`. Ces pages disent ce que fait eSportly pour le jeu, non ce qu'est le jeu.
- **Structure d'une page de jeu** : `<main>` avec un fil d'Ariane (`nav.crumbs`), l'accroche (`section.hero`), des sections, `<h2>Autres jeux</h2>` suivi d'une `nav.others` ; sous-dossier donc chemins en `../` ; CSP `script-src` limitée à une empreinte, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data:` et l'adresse du compteur de visites, aucun `frame-src`. Données structurées `FAQPage` et `BreadcrumbList`.
- **Sitemap** : une entrée d'une ligne par page, avec 5 liens hreflang et `x-default` vers l'anglais ; 180 entrées avec la News.
- **Job du matin** (`matchs.yml`) : `matchs.py`, puis l'étape « Mise à jour des news » (`continue-on-error`, 3 minutes), puis l'envoi du commit.
- **Accueils** : menu du haut déjà serré ; le lien « News » a obligé à resserrer l'espacement sous 1320 px (`header nav{gap:16px}`).
- **Flux YouTube** : le flux public d'une chaîne (`https://www.youtube.com/feeds/videos.xml?channel_id=<id>`) répond sans clé ni compte, avec 15 vidéos (titre, date de publication, nombre de vues, identifiant) ; un identifiant faux renvoie 404. Vérifié depuis le poste de travail le 27 octobre pour la chaîne « LoL Esports » ; **non vérifié depuis les serveurs GitHub**.
- **Outils** : `actualites.py` fournit déjà `update_between`, `extract_between`, `set_lastmod`, `paris()` et le lecteur HTTP `http_get`.

## 5. Les données : `blog-src/`

Le dossier `blog-src/` est ajouté à `.assetsignore` : rien de ce qu'il contient n'est servi.

```
blog-src/pages/<id>.json     une page du Blog (fiche de jeu, guide, note de version)
blog-src/channels.json       chaînes YouTube officielles par jeu (liste validée à la main)
blog-src/topplays.json       sélection du matin par jeu (écrite par topplays.py)
blog-src/claims/<id>.md      tableau des affirmations d'une page, avec extraits des sources (trace, non publiée)
```

Précision par rapport à la section 2 du design : les pages sont dans `blog-src/pages/`, pour qu'aucun identifiant de page ne puisse coïncider avec `channels` ou `topplays`.

**Une page**, `blog-src/pages/league-of-legends.json` :

```json
{
  "kind": "game", "game": "league-of-legends",
  "date": "2026-10-28", "updated": "2026-10-28",
  "sources": [{"id": "s1", "title": "…", "url": "https://…"}],
  "sections": [
    {"cite": ["s1"],
     "en": {"heading": "…", "text": ["paragraphe", "paragraphe"]},
     "fr": {…}, "es": {…}, "de": {…}, "pt-BR": {…}}
  ],
  "en": {"title": "…", "description": "…"}, "fr": {…}, "es": {…}, "de": {…}, "pt-BR": {…}
}
```

**Règles de validation** (toute violation arrête le script avec la liste des problèmes, avant d'écrire quoi que ce soit) :

- Aucun champ inconnu n'est toléré. `id` : le nom du fichier, `^[a-z0-9][a-z0-9-]*$`, unique dans les 5 langues (un seul espace de noms).
- `kind` : `game`, `guide` ou `release`. `game` : obligatoire pour `kind` `game` et égal à `id` (la page `games/<id>.html` et ses 4 équivalents doivent exister) ; facultatif pour les autres, et alors le nom d'un jeu dont la fiche existe.
- `date` et `updated` : `AAAA-MM-JJ` (jour de Paris) ; `updated` au moins égal à `date`. Une page n'est visible, générée et listée que si `date` est au plus égale à aujourd'hui.
- `sources` : de 1 à 8 ; `id` `^s[0-9]+$` unique ; `title` de 1 à 120 caractères ; `url` en `https://`, sans espace, 300 caractères au plus, unique dans la page.
- `sections` : de 3 à 8 pour une fiche de jeu, de 1 à 12 sinon. Chaque section cite (`cite`) de 1 à 4 sources déclarées, et porte les 5 langues avec `heading` (1 à 80 caractères) et `text` (de 1 à 4 paragraphes de 1 à 600 caractères).
- Au premier niveau, les 5 langues portent `title` (1 à 70) et `description` (1 à 160).
- Tout texte est simple, sur une ligne, sans `<` ni lien : les sources sont numérotées sous chaque section.

**Les chaînes**, `blog-src/channels.json` : `{"<jeu>": [{"id": "UC…", "name": "…", "proof": "https://…"}]}`. `id` : `^UC[0-9A-Za-z_-]{22}$` ; `name` de 1 à 60 caractères ; `proof` : l'adresse d'une page de l'éditeur ou de la ligue qui renvoie vers cette chaîne ; le jeu doit exister. Un jeu absent du fichier n'a pas de bloc de top plays. Seul un humain ajoute une chaîne, par pull request.

**La sélection**, `blog-src/topplays.json` : `{"<jeu>": {"fetched": "AAAA-MM-JJ", "videos": [{"id": "…", "title": "…", "channel": "…", "published": "AAAA-MM-JJ"}]}}`.

## 6. Les pages et les adresses

| Langue | Accueil du Blog | Dossier des pages | Modèle de l'accueil | Modèle d'une page de jeu |
|---|---|---|---|---|
| en (défaut, `x-default`) | `blog.html` | `blog/` | `whats-new.html` | `games/league-of-legends.html` |
| fr | `blog-fr.html` | `blog-fr/` | `nouveautes.html` | `jeux/league-of-legends.html` |
| es | `blog-es.html` | `blog-es/` | `novedades.html` | `juegos/league-of-legends.html` |
| de | `blog-de.html` | `blog-de/` | `neuigkeiten.html` | `spiele/league-of-legends.html` |
| pt-BR | `blog-pt.html` | `blog-pt/` | `novidades.html` | `jogos/league-of-legends.html` |

Une page a la même adresse relative `<dossier>/<id>.html` dans les 5 langues, donc ses liens hreflang se déduisent de son `id`. `x-default` pointe vers l'anglais. Au lancement : 5 accueils + 14 fiches × 5 langues = **75 pages**.

**Fabrication** (même méthode que la News) : la page modèle de la langue fournit l'en-tête, le pied de page, le menu de langue et la CSP ; ses liens de langue, canonical et hreflang sont redirigés vers les pages du Blog ; `<title>`, description, `og:title` et `og:description` sont remplacés (l'`og:image` du modèle est gardée) ; le paramètre `visite?p=` du compteur devient `/blog/<id>` ; le contenu de `<main>` est remplacé ; les données structurées du modèle (`FAQPage`, `BreadcrumbList`) sont remplacées par celles de la page. Les pages en sous-dossier gardent les chemins en `../` du modèle. **Un seul script est ajouté, et seulement aux fiches qui affichent des top plays** : le petit script de lecture au clic (§14), en ligne sur une seule ligne, autorisé par son empreinte SHA-256 ajoutée à `script-src`. La CSP du modèle est sinon gardée octet pour octet, avec en plus la directive `frame-src https://www.youtube-nocookie.com` (juste avant `object-src 'none'`).

**L'accueil du Blog** : l'accroche (kicker, titre, phrase d'introduction), puis la grille des jeux qui ont une fiche visible (logo, nom, description), dans l'ordre fixe `league-of-legends`, `counter-strike-2`, `valorant`, `rocket-league`, `dota-2`, `overwatch-2`, `rainbow-six-siege`, `call-of-duty`, `mobile-legends`, `honor-of-kings`, `ea-sports-fc`, `starcraft-2`, `starcraft-brood-war`, `wild-rift` (un jeu ajouté plus tard passe à la fin), puis, quand il y en a, « Derniers articles » (guides et notes de version, du plus récent au plus ancien, 12 au plus). Les puces de filtre de la maquette ne sont pas reprises : la grille des jeux fait office de catégories.

**La page d'un jeu**, dans l'ordre : fil d'Ariane (Accueil › Blog › jeu), logo et titre, description, les sections (intertitre, paragraphes, puis « Sources : [1] [2] » vers la liste finale), le bloc des top plays (§7), la liste des sources (numéro, titre, domaine, lien `rel="noopener"`), « Vérifié le <updated> », la ligne de transparence, l'encadré « Suivre <jeu> avec eSportly » (lien vers la page de jeu existante et bouton de la bêta, comme sur les pages News), les « Articles sur <jeu> » quand il y en a, puis « Autres jeux » (les autres fiches). Données structurées : `Article` (`headline`, `description`, `datePublished`, `dateModified`, `inLanguage`, `mainEntityOfPage`, `author` et `publisher` sous forme d'organisations, `citation` : les adresses des sources) et `BreadcrumbList`. Le nom du jeu est lu dans le fil d'Ariane de la page de jeu existante.

**Les textes fixes de la page** (les noms de jeux ne se traduisent pas) :

| | en | fr | es | de | pt-BR |
|---|---|---|---|---|---|
| Kicker et menu | Blog | Blog | Blog | Blog | Blog |
| Titre de l'accueil | The games behind the matches | Les jeux derrière les matchs | Los juegos detrás de los partidos | Die Spiele hinter den Matches | Os jogos por trás das partidas |
| Phrase | What each game is, how its pro scene works and how to follow it, with the sources we used. | Ce qu'est chaque jeu, comment fonctionne sa scène pro et comment la suivre, avec les sources utilisées. | Qué es cada juego, cómo funciona su escena profesional y cómo seguirla, con las fuentes que hemos usado. | Was jedes Spiel ist, wie die Profiszene funktioniert und wie du sie verfolgst – mit den verwendeten Quellen. | O que é cada jogo, como funciona a cena profissional e como acompanhá-la, com as fontes que usamos. |
| Grille | Games | Jeux | Juegos | Spiele | Jogos |
| Derniers articles | Latest articles | Derniers articles | Últimos artículos | Neueste Artikel | Últimos artigos |
| Articles sur le jeu | Articles about {game} | Articles sur {game} | Artículos sobre {game} | Artikel zu {game} | Artigos sobre {game} |
| Sources | Sources | Sources | Fuentes | Quellen | Fontes |
| Vérifié le | Checked on {date} | Vérifié le {date} | Comprobado el {date} | Geprüft am {date} | Verificado em {date} |
| Transparence | Written with AI assistance and checked against the sources cited. | Rédigé avec l'aide de l'IA et vérifié par rapport aux sources citées. | Redactado con ayuda de IA y comprobado con las fuentes citadas. | Mit KI-Unterstützung verfasst und anhand der genannten Quellen geprüft. | Escrito com ajuda de IA e conferido com as fontes citadas. |
| Encadré | Follow {game} with eSportly | Suivre {game} avec eSportly | Sigue {game} con eSportly | {game} mit eSportly verfolgen | Acompanhe {game} com o eSportly |
| Lien vers la page de jeu | See what eSportly does for {game} | Voir ce que fait eSportly pour {game} | Descubre qué hace eSportly por {game} | Das kann eSportly für {game} | Veja o que o eSportly faz por {game} |
| Autres jeux | Other games | Autres jeux | Otros juegos | Weitere Spiele | Outros jogos |
| Top plays | Top plays right now | Top plays du moment | Top plays del momento | Top Plays im Moment | Top plays do momento |
| Note des top plays | Videos from the game's official YouTube channels, ranked by views this week. A video loads from YouTube only when you click it. | Vidéos des chaînes YouTube officielles du jeu, classées par vues cette semaine. Une vidéo ne se charge depuis YouTube que lorsque tu cliques dessus. | Vídeos de los canales oficiales de YouTube del juego, por vistas esta semana. Un vídeo solo se carga desde YouTube cuando haces clic en él. | Videos der offiziellen YouTube-Kanäle des Spiels, nach Aufrufen dieser Woche sortiert. Ein Video wird erst nach einem Klick von YouTube geladen. | Vídeos dos canais oficiais do jogo no YouTube, ordenados por visualizações nesta semana. Um vídeo só é carregado do YouTube quando você clica nele. |
| Lire (libellé accessible du bouton) | Play: {title} | Lire : {title} | Reproducir: {title} | Abspielen: {title} | Reproduzir: {title} |

Les dates affichées (« Vérifié le », date d'une vidéo) s'écrivent « jour mois année » dans la langue de la page, avec les listes de mois de `actualites.py`.

**Sitemap.** Les entrées du Blog sont encadrées de marqueurs XML `<!-- blog -->` et `<!-- /blog -->`, posés une seule fois par le script d'application (§8) ; le générateur réécrit tout ce qui est entre eux (une ligne par page, triées par adresse, 5 liens hreflang et `x-default`, `lastmod` égal à `updated` pour une page et à la plus récente des `updated` visibles pour un accueil du Blog, `changefreq` `weekly`). **Pages orphelines** : un fichier de `blog/`, `blog-fr/`, `blog-es/`, `blog-de/`, `blog-pt/` ou un accueil du Blog sans page source est une erreur qui s'affiche sans rien supprimer (la suppression se fait à la main).

## 7. Les top plays

**Sélection** (`topplays.py`, bibliothèque standard seulement, lancé chaque matin). Pour chaque jeu de `channels.json` :

1. Lire le flux de chacune de ses chaînes (en-tête `User-Agent` identifiant le site, délai de 20 s, un second essai).
2. Garder les vidéos publiées dans les 7 derniers jours, ou dans les 21 derniers s'il y en a moins de 3 ; écarter les titres qui contiennent l'un des mots entiers `live`, `livestream`, `replay`, `full vod`, `full match`, `shorts` ou `vertical` (sans tenir compte de la casse ; `#shorts` est écarté, `Shortstop` ne l'est pas).
3. Classer par nombre de vues décroissant, puis garder les 3 premières dont l'**intégration est autorisée** : `https://www.youtube.com/oembed?format=json&url=<adresse de la vidéo encodée>` répond 200 (délai de 20 s, un second essai ; une vidéo dont la page oEmbed ne répond pas 200 est écartée, la suivante est essayée).
4. Écrire le résultat dans `blog-src/topplays.json`.

**Pannes.** Le jeu n'est mis à jour que si **toutes** ses chaînes ont répondu ; sinon il garde sa sélection de la veille. Quand `fetched` a plus de 14 jours, la page n'affiche plus le bloc. Un jeu sans vidéo n'affiche pas de bloc.

**Données de tiers.** Un titre est coupé à 100 caractères, débarrassé des caractères de contrôle, puis échappé dans le HTML (attributs compris) et les données structurées. Un identifiant de vidéo qui ne respecte pas `^[A-Za-z0-9_-]{11}$` est rejeté. Chaque vidéo est une carte « au clic » (§14) : aucune ressource de tiers, aucune vignette, aucun cookie et aucune requête vers YouTube ou Google avant le clic ; le clic charge le lecteur renforcé `youtube-nocookie.com` à la place de la carte.

**Affichage.** Un bloc de 3 cartes de lecture, chacune avec sa légende, puis la note du §6. Il vient de `blog.py`, qui lit `topplays.json` : les pages ne sont jamais modifiées « au milieu ».

**Chaînes.** Au lancement, Claude cherche pour chaque jeu la ou les chaînes officielles et leur preuve (§10) ; l'utilisateur valide la liste une fois. Un jeu sans chaîne officielle claire reste sans bloc.

**Agent.** Le script ne décide rien : il applique une liste validée. Plus tard, dans le chantier de l'agent, Claude pourra proposer de nouvelles chaînes (par pull request) et s'inspirer des vidéos qui montent pour suggérer des sujets d'articles, sans jamais les recopier.

## 8. Les liens vers le Blog

Modification faite **une seule fois** par un script d'application jetable, avec contrôle que chaque point d'insertion existe exactement une fois :

- **Accueils (5).** Un lien « Blog » (libellé du §6) dans le pied de page, liste « L'app », après « News » ; dans le panneau mobile, après « News ». Dans le menu du haut, après « News », **seulement si** une mesure à 1280 px de large montre que le menu tient encore dans les 5 langues (sinon il n'y est pas).
- **Pages de jeux existantes (70).** Juste avant le `<h2>` « Autres jeux », entre les marqueurs `<!-- blog-guide -->` et `<!-- /blog-guide -->`, une ligne `<p class="guide"><a href="…">Guide : <jeu>, le jeu et sa scène pro →</a></p>` générée par `blog.py` quand la fiche est visible, vide sinon ; quelques règles de style ajoutées au `<style>` de ces pages. Libellés : Guide: {game}, the game and its pro scene → ; Guide : {game}, le jeu et sa scène pro → ; Guía: {game}, el juego y su escena profesional → ; Ratgeber: {game} und seine Profiszene → ; Guia: {game}, o jogo e sua cena profissional →.
- **Politiques de confidentialité (voir aussi §14 ; 5 pages : `privacy.html`, `confidentialite.html`, `privacidad.html`, `datenschutz.html`, `privacidade.html`).** Une sous-section « 6e. Vidéos du Blog » ajoutée une seule fois, à la main, après « 6d » : les pages du Blog intègrent des lecteurs YouTube en mode renforcé (`youtube-nocookie.com`), chargés quand on arrive dessus en défilant ; YouTube (Google) reçoit alors l'adresse IP et des informations techniques du navigateur et applique sa propre politique ; aucun cookie de suivi n'est posé avant la lecture ; rien d'autre n'est transmis par le site ; la date « Dernière mise à jour » change. Le texte est proposé par Claude et **à valider par l'utilisateur** (c'est un texte juridique).
- **Sitemap.** Les marqueurs `<!-- blog -->` et `<!-- /blog -->`, avant `</urlset>`.
- **`.assetsignore`.** La ligne `blog-src`.

## 9. Les générateurs

Bibliothèque standard seulement, commentaires en français, identifiants en anglais, docstring d'usage. Tests : `unittest`, qui restent dans le dépôt.

- **`.github/scripts/blog.py`** : `load_pages`, `load_channels`, `load_topplays` (validation, §5) ; `render_page`, `render_hub`, `render_guide_link`, `render_sitemap_block` ; `generate(root, now)` ; `main(argv, root, now, fetch)`. Réutilise de `actualites.py` : `update_between`, `extract_between`, `paris`, `http_get`, les listes de mois et le traitement des fins de ligne (`_same_eol` devient `same_eol`, seul changement à `actualites.py`, avec le test qui l'appelle).
- **Ligne de commande** : sans option, génère ; `--essai` dit ce qui changerait sans rien écrire ; `--verifier` valide seulement `blog-src/` ; `--sources` (réseau, à la demande, jamais dans le job) contrôle les sources (§10).
- **`.github/scripts/topplays.py`** : `read_feed`, `select_videos`, `refresh`, `main` ; options `--essai` et `--verifier` (valide `channels.json`).
- **Écriture** : tout est calculé en mémoire, puis seuls les fichiers dont le contenu change sont écrits, avec `encoding="utf-8", newline=""` (arbre de travail en CRLF). Deux exécutions d'affilée donnent le même résultat. Une erreur de validation arrête le script avant toute écriture, avec le code de sortie 1.
- **Job du matin.** Deux étapes ajoutées à `matchs.yml` après « Mise à jour des news » et avant l'envoi : « Top plays du moment » (`python3 .github/scripts/topplays.py`) puis « Mise à jour du blog » (`python3 .github/scripts/blog.py`), chacune avec `continue-on-error: true` et `timeout-minutes: 3`. Pas de déclenchement à chaque fusion : la pull request contient déjà les pages générées.
- **Outils locaux** : Python 3.13 ; `blog.py --verifier` marche sans base des fuseaux, la génération demande `PYTHONTZPATH` ou `tzdata` sous Windows.

## 10. La rédaction des fiches

**Règles de contenu.** Des faits durables seulement (genre, éditeur, année de sortie, format d'un match, noms et fonctionnement des grandes compétitions, manières de les suivre) ; rien de daté : ni champion actuel, ni classement, ni saison en cours, ni cagnotte. De 3 à 5 sources par fiche, dont **au moins une officielle** (éditeur, ligue ou tournoi) ; pas de blog, de forum, de réseau social ni de page payante. Tout est reformulé, aucune phrase recopiée, aucune image reprise des sources (les logos des jeux sont ceux du site). Plan de 4 sections : le jeu en bref, comment fonctionne la scène pro, les grandes compétitions, comment les suivre ; de 350 à 500 mots.

**Déroulé, un jeu à la fois.**

1. **Sources** : recherche, puis lecture des pages elles-mêmes.
2. **Tableau des affirmations** `blog-src/claims/<id>.md` : `| Affirmation | Source | Extrait |`, une ligne par fait ; `Source` est un `id` de source de la page ; `Extrait` est une suite d'au plus 12 mots copiée de la page citée, ou `manuel : <raison>` pour une page qu'un script ne sait pas lire.
3. **Brouillon en anglais**, qui fait foi.
4. **Contrôle mécanique `blog.py --sources`** : chaque adresse répond (code 200 après redirections) ; chaque extrait figure dans le texte de la page citée (texte extrait du HTML, majuscules, espaces et guillemets normalisés) ; chaque fiche de jeu a son tableau ; chaque source citée est utilisée par au moins une affirmation. Exit 1 au moindre manque ; les lignes `manuel` sont listées à part.
5. **Contrôle indépendant** : un autre agent, qui ne voit que le brouillon et les pages sources, cherche toute affirmation non étayée ; deux passes de 7 fiches.
6. **Traduction** en français, espagnol, allemand et portugais, à partir de l'anglais ; les noms de jeux et de compétitions restent tels quels ; le générateur vérifie que la structure est identique dans les 5 langues.
7. **Relecture par l'utilisateur** de la version française de chaque fiche, avec son tableau d'affirmations.

**Ordre.** Deux fiches pilotes d'abord, `league-of-legends` et `valorant`, puis une **pause pour la relecture de l'utilisateur** (ton, profondeur, mise en page), puis les 12 autres. Un jeu sans source officielle reste sans fiche.

## 11. Vérification

**Tests unitaires** (`test_blog.py` et `test_topplays.py`) :

- *Validation* : chaque règle du §5, avec un test qui la viole (champ inconnu, langue manquante, source non déclarée citée, adresse non https, identifiant en double, jeu inconnu, `updated` avant `date`, texte avec `<`, trop de sections).
- *Pages* : échappement du texte et des données structurées (`&`, `<`, guillemets, `</script>`), liens `../` en sous-dossier, canonical et hreflang des 5 langues, `x-default`, 75 pages au lancement, `lastmod` tiré de `updated`, page future non générée, ordre des jeux sur l'accueil, nombre d'entrées du sitemap, pages orphelines signalées sans suppression, fins de ligne conservées, seconde exécution sans changement, CSP des pages identique à celle du modèle sauf la directive `frame-src https://www.youtube-nocookie.com` ajoutée aux pages qui affichent des vidéos.
- *Liens vers les fiches* : le bloc des pages de jeux apparaît seulement quand la fiche est visible ; deux passages identiques.
- *Sources* : faux accès réseau (adresse en 404, extrait présent, extrait absent, ligne `manuel`, tableau manquant, source inutilisée).
- *Top plays* : lecture d'un flux d'exemple, fenêtre de 7 puis 21 jours, classement, exclusion des directs, limite de 3, panne d'une chaîne qui garde la veille, bloc masqué au-delà de 14 jours, titre hostile, identifiant de vidéo invalide, validation de `channels.json`, vidéo dont l'intégration est interdite écartée (la suivante est prise), lecteur intégré avec ses attributs et sa légende, seconde exécution sans changement.
- *Job* : les trois étapes (news, top plays, blog) ont `continue-on-error: true` et `timeout-minutes` d'au plus 3 (le test du job de la News est étendu).

**Contrôles sur le vrai site** avant la pull request (hors dépôt, dérivés du vérificateur de la News) : dans le sitemap, 180 adresses plus les 5 accueils du Blog et 5 par fiche (255 pour 14 fiches), chacune avec son fichier et son canonical ; maillage hreflang complet ; aucun lien cassé de plus ; exécutions jumelles avant/après de `matchs.py`, `actualites.py`, `topplays.py` et `blog.py` (pages de matchs, d'équipes et d'événements identiques ; pages de jeux différentes seulement par le bloc inséré) ; `bascule_appstore.py --essai` sans nouveau « reste » ; navigateur : l'accueil du Blog, une fiche en 5 langues, le bloc des pages de jeux, les liens de l'accueil (ordinateur, mobile et la mesure du menu à 1280 px), les lecteurs YouTube s'affichent et se lancent, aucune erreur de CSP, aucun débordement à 375 px.

**Retour arrière** : `git revert` de la pull request ; `blog-src/` garde l'historique.

## 12. Livraison

Branche `blog` depuis `news` (`--no-track`), pull request visant d'abord `news`, puis redirigée vers `main` après la fusion de la PR n°10. Commits :

1. Spec et plan, et la ligne `blog-src` dans `.assetsignore`.
2. `blog.py`, validation des données (tests d'abord).
3. `blog.py`, pages, hreflang et sitemap.
4. `topplays.py` et la validation de `channels.json`.
5. Les deux étapes du job du matin et l'extension du test du job.
6. Les liens : script d'application sur les 5 accueils, les 70 pages de jeux et le sitemap.
7. Les fiches pilotes, la pause de relecture, puis les 12 autres fiches et `channels.json`.
8. La première génération et ses vérifications.
9. Le README, la revue finale par un relecteur indépendant et la pull request.

Rien n'est poussé ni fusionné sans l'accord de l'utilisateur, et chaque fusion se fait sur sa phrase explicite nommant la PR (d'abord la n°10, puis celle du Blog).

**Terminé quand** les 75 pages sont en ligne, le job du matin a tourné avec les deux nouvelles étapes (sur demande, juste après la fusion), les top plays s'affichent pour les jeux qui ont une chaîne validée, et les contrôles sur le site en ligne ont été refaits.

## 13. Risques et points ouverts

| Risque ou point | Traitement |
|---|---|
| **YouTube refuse peut-être l'accès depuis les serveurs GitHub** (flux testé seulement depuis le poste de travail). | Le bloc garde la veille puis disparaît ; la première exécution à la demande après la fusion le montre. |
| Une **chaîne** jugée officielle par erreur. | Preuve exigée pour chaque chaîne, liste validée à la main, ajout seulement par pull request. |
| **Titres de vidéos** en langue étrangère ou à contenu douteux, affichés tels quels. | Texte échappé et coupé ; le choix des chaînes reste humain ; pas de bloc pour un jeu sans chaîne claire. |
| **Traductions** en es, de et pt non relues par une personne qui parle ces langues. | Le contrôle indépendant réduit le risque sans l'éliminer ; correction par pull request ; mention de transparence sur les pages. |
| **Dérive des sources** (page modifiée ou disparue). | `--sources` avant chaque publication ; vérification mensuelle planifiée envisagée plus tard. |
| Un fait de fiche devenu faux (compétition renommée, format changé). | La date « Vérifié le » est affichée ; les faits datés sont exclus ; correction par pull request. |
| Menu du haut des accueils trop serré pour un lien « Blog ». | Mesure à 1280 px avant d'ajouter le lien ; sinon pied de page et panneau mobile seulement. |
| Volume : 14 fiches × 5 langues à rédiger, vérifier et relire. | Deux fiches pilotes d'abord ; l'utilisateur relit le français et le tableau d'affirmations. |
| Jeu sans source officielle (par exemple `starcraft-brood-war`). | Pas de fiche pour ce jeu, plutôt qu'une fiche fragile ; le lancement peut compter moins de 14 fiches. |
| Dépendance à la PR n°10. | Branche créée depuis `news` ; redirection vers `main` après la fusion. |
| Pages protégées par identifiant tant que le site est en préproduction. | Le Worker les protège comme le reste ; aucun changement. |
| **Vie privée (RGPD) : les lecteurs YouTube contactent Google** quand on arrive dessus en défilant (adresse IP, informations du navigateur). | Mode renforcé `youtube-nocookie.com` (pas de cookie de suivi avant la lecture), chargement différé, pas de lecture automatique ; sous-section ajoutée aux 5 politiques de confidentialité, texte à valider par l'utilisateur. |
| **Vitesse** : 3 lecteurs par fiche de jeu. | `loading="lazy"` ; mesure à la première génération. |
| Une vidéo dont le propriétaire interdit l'intégration. | Écartée à la sélection si `oembed` ne répond pas 200 (vérifié le 27 octobre : 200 pour une vidéo normale, 404 pour un identifiant inexistant ; le cas « intégration interdite » reste à vérifier sur un exemple réel). |
| Les politiques de confidentialité sont rédigées dans le dépôt de l'application puis copiées ici (README) : la modification faite ici serait écrasée si ce dépôt reste la source. | À confirmer avec l'utilisateur avant la fusion. |

## 14. Amendements du 27 octobre (soir), après les fiches pilotes

Décisions de l'utilisateur : lancer les 12 autres fiches et **suivre les recommandations** faites à l'arrêt de la tâche 9. Elles remplacent tout texte contraire des §2, §5, §6, §7, §8, §11 et §13.

1. **Temps forts seulement.** Sur les vraies données, les vidéos les plus vues étaient des rediffusions complètes de 4 à 7 heures et des vidéos verticales très courtes. `channels.json` accepte par chaîne un champ facultatif `include` : une expression régulière (syntaxe `re` de Python, insensible à la casse, 1 à 200 caractères, qui doit se compiler). Si elle est présente, seules les vidéos de cette chaîne dont le titre la contient sont candidates ; elle s'applique avant le classement par vues. Pour les chaînes LoL Esports et VALORANT Champions Tour : les titres contenant `highlights`, `top plays`, `best plays`, `game-changing plays` ou `best moments` (mots entiers) ; `shorts` et `vertical` sont exclus partout (§7). S'il y a moins de 3 vidéos qualifiées sur 21 jours, le bloc en montre moins ; s'il n'y en a aucune, il disparaît. Une chaîne sans `include` garde le comportement du §7.
2. **Lecteur au clic, sans vignette** (retour à la première décision de l'utilisateur, par recommandation : les règles de consentement européennes couvrent tout stockage dans le navigateur, et `youtube-nocookie.com` en écrirait avant la lecture). Chaque vidéo est d'abord une carte sans aucune ressource de tiers : `<li class="play"><a class="video" href="https://www.youtube.com/watch?v=<id>" data-id="<id>" aria-label="Lire : <titre>"><span class="btn" aria-hidden="true">▶</span></a>` puis la légende (titre, chaîne, date) ; sans JavaScript, le lien ouvre YouTube. Un petit script en ligne (`PLAYER_JS`, une seule ligne, sans dépendance) intercepte le clic, vérifie que `data-id` respecte `^[A-Za-z0-9_-]{11}$` et remplace la carte par `<iframe src="https://www.youtube-nocookie.com/embed/<id>?autoplay=1" title="<titre>" allowfullscreen referrerpolicy="strict-origin-when-cross-origin" allow="autoplay; encrypted-media; picture-in-picture">`. Aucune requête vers YouTube ou Google avant le clic. Ce script n'est ajouté qu'aux fiches qui affichent des top plays ; il est autorisé par son empreinte SHA-256 ajoutée à `script-src` de la CSP, en plus de `frame-src https://www.youtube-nocookie.com` (juste avant `object-src 'none'`). Le libellé `play` est ajouté (« Lire : {titre} » et équivalents) et la note des top plays est réécrite (§6). L'utilisateur peut revenir aux lecteurs visibles d'emblée : c'est un seul commit (tâche 13).
3. **Politiques de confidentialité.** La sous-section « 6e » (tâche 14) est reformulée pour le lecteur au clic : aucune requête vers YouTube avant le clic ; après le clic, YouTube (Google) reçoit l'adresse IP et des informations techniques du navigateur et peut déposer des cookies selon ses propres règles ; le texte reste à valider par l'utilisateur.
4. **Preuve de la chaîne LoL Esports.** L'utilisateur accepte la preuve indirecte (une rediffusion officielle de lolesports.com) : la règle du §5 n'est pas respectée à la lettre pour cette chaîne, et c'est une décision assumée.
