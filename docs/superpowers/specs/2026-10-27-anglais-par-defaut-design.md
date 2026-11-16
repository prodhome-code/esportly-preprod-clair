# Anglais par défaut sur l'accueil d'eSportly

- Date : 2026-10-27
- Statut : à relire par l'utilisateur
- Base : `origin/main` `abea1cb` (27 octobre 2026), site sur `https://esportly.eu` (préproduction, accès protégé par le Worker `esportly-site`)
- Branche de travail : `anglais-par-defaut` (locale, sans suivi distant)

## 1. Objectif

Un visiteur qui ouvre `https://esportly.eu/` voit l'accueil en anglais. Le français reste disponible sur `/fr.html`.

Pourquoi : l'accueil concentre l'autorité et les liens entrants, et le public visé (le e-sport de référence : HLTV, Liquipedia, VLR.gg) est anglophone. Le `x-default` pointe déjà vers l'anglais, et le site est jeune, donc il y a peu de classement à perdre.

Le chantier est réussi quand :

1. `/` est en anglais (`lang="en"`, canonical `/`) et `/fr.html` en français (`lang="fr"`, canonical `/fr.html`).
2. canonical, hreflang, `x-default` et sitemap sont cohérents sur les 5 accueils et sur les sous-pages.
3. Aucun lien interne n'est cassé de plus qu'avant, aucune page française n'est retirée, et l'ancienne adresse `en.html` reste joignable.
4. La bascule App Store (sortie annoncée le 2 novembre 2026) et le job « Matchs du jour » continuent de fonctionner.

## 2. Décisions validées (2026-10-27)

