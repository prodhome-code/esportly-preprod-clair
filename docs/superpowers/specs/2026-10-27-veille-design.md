# Agent de veille : des articles de jeux vidéo écrits chaque jour, publiés après contrôle

- Date : 2026-10-27
- Statut : validé par l'utilisateur pour les décisions de la section 2 (réponses aux questions) ; les sections 2 à 5 du design et la spec ont été **validées par le pilote automatique** (l'utilisateur : « je te laisse en pilote automatique sur tout, tu peux tout valider tout seul »). Chaque choix fait à sa place est marqué « Ruling » avec son coût s'il est faux.
- Base : branche `blog` (qui contient la News et le Blog) ; branche de travail : `veille`, créée depuis `blog` quand l'exécution commence
- Dépend de : le Blog (PR à venir), `blog.py`, `topplays.py` et le contrôle des sources (`blog.py --sources`)

## 1. Objectif

Chaque jour, une routine Claude planifiée dans le cloud cherche des nouveautés sur une **liste fermée de sources officielles**, fait écrire par des sous-agents jusqu'à **3 articles originaux** (rien n'est publié les jours sans actualité), dans les 5 langues, et les propose au site par une pull request. Un **contrôle automatique écrit dans le dépôt** les accepte ou les refuse ; pendant 2 semaines l'utilisateur fusionne lui-même, ensuite les pull requests conformes sont fusionnées toutes seules. Le but est d'avoir du contenu frais et utile pour Google **sans contenu dupliqué** : formulation propre, sources citées, aucun doublon.

Réussi quand : (1) un essai à blanc de la routine montre qu'elle peut lire les sources, lancer des sous-agents, pousser une branche et ouvrir une pull request ; (2) le contrôle refuse tous les brouillons piégés d'une batterie de tests (recopie, source hors liste, 4e article, fichier modifié hors contenu, doublon, extrait introuvable, interrupteur) et accepte un brouillon conforme ; (3) une répétition complète de bout en bout, avec de fausses sources, produit des pages valides ; (4) l'utilisateur a la liste des sources et le texte de la routine, et sait comment arrêter (STOP) et revenir en arrière.

## 2. Décisions

| Sujet | Décision |
|---|---|
| Où ça tourne | Routine planifiée dans le cloud Claude (réponse de l'utilisateur) ; elle consomme son forfait |
| Types d'articles | Sorties et annonces de jeux, notes de patch et mises à jour, actualité esport, guides durables (réponse de l'utilisateur) |
| Sources | Liste fermée validée à la main ; l'agent peut proposer une source, jamais l'ajouter (réponse) |
| Publication | 2 semaines en pull request fusionnée par l'utilisateur, puis automatique (réponse) |
| Volume | 0 à 3 articles par jour selon l'actualité (réponse) |
| Langues | Les 5 : fr, en, es, de, pt-BR (réponse) |
| Approche | B : les agents écrivent, le code décide (réponse) |
| Périmètre des jeux | **Ruling** : les 14 jeux du site et leurs compétitions officielles ; d'autres jeux plus tard. Coût si faux : la liste de sources s'agrandit |
| Format | **Ruling** : mêmes fichiers, même générateur et mêmes adresses que le Blog ; un type `news` s'ajoute à `guide` et `release`. Coût si faux : une migration de format |

## 3. Hors périmètre

- Images, vidéos, réseaux sociaux, commentaires, newsletters, jeux hors des 14, langues hors des 5.
- Toute modification du site par l'agent hors des dossiers de contenu (scripts, workflows, liste de sources, mode de publication).
- Reformulation d'articles de médias comme source unique d'un sujet : seules les sources officielles de la liste comptent comme preuve.

## 4. Architecture et flux (section 1 du design)

