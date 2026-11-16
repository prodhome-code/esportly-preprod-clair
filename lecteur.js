/* Direct sur les pages de match : une vignette remplace le lecteur tant qu'on n'a pas cliqué.
   Avant le coup d'envoi, YouTube n'a rien à lire (ni « erreur 153 », ni vidéo qui n'a rien à voir) : la vignette
   n'est alors qu'une annonce — pas de bouton lecture, pas de lien, seulement l'heure du coup d'envoi. Dès que le
   match a commencé, le clic pose le lecteur de la chaîne dans la page (avec referrer : sans lui YouTube refuse).
   Rien ne se charge pour rien : aucun iframe avant le clic. */
(function () {
  var vignettes = document.querySelectorAll(".wposter");
  for (var i = 0; i < vignettes.length; i++) {
    (function (vignette) {
      var note = vignette.querySelector(".wnote");
      var debut = vignette.getAttribute("data-start");
      var quand = debut ? new Date(debut) : null;
      var connu = !!quand && !isNaN(quand.getTime());
      var commence = connu && Date.now() >= quand.getTime();

      if (!commence) {
        // Rien à lire : la vignette annonce le direct, elle ne promet pas de vidéo.
        vignette.classList.add("attente");
        vignette.removeAttribute("data-page");
        if (note) {
          var heure = connu
            ? quand.toLocaleTimeString(document.documentElement.lang || "fr", { hour: "2-digit", minute: "2-digit" })
            : "";
          note.textContent = (heure ? heure + " · " : "") + vignette.getAttribute("data-note-wait");
        }
        return; // pas d'écouteur : impossible d'ouvrir une vidéo sans rapport
      }

      if (note) note.textContent = vignette.getAttribute("data-note-live");
      vignette.addEventListener("click", function () {
        var cadre = document.createElement("iframe");
        cadre.src = vignette.getAttribute("data-embed");
        cadre.title = vignette.getAttribute("data-title") || "";
        cadre.setAttribute("allow", "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture");
        cadre.setAttribute("allowfullscreen", "");
        // YouTube a besoin de savoir d'où vient l'intégration : « no-referrer » provoque l'erreur 153.
        cadre.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
        vignette.parentNode.replaceChild(cadre, vignette);
      });
    })(vignettes[i]);
  }
})();
