/* Mesure d'audience d'eSportly : Google Analytics 4, chargé seulement si le visiteur accepte.
   Sans accord, aucune requête vers Google et aucun cookie. Le choix est gardé 6 mois dans le navigateur (clé « esportly-consent »),
   un lien « Gérer les cookies » (pied de page, ou tout élément [data-consent-open]) permet de le changer à tout moment. */
(function () {
  'use strict';
  var ID = 'G-VXPQYVC83F', KEY = 'esportly-consent', DURATION = 182 * 864e5;
  var TEXTS = {
    en: { text: 'Can we measure which pages are read? eSportly uses Google Analytics (cookies, data sent to Google) only if you accept. The site works the same if you refuse.',
          yes: 'Accept', no: 'Refuse', more: 'Privacy', page: '/privacy.html', manage: 'Cookie settings', label: 'Audience measurement' },
    fr: { text: 'Peut-on mesurer les pages lues ? eSportly utilise Google Analytics (cookies, données envoyées à Google) seulement si tu acceptes. Le site fonctionne pareil si tu refuses.',
          yes: 'Accepter', no: 'Refuser', more: 'Confidentialité', page: '/fr/confidentialite.html', manage: 'Gérer les cookies', label: 'Mesure d’audience' },
    es: { text: '¿Podemos medir qué páginas se leen? eSportly solo usa Google Analytics (cookies, datos enviados a Google) si aceptas. El sitio funciona igual si rechazas.',
          yes: 'Aceptar', no: 'Rechazar', more: 'Privacidad', page: '/es/privacidad.html', manage: 'Gestionar cookies', label: 'Medición de audiencia' },
    de: { text: 'Dürfen wir messen, welche Seiten gelesen werden? eSportly nutzt Google Analytics (Cookies, Daten gehen an Google) nur, wenn du zustimmst. Die Seite funktioniert genauso, wenn du ablehnst.',
          yes: 'Akzeptieren', no: 'Ablehnen', more: 'Datenschutz', page: '/de/datenschutz.html', manage: 'Cookie-Einstellungen', label: 'Reichweitenmessung' },
    pt: { text: 'Podemos medir quais páginas são lidas? O eSportly só usa o Google Analytics (cookies, dados enviados ao Google) se você aceitar. O site funciona igual se você recusar.',
          yes: 'Aceitar', no: 'Recusar', more: 'Privacidade', page: '/pt/privacidade.html', manage: 'Gerenciar cookies', label: 'Medição de audiência' }
  };
  var code = ((document.documentElement.lang || 'en').toLowerCase().slice(0, 2));
  var T = TEXTS[code] || TEXTS.en;

  function read() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY));
      if (v && (v.c === 'granted' || v.c === 'denied') && Date.now() - v.t < DURATION) return v.c;
    } catch (e) {}
    return null;
  }
  function save(choice) {
    try { localStorage.setItem(KEY, JSON.stringify({ c: choice, t: Date.now() })); } catch (e) {}
  }
  function forget() {
    var names = ['_ga', '_ga_' + ID.slice(2)], host = location.hostname, parts = host.split('.');
    var domains = ['', ';domain=' + host, ';domain=.' + host, ';domain=.' + parts.slice(-2).join('.')];
    names.forEach(function (n) {
      domains.forEach(function (d) { document.cookie = n + '=; Max-Age=0; path=/' + d; });
    });
  }

  var loaded = false;
  function load() {
    if (loaded) return;
    loaded = true;
    window['ga-disable-' + ID] = false;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', ID, { allow_google_signals: false, allow_ad_personalization_signals: false, cookie_flags: 'SameSite=Lax;Secure', cookie_expires: 33696000 });
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + ID;
    document.head.appendChild(s);
  }

  function apply(choice) {
    save(choice);
    if (choice === 'granted') load();
    else { window['ga-disable-' + ID] = true; forget(); }
  }

  function style() {
    if (document.getElementById('consent-style')) return;
    var css = document.createElement('style');
    css.id = 'consent-style';
    css.textContent =
      '#consent{position:fixed;left:12px;right:12px;bottom:12px;z-index:100;max-width:720px;margin:0 auto;padding:16px 18px;border-radius:16px;' +
      'background:var(--surface,#141A2B);color:var(--text,#F4F6FF);border:1px solid var(--border,#2C3550);box-shadow:0 18px 40px rgba(0,0,0,.35);' +
      'font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}' +
      '#consent p{margin:0 0 12px}#consent a{color:inherit;text-decoration:underline}' +
      '#consent .cb{display:flex;flex-wrap:wrap;gap:10px;align-items:center}' +
      '#consent button{min-height:44px;padding:0 22px;border-radius:999px;border:1px solid var(--text,#F4F6FF);background:transparent;color:inherit;' +
      'font:700 15px -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;cursor:pointer}' +
      '#consent button:focus-visible,#consent a:focus-visible{outline:2px solid var(--or,#FFC53D);outline-offset:2px}';
    document.head.appendChild(css);
  }

  function hide() {
    var box = document.getElementById('consent');
    if (box) box.remove();
  }

  function show() {
    if (document.getElementById('consent')) return;
    style();
    var box = document.createElement('div');
    box.id = 'consent';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', T.label);
    var p = document.createElement('p');
    p.appendChild(document.createTextNode(T.text + ' '));
    var more = document.createElement('a');
    more.href = T.page;
    more.textContent = T.more;
    p.appendChild(more);
    var row = document.createElement('div');
    row.className = 'cb';
    [['granted', T.yes], ['denied', T.no]].forEach(function (b) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = b[1];
      button.addEventListener('click', function () { apply(b[0]); hide(); });
      row.appendChild(button);
    });
    box.appendChild(p);
    box.appendChild(row);
    document.body.appendChild(box);
  }

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-consent-open]') : null;
    if (t) { e.preventDefault(); show(); }
  });

  function footerLink() {
    var bottom = document.querySelector('.fbottom');
    if (!bottom || bottom.querySelector('[data-consent-open]')) return;
    var span = document.createElement('span');
    var a = document.createElement('a');
    a.href = '#';
    a.setAttribute('data-consent-open', '');
    a.textContent = T.manage;
    span.appendChild(a);
    bottom.appendChild(span);
  }

  function start() {
    footerLink();
    var choice = read();
    if (choice === 'granted') load();
    else if (choice === null) show();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
