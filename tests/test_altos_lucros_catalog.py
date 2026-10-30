from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestAltosLucrosCatalogVisibility(unittest.TestCase):
    def test_tool_is_registered_in_investments_and_prioritized(self):
        source = (ROOT / "app.js").read_text(encoding="utf-8")
        marker = "id:'altos-lucros',cat:'investimentos'"
        self.assertIn(marker, source)
        self.assertLess(source.index(marker), source.index("id:'porcentagem'"))
        self.assertIn("a.id==='altos-lucros'?-1", source)

    def test_featured_tool_card_is_highlighted(self):
        source = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("al-tool-featured", source)
        styles = (ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn("ALTOS LUCROS — destaque dentro da grade", styles)

    def test_homepage_has_direct_link_to_tool(self):
        source = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("investmentSpotlight", source)
        self.assertIn("#/ferramenta/altos-lucros", source)

    def test_tool_page_mount_and_assets_are_loaded(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("if(id==='altos-lucros')return '<div id=\"altosLucrosToolHost\"></div>';", app)
        self.assertIn("altos-lucros.js?v=20261030-2", index)
        self.assertIn("altos-lucros.css?v=20261030-2", index)


if __name__ == "__main__":
    unittest.main()
