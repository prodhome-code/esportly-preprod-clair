"""Tests de qr_ordinateur.py : l'encadré arrive une seule fois, dans la langue de la page, sans toucher aux redirections ni aux widgets."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import qr_ordinateur as qr  # noqa: E402

REAL = Path(__file__).resolve().parents[2]


def page(lang: str = "fr", eol: str = "\n", head: str = "") -> str:
    return f'<!doctype html>{eol}<html lang="{lang}"><head>{head}</head>{eol}<body>{eol}<p>x</p>{eol}</body>{eol}</html>{eol}'


class QrOrdinateur(unittest.TestCase):
    def test_encadre_dans_la_langue_de_la_page(self):
        for lang, start in (("fr", "Sur ordinateur&nbsp;?"), ("en", "On a computer?"), ("es", "¿En el ordenador?"),
                            ("de", "Am Computer?"), ("pt-BR", "No computador?"), ("pt", "No computador?"), ("ja", "On a computer?")):
            with self.subTest(lang=lang):
                shown = qr.apply(page(lang))
                self.assertEqual(shown.count('class="qrfix"'), 1)
                self.assertIn(f"<span>{start}", shown)
                self.assertIn('<img src="/qr-beta.svg" alt="" width="76" height="76" loading="lazy">', shown)
                self.assertTrue(shown.index('class="qrfix"') < shown.index("</body>"))  # avant la fin du corps de page

    def test_rejouable_et_fins_de_ligne(self):
        for eol in ("\n", "\r\n"):
            with self.subTest(eol=repr(eol)):
                once = qr.apply(page("en", eol))
                self.assertEqual(qr.apply(once), once)
                self.assertEqual(once.count("\n") - once.count("\r\n") if eol == "\r\n" else once.count("\r"), 0)  # fins de ligne conservées

    def test_redirection_et_page_sans_corps_inchangees(self):
        redirect = page("fr", head='<meta http-equiv="refresh" content="0; url=/">')
        self.assertEqual(qr.apply(redirect), redirect)
        self.assertEqual(qr.apply("<html lang=\"fr\"><p>fragment</p></html>"), "<html lang=\"fr\"><p>fragment</p></html>")

    def test_widgets_et_dossiers_techniques_ignores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.html", "equipes/b.html", "widget/fr/c.html", "docs/d.html", "news/e.html"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(page(), encoding="utf-8")
            self.assertEqual(qr.main(["--check"], root), 1)
            self.assertEqual(qr.main([], root), 0)
            changed = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.html") if 'class="qrfix"' in p.read_text(encoding="utf-8"))
            self.assertEqual(changed, ["a.html", "equipes/b.html"])
            self.assertEqual(qr.main(["--check"], root), 0)

    def test_feuille_de_style_ordinateur_seulement(self):
        css = (REAL / "qr-flottant.css").read_text(encoding="utf-8")
        self.assertIn(".qrfix{display:none}", css)  # caché par défaut : téléphone et tablette ne le voient pas
        self.assertIn("@media (min-width:1100px) and (hover:hover) and (pointer:fine){", css)
        self.assertRegex(css, r"\.qrfix\{display:flex;position:fixed;left:12px;bottom:12px;")
        self.assertIn("@media print{.qrfix{display:none!important}}", css)

    def test_toutes_les_pages_du_site_l_ont(self):
        """Dans l'arbre de travail, chaque page publique (hors widgets et redirections) a un seul encadré, et la feuille de style existe."""
        self.assertTrue((REAL / "qr-beta.svg").is_file())
        self.assertTrue((REAL / "qr-flottant.css").is_file())
        count = 0
        for path in qr.pages(REAL):
            text = path.read_bytes().decode("utf-8")
            if 'http-equiv="refresh"' in text or "</body>" not in text:
                continue
            count += 1
            with self.subTest(page=path.relative_to(REAL).as_posix()):
                self.assertEqual(text.count('class="qrfix"'), 1)
                self.assertEqual(len(re.findall(r'<link rel="stylesheet" href="/qr-flottant.css">', text)), 1)
        self.assertGreater(count, 300)


if __name__ == "__main__":
    unittest.main()
