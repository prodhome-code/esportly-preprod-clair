# Sources de la veille : liste fermée, preuves, ce qui reste partiel

Mis à jour le 08/11/2026. Chaque entrée de `blog-src/veille/sources.json` a été vérifiée par des commandes réelles le
même jour (`veille.py collect`) : code HTTP, type de contenu, nombre d'éléments lus, et `robots.txt` pour notre agent
`esportly-veille/1.0 (+https://esportly.eu)`. **20 sources, 0 en panne, 228 éléments vus** au dernier passage.

## Les 14 jeux sont couverts

| Jeu | Source(s) | Type | Vérification du 08/11/2026 |
|---|---|---|---|
| League of Legends | LoL Esports (Riot), League of Legends — actualités (Riot) | pages | 200, robots OK |
| Counter-Strike 2 | ESL (RSS), BLAST, HLTV *(média)*, Counter-Strike 2 — mises à jour Valve sur Steam (RSS) | flux + pages | 200, robots OK |
| Valorant | VALORANT Esports (Riot), VALORANT — actualités (Riot) | pages | 200, robots OK |
| Rocket League | Rocket League — annonces Psyonix sur Steam (RSS) | flux | 200, 10 éléments, robots OK |
| Dota 2 | Dota 2 — annonces Valve sur Steam (RSS) | flux | 200, 10 éléments, robots OK |
| Overwatch 2 | Overwatch 2 — actualités (Blizzard) | page | 200, 12 articles lus, robots OK |
| Rainbow Six Siege | Rainbow Six Siege Esports (Ubisoft) | page | 200, robots OK |
| Call of Duty | Call of Duty — annonces Activision sur Steam (RSS) | flux | 200, 8 éléments, robots OK |
| Mobile Legends: Bang Bang | MPL Indonesia (Moonton) | page | 200, robots OK — **en indonésien** |
| Honor of Kings | Honor of Kings (Level Infinite) | page | 200, robots OK — page d'accueil, pas de rubrique dédiée |
| EA SPORTS FC | EA SPORTS FC Pro, EA — actualités | pages | 200, robots OK |
| StarCraft II | StarCraft II — actualités (Blizzard) | page | 200, 4 articles lus, robots OK |
| StarCraft: Brood War | la même page (Brood War y figure) | page | idem |
| Wild Rift | Wild Rift — actualités (Riot) | page | 200, robots OK |
| Tous les jeux Riot | Riot Games — actualités | page | 200, robots OK |

## Les flux Steam, pourquoi c'est officiel

`store.steampowered.com/feeds/news/app/<appid>` publie les annonces **écrites par l'éditeur** (Valve pour Dota 2 et
Counter-Strike 2, Psyonix pour Rocket League, Activision pour Call of Duty) : notes de patch, saisons, annonces
d'événement. Ce n'est pas un média. C'est ce qui a permis de couvrir Dota 2, Rocket League et Call of Duty, dont les
sites officiels sont soit fermés à notre agent, soit affichés par JavaScript. Le flux de l'API Steam
(`api.steampowered.com`) reste interdit par son `robots.txt` : on ne l'utilise pas.

## Ce qui reste partiel (et pourquoi)

- **Esport Rocket League (RLCS)** : `rocketleague.com` répond **403** à notre agent (protection anti-robot) alors que son
  `robots.txt` l'autorise. Le flux Steam couvre le jeu (patchs, saisons), pas le circuit RLCS. Piste : autoriser
  `epicgames.com`, ou une page RLCS statique.
- **Esport Call of Duty (CDL)** : `callofdutyleague.com` ne répond pas à notre agent (délai dépassé), `robots.txt`
  illisible. Le flux Steam couvre le jeu, pas la ligue.
- **Esport StarCraft II** : `news.blizzard.com` n'a pas de `robots.txt` (404, donc rien n'est interdit) et sa page
  StarCraft II est lisible ; il n'y a pas de flux RSS, la lecture passe par les liens de la page.
- **Mobile Legends** : la seule source lisible est indonésienne (MPL Indonesia). Un fait qui n'existe qu'en indonésien
  doit être traduit et sa preuve recopiée, ou écarté.
- **Sources écartées** : `liquipedia.net`, `sheepesports.com`, `dust2.us` (403 / robots.txt refusé),
  `esportsinsider.com` (robots.txt refuse), `blog.counter-strike.net` (403), `news.blizzard.com` comme source directe
  (pas de RSS). HLTV est dans la liste mais marqué média : il repère, il ne prouve pas.
- **Jeux hors des 14** (Apex/ALGS…) : hors périmètre, l'article ALGS existant a été écrit à la main.

## Règles de la liste

- Une entrée = un domaine + la preuve de sa lecture (colonne « Vérification »). Pas de preuve, pas d'entrée.
- La liste ne se modifie que par une pull request de l'utilisateur : la routine peut **proposer** une source dans le
  corps de sa pull request, jamais l'ajouter.
- Une source marquée « média » (HLTV) sert à **repérer** un sujet ; elle ne peut jamais être la preuve d'un fait. Le
  tableau d'affirmations exige une source officielle (éditeur, ligue, organisateur).
- Une source qui ne répond plus est sautée et notée dans `veille/candidates.json` (`en_panne`) : la journée continue.
- Une redirection qui sort de la liste blanche est refusée ; `also` déclare un second domaine de la même organisation
  (par exemple `news.blizzard.com` pour Blizzard).
- Trois éléments par source au plus dans les candidats, pour qu'une source bavarde ne mange pas les 15 places.
