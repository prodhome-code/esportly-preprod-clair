# Onglet Live : ordre par état et fin des matchs notée

Demande du 1er novembre 2026 : « un bot ou un agent qui arrive sur la page Live ; quand un live se finit, il faut le noter. Quand le
live se finit, mettre ce match en bas et indiquer qu'il est fini ; ce qui est en direct doit être tout en haut. »
Suite de `2026-10-31-live-design.md` (état calculé par l'horloge, pas de code serveur).

## Décisions

1. **Ordre** : en direct tout en haut, puis les matchs à venir (groupés par jour comme avant), puis les terminés tout en bas
   (le plus récent d'abord), sous le titre « Matchs terminés » (5 langues). C'est le script de la page qui range les `<li>` d'après
   l'horloge du visiteur (l'état change sans que la page soit refabriquée) ; sans JavaScript la page reste la liste chronologique
   du jour. Les titres vides sont cachés.
2. **Libellé** : « Terminé / Finished / Terminado / Beendet / Encerrada » (déjà dans `LABELS`) sur chaque match fini, plus le titre de
   section ; carte atténuée comme avant.
3. **La fin est « notée » par un robot, sans rien inventer.** Seule source : le flux de résultats du relais eSportly
   (`/calendrier/resultats/semaine.json`, le même que celui des pages « matchs de la semaine » et des grands événements : un
   `id` de match, les deux équipes et le `score` ; sa `date` est le coup d'envoi du match, pas sa fin : vérifié sur le match 1713105,
   `date` = `DTSTART` du calendrier). La présence d'un score dit « fini » ; l'heure de fin exacte est inconnue, le robot note seulement
   l'heure à laquelle il l'a constaté (`vu`). Rien n'est déduit de l'horloge ni d'un site tiers (hltv.org
   reste un simple repère, jamais cité). Un résultat n'est retenu que si son `id` est celui d'un match de la page, que ce match a déjà commencé
   (coup d'envoi ≤ maintenant) et que le résultat nomme deux équipes.
4. **Ce que la fin change** : le match garde `data-final` (heure du constat) ; le script le met en « terminé » même si l'horloge le croit encore
   en direct (match plus court que prévu). Sa page (`<langue>/live/<id>.html`) montre le score **caché derrière un bouton** (« Voir le
   score »), comme partout sur le site : pas de spoiler. La liste Live ne montre que « Terminé ».
5. **Cadence** : un workflow GitHub Actions `live.yml`, toutes les heures (à :40, le relais rafraîchit ses calendriers chaque heure), qui
   ne fait presque rien quand il n'y a rien de nouveau (une requête, aucune écriture). Le dépôt est privé : une heure plutôt que
   30 minutes pour rester dans les minutes gratuites (la cadence est une ligne du workflow).
6. **Données** : `suivi/live.json` (hors site, `.assetsignore`) garde les matchs du jour fabriqués le matin (`matchs`) et les fins
   notées (`fins`, `{id: {vu, score, equipes}}`). Le robot du matin (`matchs.py`) l'écrit ; le robot de l'heure (`matchs.py --live`)
   le complète et refabrique les 5 pages Live et les pages de match, puis le workflow rejoue les mêmes retouches que `matchs.yml`
   (menu, titres, analytics, QR) et propose la mise à jour par un commit sur `main` (même mécanique que « Matchs du jour »).

## Code

- `live.py` : `LABELS[..]["h_done"]`, `note` mise à jour ; `render_main(..., finals=None)` : `li` avec `data-final`, sections
  `En direct` (`#l-live`) et `Matchs terminés` (`#l-done`) cachées au départ, `data-grp` sur les listes ; `JS` : état forcé à
  « done » si `data-final`, rangement, titres vides cachés ; `STYLE` : `.matchs[hidden]{display:none}`.
- `live_match.py` : `render_page(..., final=None)` : bloc « Résultat » (`<details>`), phrase du score ajustée ; `build(..., finals=None)`.
- `live_suivi.py` (nouveau, testé) : lecture et écriture de `suivi/live.json`, `new_finals(matchs, results, now)` (règles du point 3).
- `matchs.py` : `--live` saute les sections 1 à 3 (équipes, semaine, événements), relit `suivi/live.json` au lieu des calendriers,
  note les fins et ne refabrique rien s'il n'y en a pas de nouvelle ; en mode normal il écrit `suivi/live.json`.
- `.github/workflows/live.yml`, `.assetsignore`, README.

## Hors périmètre

- Un match qui dépasse l'horaire prévu reste « terminé » par l'horloge après `fin + 30 min` tant que le flux n'a pas de résultat :
  le flux ne dit pas « en cours », on ne l'invente pas.
- Score sur la liste Live, vrai flux en direct (côté app, autre dépôt).