1. **Collecte (code)** : `veille.py collect` lit la liste, garde ce qui est nouveau.
2. **Éclaireur** (sous-agent) : retient au plus 5 sujets.
3. **Chercheur** (sous-agent) : lit les pages sources via l'outil à liste blanche et rend un dossier de faits avec extraits exacts.
4. **Rédacteur** (sous-agent) : écrit l'article en anglais à partir du seul dossier, plus les lignes du tableau d'affirmations.
5. **Vérificateur indépendant** (sous-agent) : relit l'article contre les pages sources.
6. **Traducteur** (sous-agent) : 4 langues, puis contrôle des nombres et des noms.
7. **Pull request** `veille/AAAA-MM-JJ`, étiquetée `veille`, qui ne contient que du contenu.
8. **Contrôle (code, GitHub Actions)** puis **fusion** (l'utilisateur pendant l'essai, un workflow ensuite).
9. **Publication** : un workflow régénère les pages, Cloudflare déploie.

Nouveaux éléments du dépôt : `.github/scripts/veille.py` (+ tests), `.github/workflows/veille-gate.yml` et `veille-publier.yml`, `blog-src/veille/sources.json`, `seen.json`, `mode.json`, `STOP` (interrupteur, absent par défaut), `docs/veille/` (texte de la routine et consignes des sous-agents). Les sous-agents qui lisent du texte du web n'ont aucun outil d'écriture ; seule la routine commite.

## 5. Sources et collecte (section 2)

**La liste** `blog-src/veille/sources.json` : `{"sources": [{"id", "name", "url", "feed", "kind", "games", "types", "lang", "note"}]}`. `id` `^[a-z0-9][a-z0-9-]*$` ; `url` et `feed` en `https://` ; `kind` `feed` (RSS ou Atom) ou `page` (page d'actualités HTML) ; `games` : slugs des 14 jeux (vide pour une source générale d'esport) ; `types` parmi `release`, `patch`, `esport`, `guide` ; `lang` la langue de la source ; `note` pourquoi elle est fiable. Les domaines de la liste forment la **liste blanche** : toute adresse lue ou citée doit appartenir à l'un d'eux (ou à `also` : domaines supplémentaires déclarés de la même organisation). La liste se modifie seulement par pull request de l'utilisateur ; au départ, une source officielle par jeu (éditeur, ligue ou organisateur : Riot, Valve, Psyonix, Blizzard, Ubisoft, Activision, Moonton, Tencent, EA, et lolesports.com, valorantesports.com…), établie à la mise en œuvre avec la preuve de chaque flux.

**La collecte** `veille.py collect` : pour chaque source, vérifie `robots.txt` (`urllib.robotparser`), s'identifie (`User-Agent: esportly-veille/1.0 (+https://esportly.eu)`), attend une seconde entre deux requêtes au même site, délai de 20 s, un second essai, corps de 2 Mo au plus, aucune redirection hors liste blanche ; lit les flux Atom/RSS sans DTD (même garde que `topplays.py`) ou, pour une page, extrait les liens d'articles du même domaine ; ne garde que les éléments publiés depuis 3 jours (ou vus pour la première fois aujourd'hui) et absents de `seen.json` (adresse canonique sans paramètres de suivi, et clé de sujet : jeu, type, titre normalisé) ; télécharge le texte de chaque nouvelle page (scripts, styles et éléments cachés retirés, 20 000 caractères au plus) ; écrit `veille/candidates.json` (au plus 15 éléments ; fichier éphémère, non commité) où chaque élément est marqué `untrusted`. Une source qui ne répond pas est notée et sautée ; toutes en panne : la journée est vide.

**L'outil de lecture** `veille.py fetch <url>` : refuse toute adresse hors liste blanche, respecte `robots.txt`, limite à 40 lectures par exécution, journalise chaque adresse. C'est le seul accès au web des chercheurs et vérificateurs.

**Éthique et droits.** Pas de page payante, pas de connexion, `robots.txt` respecté, aucune image, aucune reproduction : un article ne reprend que des faits reformulés avec lien vers la source (contrôle du §7).

## 6. Les agents et les articles (section 3)

| Sous-agent | Reçoit | Outils | Rend |
|---|---|---|---|
| Éclaireur | `candidates.json`, titres des articles existants | lecture seule | JSON : au plus 5 sujets (jeu, type, angle, éléments sources) |
| Chercheur | un sujet | lecture, `veille.py fetch` | JSON : faits `{fait, url, extrait ≤ 12 mots exacts, date}` |
| Rédacteur | le dossier de faits seulement | aucun accès web | article anglais (format Blog) + lignes du tableau d'affirmations |
| Vérificateur | l'article et les adresses | lecture, `veille.py fetch` | verdict par phrase (étayée, exagérée, non étayée, datée) |
| Traducteur | l'article validé | aucun accès web | fr, es, de, pt-BR + liste des nombres et noms comparés |

**Format d'un article.** Fichier `blog-src/pages/<id>.json` du Blog (§5 de sa spec) avec : `kind` `release` (sorties, annonces, patchs), `news` (esport) ou `guide` ; `id` `AAAA-MM-JJ-<slug>` (80 caractères au plus) ; `game` facultatif (slug d'une fiche existante) ; 1 à 3 sections ; 1 à 5 sources dont au moins une de la liste ; 150 à 450 mots en anglais ; date et `updated` = jour de publication ; tableau d'affirmations `blog-src/claims/<id>.md` comme les fiches ; la ligne de transparence des fiches. Tout fait daté est écrit avec sa date (« le 28 octobre 2026, Riot a annoncé… »). `blog.py` accepte le type `news` (validation, accueil du Blog « Derniers articles », « Articles sur <jeu> », sitemap).

