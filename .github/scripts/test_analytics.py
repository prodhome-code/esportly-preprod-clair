"""Tests de analytics.py : la CSP s'élargit juste ce qu'il faut, la balise arrive une seule fois, rien ne bouge sur une page en règle."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analytics  # noqa: E402

SELF = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; script-src 'sha256-AAA='; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'\">")
NONE = "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'\">"
NO_SCRIPT = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; script-src 'none'; img-src 'self'; "
             "connect-src 'self'\">")


def page(csp: str, eol: str = "\n", extra: str = "") -> str:
    return f"<!doctype html>{eol}<html lang=\"fr\"><head>{csp}{extra}</head>{eol}<body>{eol}<p>x</p>{eol}</body>{eol}</html>{eol}"


class AnalyticsTest(unittest.TestCase):
    def test_csp_avec_script_src_garde_les_empreintes_et_gagne_google(self):
        shown = analytics.apply(page(SELF))
        self.assertIn("script-src 'sha256-AAA=' 'self' https://www.googletagmanager.com;", shown)
        self.assertIn("img-src 'self' data: https://*.google-analytics.com https://*.googletagmanager.com;", shown)
        self.assertIn("connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com;", shown)
        self.assertIn("object-src 'none'; base-uri 'none'", shown)  # le reste ne bouge pas

    def test_script_src_none_est_remplace(self):
        shown = analytics.apply(page(NO_SCRIPT))
        self.assertIn("script-src 'self' https://www.googletagmanager.com;", shown)
        self.assertNotIn("script-src 'none'", shown)

    def test_csp_default_src_none_gagne_les_trois_directives(self):
        shown = analytics.apply(page(NONE))
        self.assertIn("default-src 'none'; style-src 'unsafe-inline'; script-src 'self' https://www.googletagmanager.com; "
                      "img-src https://*.google-analytics.com https://*.googletagmanager.com; connect-src ", shown)
        self.assertIn("; base-uri 'none'", shown)

    def test_balise_une_seule_fois_avant_body_et_rejouable(self):
        once = analytics.apply(page(SELF))
        self.assertEqual(once.count(analytics.TAG), 1)
        self.assertTrue(once.index(analytics.TAG) < once.index("</body>"))
        self.assertEqual(analytics.apply(once), once)

    def test_fins_de_ligne_de_la_page_gardees(self):
        shown = analytics.apply(page(SELF, "\r\n"))
        self.assertNotIn("\n\n", shown.replace("\r\n", ""))
        self.assertIn(analytics.TAG + "\r\n</body>", shown)

    def test_redirection_et_page_sans_csp_laissees_telles_quelles(self):
        redirect = page(NONE, extra='<meta http-equiv="refresh" content="0; url=/">')
        self.assertEqual(analytics.apply(redirect), redirect)
        bare = "<html><body></body></html>"
        self.assertEqual(analytics.apply(bare), bare)

    def test_main_ne_touche_pas_widget_ni_docs_et_check_signale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.html", "equipes/b.html", "widget/fr/c.html", "docs/d.html"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(page(SELF).encode())
            self.assertEqual(analytics.main(["--check"], root), 1)
            self.assertEqual(analytics.main([], root), 0)
            self.assertEqual(analytics.main(["--check"], root), 0)
            self.assertIn("analytics.js", (root / "equipes/b.html").read_text(encoding="utf-8"))
            self.assertNotIn("analytics.js", (root / "widget/fr/c.html").read_text(encoding="utf-8"))
            self.assertNotIn("analytics.js", (root / "docs/d.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
