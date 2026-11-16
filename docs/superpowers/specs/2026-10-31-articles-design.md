# Articles News et Blog : page dédiée, sommaire latéral, images

Date : 31/10/2026. Demande de l'utilisateur : cliquer sur une news ou un article de Blog ouvre une page d'article avec, à droite, une barre latérale qui montre le plan (sommaire) ; l'article est généré d'après des sources ; présentation simple avec des images qui donnent envie. Images : IA fidèle à la charte du site et de l'app, et images officielles avec leur source citée.

## Comprise

- **Blog** : les fiches de jeu et les guides existent déjà (4 sections, sources numérotées). On ajoute le sommaire latéral et une grande image de couverture. Rien d'autre ne change dans leur contenu.
- **News** : aujourd'hui une news est une carte de 280 caractères. Chaque news peut recevoir un `article` (sections, sources, image) dans `news/news.json`. Elle devient alors une page `/<dossier>/<id>` ; la carte de la liste y mène. Sans `article`, la carte reste comme avant.
- 5 langues, menus, filtre par jeu et pied de page inchangés. Aucune ressource externe (CSP stricte), sommaire en HTML/CSS pur, sans JavaScript.

## Conception

1. **Une seule mise en page d'article** (`site_chrome.article_layout`) pour le Blog et les News : fil d'Ariane, couverture, titre, chapô, deux colonnes sur ordinateur (texte à gauche, sommaire collant à droite ; sur téléphone le sommaire passe en repliable au-dessus du texte), sources numérotées à la fin.
2. **Sommaire** : généré à partir des intertitres des sections (`<h2 id="s1">`…) plus « Top plays » et « Sources » quand ils existent. Liens d'ancre, `aria-label` « Sommaire / Contents… ».
3. **News avec article** : `article = {"image": {...}, "sources": [{id,title,url}], "sections": [{"cite": [ids], "fr": {"heading","text":[…]}, …}]}` ; mêmes règles de vérification que les fiches du Blog (3 sources au moins dont une officielle, chaque section cite au moins une source). Le script de génération du Blog les rend dans le modèle de la page du jeu (à défaut celui de League of Legends) ; dossiers `NEWS_DIRS` : `news-item` (en), `actu` (fr), `noticia` (es), `meldung` (de), `artigo` (pt-BR). Le sitemap, les données structurées `NewsArticle` et les hreflang suivent.
4. **Images** : `img/couvertures/<id>.webp` (1600×900, au plus 200 Ko). Deux origines, déclarées dans la donnée : `{"kind":"ia","src"}` (générée d'après la charte : fond nuit, accents, formes de l'app, sans logo ni visage réel) ou `{"kind":"officielle","src","credit","source_url"}` (affichée avec « Image : <crédit> · source »). Une image officielle n'est ajoutée que si la licence ou le kit de presse de l'éditeur l'autorise ; sinon on garde l'image IA et on cite la source en lien. Texte alternatif décrivant la scène, légende « Illustration générée par IA » pour les images IA.
5. **Tests** : sommaire (ancres uniques, ordre), page d'article de News (5 langues, menu, sources, image, canonique/hreflang, sitemap), validation des données, rejouabilité, liste → article, absence d'article → carte inchangée.

## Hors périmètre

Pages d'équipe et de jeu, accueil. Pas de commentaires, pas de recherche.
