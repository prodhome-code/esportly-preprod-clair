/* Modal QR pour les badges App Store, sur ordinateur : cliquer sur un badge (l'image
   « Download on the App Store ») ouvre le QR à scanner avec l'iPhone, au lieu de quitter le
   site. Sur téléphone/tablette, le clic suit le lien direct. Chargé par qr_ordinateur.py.
   Le bandeau d'accueil (data-qr-title) ouvre la même modal avec son propre titre.
   Les <time> du bandeau passent en heure locale du visiteur (tous appareils). */
(function () {
  function localizeTimes() {
    var els = document.querySelectorAll('.bandeau time[datetime]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var d = new Date(el.getAttribute('datetime'));
      if (isNaN(d.getTime())) continue;
      var lang = document.documentElement.lang || 'fr';
      try {
        el.textContent = new Intl.DateTimeFormat(lang, {
          weekday: 'long', day: 'numeric', month: 'long',
          hour: '2-digit', minute: '2-digit'
        }).format(d);
      } catch (err) {}
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', localizeTimes);
  else localizeTimes();

  var fine = window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  if (!fine) return;

  var modal = null;
  var STORE = 'https://apps.apple.com/app/apple-store/id6819243569?pt=127103293&ct=site_esportly&mt=8';
  var DEFAULT_TITLE = 'Scanne avec ton iPhone';

  function build() {
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'qrmodal';
    modal.id = 'qr-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', "Télécharger eSportly sur l'App Store");
    modal.innerHTML =
      '<div class="qrmodal-card">' +
        '<button class="qrmodal-close" type="button" aria-label="Fermer">&times;</button>' +
        '<div class="qrmodal-brand"><img src="/embleme.svg" alt="" width="36" height="36"><span><i>e</i>Sportly</span></div>' +
        '<img class="qrmodal-qr" src="/qr-app-store.svg" width="200" height="200" alt="" aria-hidden="true">' +
        '<p class="qrmodal-title">' + DEFAULT_TITLE + '</p>' +
        '<p class="qrmodal-text">Ouvre l\'appareil photo et vise le code pour télécharger eSportly.</p>' +
        '<a class="qrmodal-btn" href="' + STORE + '">Ouvrir l\'App Store</a>' +
      '</div>';
    document.body.appendChild(modal);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    modal.querySelector('.qrmodal-close').addEventListener('click', close);
    return modal;
  }

  function open(title) {
    var m = build();
    var el = m.querySelector('.qrmodal-title');
    if (el) el.textContent = title || DEFAULT_TITLE;
    m.classList.add('open');
    document.documentElement.style.overflow = 'hidden';
  }

  function close() {
    if (modal) modal.classList.remove('open');
    document.documentElement.style.overflow = '';
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    var a = t && t.closest ? t.closest('a') : null;
    if (!a) return;
    if (a.hasAttribute('data-qr-title')) {
      e.preventDefault();
      open(a.getAttribute('data-qr-title'));
      return;
    }
    if ((a.getAttribute('href') || '').indexOf('apps.apple.com') === -1) return;
    if (!a.querySelector('img[src*="app-store"]') && !a.classList.contains('o2-cta')) return;
    e.preventDefault();
    open();
  });

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
})();