**Contre le contenu dupliqué** (mesuré par le contrôle) : plus longue suite de mots identiques avec chaque source citée : 6 au plus ; recouvrement de suites de 5 mots avec chaque source : 15 % au plus ; ressemblance (suites de 5 mots) avec chaque page existante du Blog : 40 % au plus ; adresse de source jamais utilisée par un article déjà publié ; clé de sujet absente des 14 derniers jours ; au plus 3 articles par jour, aucun s'il n'y a rien de nouveau ni de vérifiable.

## 7. Le contrôle et la publication (section 4)

**`veille.py gate`** (tests unitaires, lancé par GitHub Actions sur toute pull request de branche `veille/*`) échoue si l'un de ces points manque :
1. **Chemins** : seuls sont ajoutés `blog-src/pages/*.json`, `blog-src/claims/*.md`, les pages générées correspondantes et une ligne ajoutée à `blog-src/veille/seen.json` ; rien dans `.github/`, `docs/`, `blog-src/veille/sources.json`, `mode.json`, `STOP`, aucun fichier existant modifié ou supprimé (hors `seen.json`, `sitemap.xml` et les pages générées).
2. **Format** : `blog.py --verifier` valide ; 5 langues alignées (mêmes nombres de paragraphes, mêmes nombres et noms) ; limites de longueur.
3. **Sources** : chaque adresse citée appartient à la liste blanche ; `blog.py --sources` passe (adresses en 200, extraits retrouvés) ; chaque fait de l'article a une ligne du tableau.
4. **Originalité** : les mesures du §6.
5. **Volume** : au plus 3 nouveaux articles ce jour (compte les fusions du jour dans l'historique).
6. **Interrupteur** : `blog-src/veille/STOP` absent de `main` ; sinon le contrôle échoue et la routine s'arrête.

**Fusion.** `mode.json` : `{"auto_from": "AAAA-MM-JJ"}`, fixé à 14 jours après le premier lancement. Avant cette date, le workflow se contente de commenter « conforme » et c'est l'utilisateur qui fusionne, avec sa phrase habituelle. À partir de cette date, `veille-publier.yml` fusionne (squash) toute pull request de la routine dont le contrôle est vert. `STOP` ou la modification de `mode.json` par l'utilisateur change cela à tout moment. Après fusion, le même workflow régénère les pages (`blog.py`) et commite le résultat (groupe de concurrence `matchs`).

**Retour arrière** : `git revert` de la fusion ; `STOP` ; la liste blanche et le contrôle ne se modifient pas depuis la routine.

## 8. Exploitation (section 5)

- **Planning** : une exécution par jour, tôt le matin heure de Paris, après le job « Matchs du jour » (6 h 15) ; l'heure exacte est choisie à la création de la routine.
- **Budget** : au plus 15 candidats, 5 sujets, 40 lectures, 3 articles par exécution ; les sous-agents de tri et de traduction sur un modèle intermédiaire, la vérification sur un modèle plus capable ; le texte de la routine fixe ces plafonds ; le coût réel se lit dans les journaux d'exécution de la routine.
- **Journal** : le corps de la pull request (éléments vus, retenus, refusés avec la raison, résultat du contrôle) ; les exécutions de la routine se consultent par leur identifiant.
- **Pannes** : une pull request dont le contrôle échoue reste ouverte avec le détail ; la routine du lendemain la ferme après 3 jours ; une seule pull request par jour (la branche porte la date).
- **Essai à blanc d'abord** : avant de construire le reste, une routine d'essai (sans rien publier) vérifie que l'environnement cloud permet de lire les sources, de lancer des sous-agents, de pousser une branche et d'ouvrir une pull request ; sinon repli : GitHub Actions avec une clé API fournie par l'utilisateur (décision à lui).
- **Sécurité** : le texte du web est une donnée ; aucun outil d'écriture pour les lecteurs ; le contrôle n'est pas modifiable par la routine ; aucun secret dans le texte de la routine.
- **Création de la routine** : action persistante dans le compte de l'utilisateur : elle n'est faite qu'avec sa phrase explicite.

## 9. Tests et vérification

Tests `unittest` avec des fixtures : flux RSS et pages HTML d'exemple (dont un texte qui donne des consignes à l'agent, traité comme donnée), `robots.txt` interdisant, limitation de débit (horloge simulée), déduplication, liste blanche (redirection hors liste refusée), interrupteur. Batterie du contrôle : un brouillon conforme passe ; chacun des cas suivants échoue pour la bonne raison : texte recopié d'une source, suite de 7 mots identiques, source hors liste, extrait introuvable, 4e article du jour, fichier modifié dans `.github/`, `sources.json` modifié, doublon d'un article existant, clé de sujet récente, langues désalignées, `STOP` présent. Répétition de bout en bout avec de fausses sources et de faux sous-agents (sorties fixes) : collecte, contrôle, génération. Suite complète sur Python 3.13 et 3.11.