| Sujet | Décision |
|---|---|
| Sens de « d'abord en anglais » | Anglais par défaut sur `/`, le français passe sur `/fr.html` |
| Redirection selon la langue du navigateur | Aucune (mauvaise pour le SEO ; en JavaScript seulement sur ce type d'hébergement) |
| Bandeau « Voir en français » | Aucun : le menu de langue en haut de page suffit pour l'instant |
| Approche | Script de migration rejouable (approche A) |
| Ancienne adresse `en.html` | Page de renvoi vers `/` (canonical + renvoi immédiat), retirée du sitemap |
| Règles de recâblage | Section 6 ; la 404 passe en anglais d'abord |
| Générateur et bascule | Aucun changement de logique (section 10) |
| Problème des URL `.html` redirigées par Cloudflare | Traité à part, hors de ce chantier |

## 3. Hors périmètre

- Détection de la langue du navigateur, bandeau de suggestion de langue.
- Les URL en `.html` que Cloudflare redirige vers l'adresse sans extension (voir section 13).
- Le futur site Astro, le Worker (`worker/index.js`, `wrangler.jsonc`) et tout réglage Cloudflare. Seule exception : la ligne `docs` ajoutée à `.assetsignore` (section 12), qui garde la documentation hors des pages servies et ne change rien au déploiement du site.
- Les traductions : les 5 versions existent déjà.
- Toute mesure SEO (SEMrush, Search Console).

## 4. État actuel (constaté le 27 octobre sur `origin/main`)

- **Un seul conflit de nom : l'accueil.** `/` est `index.html` (français) et l'anglais est `en.html`. Toutes les autres pages ont un nom distinct par langue (`equipes.html` / `teams.html`, `jeux/` / `games/`, `presse.html` / `press.html`…).
- **hreflang des accueils :** fr → `/`, en → `/en.html`, es → `/es.html`, de → `/de.html`, pt-BR → `/pt.html`, `x-default` → `/en.html`. Sur les sous-pages, le `x-default` est déjà anglais.
- **Liens vers l'un des deux accueils :**
  - 448 liens relatifs dans 223 fichiers HTML (476 une fois les 28 liens `.././` ci-dessous normalisés) ;
  - 258 URL absolues dans 200 fichiers (canonical, hreflang, fil d'Ariane des données structurées, `<loc>` du sitemap) ;
  - 224 fichiers au total : 223 HTML (dont `404.html`) et `sitemap.xml` ;
  - toutes les URL absolues sont précédées d'un guillemet, sauf les deux `<loc>` du sitemap ; aucun guillemet simple, aucun `index.html` explicite ;
  - variantes implicites (elles se résolvent vers un accueil sans être l'une des six formes exactes) : `href=".././"` et `href=".././#jeux"` dans le fil d'Ariane des 14 pages `jeux/*.html` (28 liens, normalisés en `../` par un commit préalable, §12) et `href="/./"` dans `404.html` ; aucune autre (constaté par une résolution de chaque `href` sur tout l'arbre).
- **Cloudflare :** le Worker protège tout le site (authentification de base, noindex) sauf une liste de pages et de fichiers publics. `/` et `/fr` seront protégés comme le reste ; le Worker n'a pas à changer.
- **`matchs.py` :** `HOME` (ligne 70) est défini et jamais lu. `URL = "https://esportly.eu/"` est une base d'adresses (images d'aperçu, widgets, repli des données structurées), pas un lien d'accueil.
- **`bascule_appstore.py` :** parcourt tous les `*.html` et remplace du texte ; aucun nom de fichier d'accueil dans le code.
- **Outils :** Python 3.13 est installé (`C:\Users\horny\AppData\Local\Programs\Python\Python313\python.exe`, ou `py`). `python3` sur le PATH n'est que le raccourci du Microsoft Store.

## 5. Carte des URL

| URL | Avant | Après |
|---|---|---|
| `/` (`index.html`) | accueil français | **accueil anglais** : contenu de l'actuel `en.html`, `lang="en"`, canonical `https://esportly.eu/` |
| `/fr.html` (nouveau) | n'existe pas | **accueil français** : contenu de l'actuel `index.html`, `lang="fr"`, canonical `https://esportly.eu/fr.html` |
| `/en.html` | accueil anglais | **page de renvoi** vers `/` (section 7), absente du sitemap |
| `/es.html`, `/de.html`, `/pt.html` | accueils | inchangés (leurs liens vers le français et l'anglais sont corrigés) |
| Toutes les autres pages | | **URL inchangées** |

Jeu hreflang des 5 accueils et du sitemap : fr → `/fr.html`, en → `/`, es, de et pt-BR inchangés, `x-default` → `/`.

## 6. L'échange des deux cibles d'accueil

**Règle centrale : chaque lien garde la destination qu'il avait.** Un lien vers l'accueil français mène toujours au français, un lien vers l'accueil anglais mène toujours à l'anglais. C'est un échange de deux cibles, appliqué en une seule substitution simultanée (jamais en deux passes).

Forme relative : la valeur **entière** d'un attribut `href="…"` (guillemets doubles), éventuellement suivie d'une ancre `#…` qui est conservée.

| Cible avant | Cible après |
|---|---|
| `./` | `fr.html` |
| `../` | `../fr.html` |
| `/` | `/fr.html` |
| `en.html` | `./` |
| `../en.html` | `../` |
| `/en.html` | `/` |

Forme absolue : `https://esportly.eu/` et `https://esportly.eu/en.html`, lorsqu'elles sont précédées d'un guillemet ou de `<loc>` **et** suivies d'un guillemet, d'un `<` ou d'un `#` (valeurs d'`href`, fil d'Ariane des données structurées, `<loc>` du sitemap). Une mention de l'adresse dans un texte courant n'est donc jamais touchée.

| Cible avant | Cible après |
|---|---|
| `https://esportly.eu/` | `https://esportly.eu/fr.html` |
| `https://esportly.eu/en.html` | `https://esportly.eu/` |

Précisions :

- Seule la valeur entière de l'attribut compte : `neuigkeiten.html` (qui se termine par `en.html`), `../equipes/x.html` ou `https://esportly.eu/equipes/x.html` ne sont jamais touchés.
- Fichiers concernés : tous les `*.html` et `sitemap.xml` (ainsi que les autres `*.xml` de la racine s'ils contiennent ces cibles), hors `.git`. `404.html` est une **exception** : il est réécrit à la main (section 8).
- **Échange inverse**, utilisé pour le test d'exactitude : `fr.html → ./`, `../fr.html → ../`, `/fr.html → /`, `./ → en.html`, `../ → ../en.html`, `/ → /en.html`, avec les mêmes correspondances en absolu. Appliqué à l'arbre migré, il doit redonner l'original (section 11), à une exception près : la propriété JSON-LD `"url"` d'un accueil désigne sa propre adresse ; après l'échange, le script la remet donc au canonical de la page (l'accueil anglais garde `https://esportly.eu/`, le français prend `https://esportly.eu/fr.html` ; es, de et pt portent déjà leur adresse).

## 7. Déplacement des fichiers et page de renvoi

Ordre des opérations : 1) l'échange est calculé en mémoire sur tous les fichiers concernés, y compris `index.html` et `en.html` ; 2) les fichiers sont écrits ; 3) `index.html` est renommé en `fr.html`, puis `en.html` en `index.html` (renommage sur le disque, sans appeler git : les commits sont faits à part) ; 4) le nouveau `en.html` est créé.

Le nouveau `en.html` est une page minimale :

- `lang="en"`, titre `eSportly`, politique de sécurité de contenu sans script ;
- `<link rel="canonical" href="https://esportly.eu/">` ;
- renvoi immédiat : `<meta http-equiv="refresh" content="0; url=./">` ;
- un lien visible « eSportly » vers `./` pour qui n'est pas renvoyé ;
- ni hreflang, ni `noindex` (le canonical suffit ; un noindex le contredirait), et aucune entrée dans le sitemap.

Ce renvoi ne vaut que pour l'ancienne adresse `en.html`, pour que les anciens liens et favoris continuent à marcher. Ce n'est pas une redirection selon la langue du visiteur.

## 8. Retouches hors échange

| Fichier | Changement |
|---|---|
| `404.html` | Passe en anglais d'abord, avec une phrase française : `lang="en"`, « Page not found », bouton « Back to home » vers `/`, bouton secondaire « Retour à l'accueil » (`lang="fr"`) vers `/fr.html`, raccourcis (`/#jeux`, `/teams.html`, « Join the beta », `/press.html`) et pied de page repris de l'accueil anglais. Ses 4 liens d'accueil (`/`, `/en.html`, `/#jeux`, `/./`) sont réécrits dans la foulée. |
| `manifest.webmanifest` | `lang` → `en`, `description` → « Your esports team, every match, right on time. » |
| `sitemap.xml` | En plus de l'échange : `lastmod` des 5 accueils = date d'exécution du script (format `AAAA-MM-JJ`, comme les entrées existantes) ; aucune entrée `/en.html` ; `/` et `/fr.html` présentes. Les autres entrées gardent leur `lastmod`. |
| `README.md` | Une phrase : `index.html` = accueil anglais, `fr.html` = accueil français, `en.html` = renvoi vers `/`. |
| `.github/scripts/matchs.py` | `HOME` réaligné (`"fr": "fr.html"`, `"en": "./"`) pour ne pas induire en erreur ; `URL` inchangée. |

## 9. Le script de migration

- Emplacement : `.github/scripts/anglais_par_defaut.py`, bibliothèque standard seulement, commentaires en français, même style que `bascule_appstore.py` (docstring avec usage, option `--essai`). Il est jetable : à supprimer après la fusion, comme `bascule_appstore.py` après la sortie.
- Usage : `python .github/scripts/anglais_par_defaut.py --essai` (dit ce qui changerait, n'écrit rien) puis sans option.
- **Tout ou rien :** tous les nouveaux contenus sont calculés en mémoire et contrôlés avant la moindre écriture.
- **Garde-fous :**
  - refuse de tourner si `fr.html` existe déjà ou si `index.html` est déjà en `lang="en"` (pas de double échange) ;
  - refuse si l'état de départ n'est pas celui attendu (`index.html` en `lang="fr"`, `en.html` en `lang="en"`) ;
  - s'arrête en listant tout lien d'accueil de forme inconnue : tout `href` qui se résout (chemin normalisé) vers un accueil (`/`, `index.html`, `en.html`, `fr.html`) sans être l'une des six formes exactes de la profondeur du fichier (donc `.././`, `./en.html`, `.`, `..`, les formes avec `?`, les guillemets simples, `../../`), ou une URL d'accueil précédée ou suivie d'un contexte non prévu (section 6). Un lien vers `fr.html` est toujours inconnu : il ne peut pas exister avant la migration, sa présence signale une migration à moitié faite. La seule variante connue restante (`/./`) est dans `404.html`, exclu explicitement.
- **Contrôles internes avant écriture :** plus aucune cible non échangée ; canonical de `index.html` = `https://esportly.eu/` et de `fr.html` = `https://esportly.eu/fr.html` ; les 5 accueils portent le même jeu hreflang (fr, en, es, de, pt-BR, `x-default`) et chacun se référence lui-même par son canonical ; le sitemap ne contient aucune entrée `/en.html` ; le `"url"` des données structurées de chaque accueil égale son canonical.
- Sortie : `N fichier(s) à changer` (ou `changé(s)`), comme `bascule_appstore.py`.

**Rejouer.** Si `origin/main` avance avant la fusion (robot du matin, modifications de l'équipe) : recréer la branche depuis `origin/main` à jour, relancer le script, puis reprendre le commit des retouches (section 12). Les conflits ne peuvent venir que de ces quatre fichiers de retouche.

## 10. Générateur et bascule App Store

**`matchs.py` / `matchs.yml` : aucun changement de logique.**
- Les pages « matchs de la semaine » et « grands événements » sont fabriquées à partir des 5 pages « Nouveautés » (`nouveautes.html`, `whats-new.html`, `novedades.html`, `neuigkeiten.html`, `novidades.html`). Ces modèles sont dans le périmètre de l'échange : le passage de 6 h 15 reproduit les bons liens.
- Le script ne touche jamais aux accueils. Le `git add -A` du workflow embarque `fr.html` sans rien changer.

**`bascule_appstore.py` / `bascule.yml` : aucun changement.**
- Il parcourt tous les `*.html` : `fr.html` est traité automatiquement, et la page de renvoi `en.html` n'a rien à remplacer.
- Il tourne chaque heure jusqu'à la sortie annoncée le 2 novembre, puis se désactive. Les deux workflows partagent le groupe de concurrence `matchs`.
- **Calendrier :** ne pas fusionner le 2 novembre, pour ne pas faire deux réécritures massives des accueils le même jour. Avant ou après la bascule convient, grâce au script rejouable. La date se décide avec le propriétaire.

## 11. Vérification (avant livraison)

| # | Contrôle | Critère de réussite |
|---|---|---|
| 1 | **Exactitude :** appliquer l'échange inverse à l'arbre migré | Redonne l'original, fichier par fichier, sauf `404.html`, `manifest.webmanifest`, `README.md`, `matchs.py`, le nouveau `en.html` les `lastmod` des accueils et le `"url"` JSON-LD de l'accueil anglais. `fr.html` inversé = ancien `index.html`, `index.html` inversé = ancien `en.html`. |
| 2 | **Liens internes :** résolution de chaque `href` et `src` relatif | Aucun lien cassé de plus qu'avant (comparaison avant / après) |
| 3 | **hreflang :** sur les 5 accueils et les sous-pages | Auto-référence, liens retour réciproques, chaque URL = canonical de sa cible, `x-default` → `/` pour les accueils |
| 4 | **Sitemap** | XML valide, chaque `<loc>` = canonical de sa page, `/` et `/fr.html` présents, aucune entrée `/en.html`, aucun fichier inexistant |
| 5 | **Accueils** | `/` : `lang="en"`, canonical `/` ; `fr.html` : `lang="fr"`, canonical `/fr.html` ; `en.html` : canonical `/`, renvoi vers `./` |
| 6 | **Garde-fous du script** | Double exécution refusée ; variante de lien inconnue → arrêt avec la liste |
| 7 | **Exécutions jumelles** de `matchs.py` et de `bascule_appstore.py --essai` sur une copie avant et une copie après (mêmes instants) | Résultats identiques aux liens d'accueil près ; même nombre de fichiers « à changer » pour la bascule |
| 8 | **Rendu local :** serveur statique, accueils et menu de langue, mobile et ordinateur | `/` anglais, `/fr.html` français, le menu de langue passe de l'un à l'autre, la 404 est correcte |
| 9 | **Langue des liens d'accueil :** tout lien (hors sélecteur de langue `hreflang`) qui mène à un accueil, et tout `item` ou `url` JSON-LD d'accueil | Mène à l'accueil de la langue de la page (`fr` → `fr.html`, `en` → `/`) |

`matchs.py` utilise `zoneinfo` : sous Windows, il peut demander le paquet `tzdata`, installé alors dans un environnement virtuel jetable (hors du dépôt et du système).

**Non vérifiable ici :** le rendu réel sur `esportly.eu` (accès protégé, aucun identifiant ni accès Cloudflare côté Claude). Après déploiement, ouvrir `/`, `/fr` et `/en`.

## 12. Livraison

Cinq commits sur `anglais-par-defaut`, créée depuis `origin/main` avec `--no-track` (dans l'ordre : 1, 2, 3, 4, 5) :

1. La spec (`docs/`) et la ligne `docs` ajoutée à `.assetsignore` (sinon Cloudflare servirait le dossier comme pages du site).
2. Normalisation préalable : `href=".././"` et `href=".././#jeux"` deviennent `href="../"` et `href="../#jeux"` dans les 14 pages `jeux/*.html` (même destination, forme standard que l'échange sait traiter).
3. Le script `.github/scripts/anglais_par_defaut.py` et ses tests.
4. Le résultat mécanique de son exécution (échange, déplacements, nouveau `en.html`, sitemap).
5. Les retouches : `404.html`, `manifest.webmanifest`, `README.md`, `matchs.py` (`HOME`).

Rien n'est poussé ni fusionné sans l'accord de l'utilisateur. Si le compte GitHub de ce PC peut pousser une branche (pas `main`), une pull request est ouverte ; sinon la branche locale est remise au propriétaire.

## 13. Risques et points ouverts

| Risque ou point | Traitement |
|---|---|
| **Cloudflare redirige `/x.html` vers `/x`** (307, constaté sur `/privacy.html`), alors que canonical, hreflang et sitemap utilisent `.html`. Google n'accepte pas d'URL hreflang qui redirigent. | Hors de ce chantier, sans effet tant que le site est protégé et en noindex. **À traiter avant l'ouverture publique.** Ne pas désactiver la suppression de `.html` côté Cloudflare : l'app s'appuie sur des adresses sans extension comme `/match`. |
| **Source des pages.** Le README dit que les pages sont rédigées dans le dépôt de l'app (dossier `Site/`) puis copiées ici ; les derniers commits ressemblent à des modifications faites directement ici. | À confirmer avec le propriétaire. Si la source est ailleurs, le changement doit y être reporté, sinon la prochaine copie l'écrasera. |
| **Le français perd son URL d'accueil historique.** `/fr.html` n'a pas d'historique. | Accepté : site jeune et protégé. Les pages françaises (équipes, jeux, presse…) gardent leurs URL. |
| **Public français et anglais.** L'anglais est un public plus grand mais très concurrentiel ; le français est plus petit mais plus facile à gagner (Karmine Corp, Vitality). | Aucune mesure faite. Garder les pages françaises indexées et bien liées ; mesurer après l'ouverture publique. |
| **Liens externes et app** qui pointaient vers `/` afficheront l'anglais. | Voulu. Les liens vers `en.html` continuent de marcher grâce au renvoi. |
| **Conflit avec le robot du matin ou la bascule** pendant que la branche attend. | Script rejouable (section 9). |
| **Libellé de la bêta dans la 404 anglaise** (« Join the beta ») : après la bascule App Store, ce libellé peut rester. | Même comportement qu'aujourd'hui avec « Rejoindre la bêta » : il apparaît dans le rapport « reste » de la bascule, à relire à la main. |
