import unittest
from unittest.mock import Mock

from bs4 import BeautifulSoup

from deal_radar_sources import (
    _ml_card_offer,
    _ml_product_from_json,
    _ml_search_diagnostic,
)


class MercadoLivreParserTests(unittest.TestCase):
    def test_extracts_offer_from_poly_card_markup(self):
        html = """
        <li class="poly-card">
          <a class="poly-component__title"
             href="https://www.mercadolivre.com.br/console-playstation-5/p/MLB12345678">
            Console PlayStation 5 Slim 1TB
          </a>
          <div class="poly-price__current">
            <span class="andes-money-amount">
              <span class="andes-money-amount__currency-symbol">R$</span>
              <span class="andes-money-amount__fraction">3.499</span>
              <span class="andes-money-amount__cents">90</span>
            </span>
          </div>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        offer = _ml_card_offer(soup.select_one("a.poly-component__title"), "https://lista.mercadolivre.com.br/console-playstation-5")

        self.assertIsNotNone(offer)
        self.assertEqual(offer["title"], "Console PlayStation 5 Slim 1TB")
        self.assertEqual(offer["price"], 3499.90)
        self.assertTrue(offer["url"].startswith("https://www.mercadolivre.com.br/"))

    def test_extracts_offer_from_alternate_item_link_markup(self):
        html = """
        <div class="ui-search-result">
          <a href="https://produto.mercadolivre.com.br/MLB-123456789-console-playstation-5">
            <h2>Console PlayStation 5</h2>
          </a>
          <span>R$ 3.299,00</span>
          <span>Frete grátis</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        offer = _ml_card_offer(soup.select_one("a[href]"), "https://lista.mercadolivre.com.br/console-playstation-5")

        self.assertIsNotNone(offer)
        self.assertEqual(offer["title"], "Console PlayStation 5")
        self.assertEqual(offer["price"], 3299.00)
        self.assertTrue(offer["free_shipping"])

    def test_reads_product_json_ld(self):
        product = {
            "@type": "Product",
            "name": "Console PlayStation 5",
            "url": "https://www.mercadolivre.com.br/console-playstation-5/p/MLB12345678",
            "image": "https://http2.mlstatic.com/example.jpg",
            "offers": {"@type": "Offer", "price": "3299.90", "priceCurrency": "BRL"},
        }
        offer = _ml_product_from_json(product, "https://lista.mercadolivre.com.br/console-playstation-5")

        self.assertIsNotNone(offer)
        self.assertEqual(offer["price"], 3299.90)
        self.assertEqual(offer["title"], "Console PlayStation 5")

    def test_diagnostic_identifies_antibot_page(self):
        response = Mock()
        response.status_code = 200
        response.url = "https://lista.mercadolivre.com.br/console-playstation-5"
        response.text = "<html><title>Security Check</title><body>Verify you are human</body></html>"
        soup = BeautifulSoup(response.text, "html.parser")

        message = _ml_search_diagnostic(response, soup)
        self.assertIn("verificação de segurança/antirobô", message)
        self.assertIn("HTTP 200", message)


if __name__ == "__main__":
    unittest.main()