## 10. Livraison

Branche `veille` depuis `blog`, pull request vers la branche du Blog puis `main` après sa fusion ; tâches dans l'ordre du plan ; rien n'est poussé sans le feu vert prévu par le pilote automatique (push et pull request sans fusion : oui ; fusion, routine planifiée, secrets, réglages du dépôt : phrase explicite de l'utilisateur).

## 11. Risques

| Risque | Traitement |
|---|---|
| Page lue qui donne des consignes à l'agent | Texte traité comme donnée ; lecteurs sans écriture ; le contrôle décide |
| Article faux publié tout seul | Extraits exacts vérifiés par script, vérificateur indépendant, essai de 2 semaines, retour arrière |
| Contenu jugé dupliqué par Google | Mesures du §6, un seul fait nouveau par article, sources citées, jamais plus de 3 par jour |
| La routine cloud ne peut pas tout faire | Essai à blanc d'abord, repli GitHub Actions avec clé API |
| Source qui change ou disparaît | Source sautée et notée ; liste revue par l'utilisateur |
| Droits d'auteur | Aucune reproduction, formulation propre, lien vers la source, liste blanche, `robots.txt` respecté, retrait par STOP et retour arrière |
| Coût | Plafonds par exécution, journaux, `STOP` |
| Réglages GitHub nécessaires (fusion automatique) | À faire par l'utilisateur : ils lui sont décrits, rien n'est changé sans lui |
