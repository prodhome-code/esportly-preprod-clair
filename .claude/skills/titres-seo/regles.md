# Règles des titles et métadescriptions du site eSportly

Lues par le skill `titres-seo` à chaque génération, dans les 5 langues du site (fr, en, es, de, pt-BR). Modifie-les librement :
une règle par ligne. Le script `scripts/controle.py` vérifie celles qui se mesurent (longueurs, marque, mots répétés, interdits,
doublons, mots hors page).

## Title

- Longueur : 55 à 63 caractères, espaces compris.
- Pas de marque en fin de title (décision du 31/10/2026 : « évite de mettre eSportly à la fin ») : les 55 à 63 caractères vont aux
  mots-clés. La marque n'apparaît que sur les accueils (en tête, « eSportly · … ») ; ailleurs on l'évite ; si elle est vraiment
  nécessaire, elle est au milieu d'une suite de mots-clés, jamais en suffixe. La description peut la nommer une fois.
- Mot-clé principal en premier, mots-clés secondaires ensuite. Suite de mots-clés, pas de phrase, pas de verbe d'appel à l'action.
- Casse normale de la langue (majuscule au premier mot, aux noms propres, aux jeux et aux équipes). Pas de Title Case, même en anglais :
  les titles actuels du site sont en casse normale et Google les affiche tels quels.
- Aucun mot répété dans un même title (les mots vides de la langue ne comptent pas : de, du, the, of, del, der, do…).
- Séparateurs permis : « : » après le mot de tête (Esport Valorant : …), « , » entre termes parallèles, « & » ou « et », « ? » sur les
  pages guide. Jamais de tiret cadratin « — », ni de point d'exclamation, ni d'émoji.
- Libellé intouchable : le nom d'un jeu, d'une équipe, d'un événement ou le titre d'un article reste tel quel, mot pour mot
  (Counter-Strike 2, Karmine Corp, VCT Champions 2026). On ajoute les mots-clés autour, on ne réécrit pas le libellé.
- Seuls des mots présents sur la page (title et description actuels, texte, libellés) ou des mots-clés validés SEMrush avec du
  volume. Jamais de mots inventés ou génériques sans valeur.
- Singulier par défaut ; pluriel seulement si c'est le pluriel que SEMrush montre comme recherché (« matchs », « alertes », « équipes »).
- Pages quasi identiques (les 14 jeux, les 83 équipes) : varier l'angle plutôt que recopier la même formule partout — par exemple
  « alertes de match » sur une page, « score en direct » en tête sur une autre, « calendrier » sur une troisième, selon ce que
  SEMrush donne pour ce jeu ou cette équipe.
- Mots-clés à faible volume et faciles à ranker, de préférence à 3 mots plutôt qu'à 1 ou 2.

## Métadescription

- Longueur : 120 à 155 caractères. Une ou deux phrases complètes, qui finissent par un point.
- Le mot-clé principal dans les 60 premiers caractères, dit autrement que dans le title (pas la même suite de mots).
- Dit ce que la page contient vraiment (ce qu'on y lit ou ce que l'app fait pour cette page), avec une précision utile : le jour de
  mise à jour, les jeux couverts, « sans compte », « gratuit » si c'est vrai sur la page.
- Peut nommer eSportly une fois ; pas obligatoire.
- Tutoiement en français, espagnol et portugais, « du » en allemand, « you » en anglais : le ton des accueils.
- Pas de formule commerciale ni de style IA : pas d'accroche, pas de tiret cadratin, pas de point d'exclamation, pas de superlatif.

## Par langue

- Mot-clé principal déduit de l'URL et de la page, puis volumes et mots-clés liés dans SEMrush, **base de la langue** :
  fr → `fr`, en → `us` (volumes mondiaux les plus fiables ; `uk` en second si le mot-clé est typiquement britannique),
  es → `es`, de → `de`, pt-BR → `br`.
- On ne traduit pas un title d'une langue à l'autre : chaque langue a ses propres mots-clés (« esport » en français, « esports » en
  anglais, « E-Sport » en allemand, « esports » en espagnol et portugais, selon SEMrush).
- Graphie du mot-clé : celle que SEMrush montre comme recherchée (« e-sport » ou « esport »), même si le site écrit autrement.
- Accents et orthographe corrects dans chaque langue (ß, ñ, ã, œ…).

## Interdits

- fr : « Découvrez », « meilleur », « incontournable », « idéal », « officiel », « gratuitement » ; en : « discover », « best »,
  « ultimate », « official », « top », « amazing » ; es : « descubre », « mejor », « oficial », « increíble » ; de : « entdecke »,
  « beste », « offizielle », « ultimativ » ; pt-BR : « descubra », « melhor », « oficial », « incrível ».
- Partout : « — », « ! », émojis, « Site officiel », « Notre gamme », accroches publicitaires.

## Pages à laisser

- Pages légales et techniques (CGU, confidentialité, mentions légales, accessibilité, presse, nouveautés) : pas de travail SEO, on
  garde leur title ; seule la longueur de la description est contrôlée si on y touche.

## Exemples de référence (titles validés)

- `/` (en) → eSportly · Your esports team, every match, right on time (accueil : marque en tête, exception à la règle du suffixe)
- `/fr/blog/valorant` → Esport Valorant : le jeu et sa scène pro – eSportly (le style avant le skill : suffixe de marque, à ne plus faire)
