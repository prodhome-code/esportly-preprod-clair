/* Détection de langue, chargé par langue_partout.py dans le <head> de chaque page.
   - Sur l'accueil anglais (/), redirige vers la langue du navigateur (fr/es/de/pt), sauf si un
     choix manuel a déjà été retenu (cookie « lang »).
   - Retient le choix fait en cliquant sur une langue du sélecteur. */
(function () {
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[hreflang]') : null;
    if (!a) return;
    var code = (a.getAttribute('hreflang') || '').slice(0, 2).toLowerCase();
    if (code) document.cookie = 'lang=' + code + '; path=/; max-age=31536000; SameSite=Lax';
  });

  if (/(?:^|;\s*)lang=/.test(document.cookie)) return;
  var path = location.pathname.replace(/\/index\.html$/, '/');
  if (path !== '/' && path !== '') return;
  var lang = (navigator.language || 'en').slice(0, 2).toLowerCase();
  var target = { fr: '/fr.html', es: '/es.html', de: '/de.html', pt: '/pt.html' }[lang];
  if (target) location.replace(target);
})();
