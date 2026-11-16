# Veille : des articles écrits chaque jour, publiés après contrôle

Cette partie ajoute au dépôt l'**agent de veille** décrit dans
[`docs/superpowers/specs/2026-10-27-veille-design.md`](../superpowers/specs/2026-10-27-veille-design.md) : une routine
quotidienne cherche des nouveautés sur une **liste fermée de sources officielles**, fait écrire jusqu'à **3 articles
originaux** en 5 langues (rien les jours sans actualité), puis propose le résultat par une pull request. Un contrôle
écrit dans le dépôt accepte ou refuse ; l'utilisateur fusionne pendant les 2 premières semaines, ensuite les pull
requests conformes se fusionnent seules.

Le principe : **les agents écrivent, le code décide.** Aucun agent ne touche à la liste des sources, au contrôle, ni à
un réglage : seule la routine peut commiter, et seulement du contenu (pages, tableaux d'affirmations, `seen.json`).

## Fichiers

| Fichier | Rôle | Modifiable par |
|---|---|---|
| `blog-src/veille/sources.json` | la liste fermée des sources, avec la preuve de chaque flux | l'utilisateur, par pull request |
| `blog-src/veille/seen.json` | adresses et clés de sujet déjà vues (anti-doublon) | la routine (une ligne par jour) |
| `blog-src/veille/mode.json` | `{"auto_from": "AAAA-MM-JJ"}` : début de la fusion automatique ; `null` = essai | l'utilisateur |
| `blog-src/veille/STOP` | interrupteur : sa présence arrête la veille et bloque toute fusion | l'utilisateur |
| `.github/scripts/veille.py` | collecte, outil de lecture, contrôle | personne (code) |
| `.github/scripts/test_veille.py` | tests (aucun réseau) | personne (code) |
| `.github/workflows/veille-gate.yml` | contrôle de chaque pull request `veille/…` | personne (code) |
| `.github/workflows/veille-publier.yml` | régénère les pages après fusion, et fusionne les pull requests conformes après l'essai | personne (code) |
| `docs/veille/routine.md` | le texte de la routine planifiée | l'utilisateur |
| `docs/veille/agents/*.md` | consignes des 5 sous-agents | l'utilisateur |
| `docs/veille/sources.md` | preuves des sources, jeux non couverts | l'utilisateur |

`veille/candidates.json` (à la racine) est éphémère et **jamais commité** : c'est le brouillon du jour, lu par les
sous-agents.

## Commandes

```bash
python3 .github/scripts/veille.py --verifier     # valide blog-src/veille/*.json (aucun réseau)
python3 .github/scripts/veille.py collect        # lit les sources, écrit veille/candidates.json (≤ 15 éléments)
python3 .github/scripts/veille.py fetch <url>    # lit une page de la liste blanche (outil des chercheurs, 40 lectures/jour)
python3 .github/scripts/veille.py gate           # contrôle une pull request (lit git diff origin/main...HEAD)
python3 .github/scripts/veille.py gate --fichiers a b --jour 2026-11-22   # même contrôle, fichiers et jour imposés
python3 .github/scripts/veille.py seen <url>…    # note des adresses comme vues
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -p "test_veille.py" -v
```

## Une journée de veille

1. La routine lance `collect` : 0 à 15 candidats, chacun marqué `untrusted`, avec le texte de sa page (20 000 caractères au plus).
2. L'**éclaireur** retient au plus 5 sujets (ou aucun : journée vide).
3. Le **chercheur** lit les pages sources de son sujet avec `veille.py fetch` et rend un dossier de faits, chacun avec une adresse et un extrait de 12 mots au plus.
4. Le **rédacteur** écrit l'article en anglais à partir du seul dossier, plus les lignes du tableau d'affirmations.
5. Le **vérificateur** relit l'article contre les pages sources, phrase par phrase.
6. Le **traducteur** écrit fr, es, de, pt-BR et compare les nombres et les noms.
7. La routine écrit `blog-src/pages/<id>.json`, `blog-src/claims/<id>.md`, une ligne dans `seen.json`, pousse la branche `veille/AAAA-MM-JJ` et ouvre une pull request étiquetée `veille`.
8. `veille-gate.yml` contrôle, commente, et refuse ou accepte.
9. L'utilisateur fusionne (essai), ou `veille-publier.yml` fusionne tout seul après `auto_from`.
10. Après fusion, les pages sont régénérées (`blog.py`) et Cloudflare déploie.

## Arrêter, repartir

- **Arrêter** : créer le fichier `blog-src/veille/STOP` (même vide) et le pousser sur `main`. Le contrôle refuse, la routine s'arrête, aucune fusion automatique.
- **Repartir** : supprimer `STOP`.
- **Revenir en arrière** : `git revert` de la fusion concernée, puis `blog.py` régénère les pages.
- **Passer en fusion automatique** : remplacer `null` par une date, 14 jours après le premier lancement (`mode.json`).

## Sécurité

- Les domaines de `sources.json` forment la **liste blanche** : `fetch` refuse toute adresse hors de ces domaines, y compris après redirection.
- `robots.txt` est vérifié avant chaque lecture ; un robots illisible vaut refus.
- Une seconde entre deux requêtes au même site, délai de 20 s, 2 000 000 d'octets au plus, aucune image, aucune connexion, aucune page payante.
- Le texte du web est une **donnée** : s'il contient des consignes, elles ne sont pas exécutées ; les sous-agents qui lisent n'ont aucun outil d'écriture.
- Aucune reproduction : l'article reformule, cite ses sources numérotées et lie chaque fait à son extrait. Le contrôle mesure la plus longue suite de mots identiques (6 au plus) et le recouvrement des suites de 5 mots (15 % au plus par source, 40 % avec une page existante).
