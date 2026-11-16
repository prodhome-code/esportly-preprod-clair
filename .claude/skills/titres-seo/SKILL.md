---
name: titres-seo
description: Refait les balises title et les métadescriptions des pages du site eSportly dans ses 5 langues (fr, en, es, de, pt-BR) selon regles.md, avec les volumes et mots-clés liés de SEMrush (base de chaque langue). À utiliser quand l'utilisateur veut de nouveaux titles ou descriptions pour des pages du site, ou vérifier ceux qui existent.
---

# Titles et métadescriptions du site eSportly

Adaptation au site du skill `generateur-title` de l'utilisateur (`C:\Users\horny\Claude\TITLEgenerator`) : même processus (mot-clé
principal validé, puis SEMrush, puis rédaction en suite de mots-clés, puis contrôle), mais par langue, avec les métadescriptions, et
appliqué aux **sources** des pages, jamais aux pages fabriquées.

## 1. Préparer

- Lis `regles.md` (à côté de ce fichier). Ses règles priment sur tes habitudes de rédaction.
- Inventorie les pages : `py -3.13 .claude/skills/titres-seo/scripts/inventaire.py` écrit `docs/seo/inventaire-titres.csv`
  (URL publiée, langue, title et description actuels avec leur longueur, source à modifier). Si l'utilisateur ne vise que certaines
  pages, garde seulement ces lignes.
- La source des titles et descriptions de toutes les pages est `seo/titres.json` à la racine du site (chemin public → `title`,
  `description`) : les scripts qui fabriquent des pages (Blog, News, semaine, événements, Live) y lisent le `<title>`, la description
  et les og:* (`site_chrome.seo`), le H1 gardant le titre de la page (JSON du Blog, LABELS des scripts) ; les pages de jeux et
  d'équipes le reçoivent par `.github/scripts/titres_seo.py` (rejouable, aussi lancé chaque matin par `matchs.yml`). Les pages de
  jeux et d'équipes sont à l'origine copiées du dossier `Site/` du dépôt de l'app : le script remettra les titles après une copie.
- Les pages « à laisser » de `regles.md` (accueils, légales, presse, nouveautés) ne reçoivent pas de nouveau title.

## 2. Mot-clé principal : faire valider avant SEMrush

- Pour chaque famille et chaque langue, déduis un mot-clé principal à partir de l'URL, du title actuel et de la page (ex.
  `/fr/jeux/valorant` → « valorant score en direct » ; `/blog/valorant` → « valorant esports »). Pour une famille de pages (14 jeux,
  26 équipes), un gabarit suffit : « <jeu> score en direct ».
- Affiche un tableau `famille | langue | pages | mot-clé principal proposé` (une ligne par page seulement pour les pages uniques).
- **Attends la validation de l'utilisateur.** Il corrige par lots (« jeux fr : alertes match <jeu> »). Aucune requête SEMrush avant ça.

## 3. Interroger SEMrush, base de la langue

- Les outils SEMrush sont `keyword_research`, `get_report_schema` et `execute_report`. S'ils sont différés, charge-les avec ToolSearch.
- Appelle `keyword_research` pour voir les rapports disponibles, et choisis ceux qui donnent : le volume d'un mot-clé, les mots-clés
  liés, les questions. Ne devine pas de nom de rapport.
- `database` selon la langue : fr → `fr`, en → `us`, es → `es`, de → `de`, pt-BR → `br`. Une requête par mot-clé principal validé
  (une fois par gabarit : « valorant score en direct » sert à la seule page Valorant, mais « esports news » sert à une page), avec
  `display_limit` entre 30 et 50.
- Si SEMrush renvoie une erreur (`no_api_units`, `no_subscription`, `rate_limit`…), transmets son message et son lien tels quels
  et arrête-toi. N'invente jamais de mots-clés ni de volumes.

## 4. Choisir les mots-clés secondaires

- Garde ceux qui ont le plus de volume parmi ceux qui décrivent vraiment la page, sans doublon de sens, dans la langue de la page.
- Singulier ou pluriel, graphie (« e-sport » / « esport ») : ce que SEMrush montre comme recherché.

## 5. Rédiger

- Écris chaque title et chaque description selon `regles.md` : mot-clé principal en tête, 55 à 63 caractères, sans marque
  (ni en suffixe ni ailleurs, sauf sur les accueils) ; description de 120 à 155 caractères, une ou deux phrases, le mot-clé dit autrement.
- Écris le résultat dans `docs/seo/titres-<AAAA-MM-JJ>.csv` (UTF-8 avec BOM, séparateur « ; »), colonnes de l'inventaire plus :
  - `New TITLE`, `nb car title` (Python `len()`, jamais compté à la main) ;
  - `New DESCRIPTION`, `nb car description` ;
  - `Mots-clés retenus` : `principal (volume); secondaire (volume); …`.

## 6. Contrôler

- Lance `py -3.13 .claude/skills/titres-seo/scripts/controle.py docs/seo/titres-<date>.csv`.
- Corrige chaque ligne signalée, recalcule les compteurs, relance, jusqu'à « Aucun problème. ».
- Si une ligne ne peut pas respecter une règle (pas assez de mots-clés pertinents pour 55 caractères, nom de jeu trop long), laisse-la
  la plus proche possible et signale-la à l'utilisateur au lieu de forcer.

## 7. Appliquer dans les sources

- Reporte les titles et descriptions validés dans `seo/titres.json` (une entrée par page, clé = chemin public), lance
  `py -3.13 .github/scripts/titres_seo.py` (toutes les pages listées), puis `blog.py` et `actualites.py` avec `PYTHONUTF8=1` (ils
  doivent répondre 0 fichier changé pour leurs pages : même texte), lance les tests du site, ouvre une pull request vers `main`.

## 8. Rendre compte

Affiche un tableau `URL | ancien title | nouveau title | nb car | nouvelle description | nb car`, puis la liste des lignes à arbitrer
s'il y en a.
