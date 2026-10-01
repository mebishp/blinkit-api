from app.blinkit import parser
from app.blinkit.categories import build_category_tree, humanize
from tests.conftest import load_json, load_text


def test_parse_search_listing():
    products, next_url, total = parser.parse_listing(load_json("search_milk_delhi.json")["response"])
    assert len(products) == 12
    assert next_url and "offset=12" in next_url
    assert total == 38

    p = products[0]
    assert p.id == "793109"
    assert p.name == "Country Delight 25 g High Protein Vanilla Milk"
    assert p.brand == "Country Delight"
    assert p.unit == "250 ml"
    assert p.price.selling == 101 and p.price.mrp == 129
    assert p.price.discount_pct == 21.7
    assert p.in_stock and p.inventory == 1
    assert p.merchant_id == "36778"
    assert p.is_sponsored
    assert p.url.endswith("/prid/793109")
    assert all(x.price.selling is not None for x in products)


def test_parse_category_listing():
    products, next_url, total = parser.parse_listing(load_json("listing_14_922.json")["response"])
    assert len(products) == 15
    assert total == 88
    assert "l1_cat=922" in next_url
    assert len({p.id for p in products}) == len(products)


def test_parse_product_detail():
    d = parser.parse_product_detail(load_json("product_pdp.json")["response"], 793109)
    assert d is not None
    assert d.name == "Country Delight 25 g High Protein Vanilla Milk"
    assert d.price.selling == 101 and d.price.mrp == 129
    assert len(d.images) == 5
    assert d.categories["l0"].id == 12
    assert d.categories["l0"].name == "Tea, Coffee & Milk Drinks"
    assert d.breadcrumbs[0] == "Tea, Coffee & Milk Drinks"
    assert d.attributes["Shelf Life"] == "90 days"
    assert "is_return_eligible" not in d.attributes  # internal flags dropped
    assert d.description and d.description.startswith("Country Delight")
    assert d.similar and all(s.id != "793109" for s in d.similar)


def test_parse_location_and_eta():
    info = parser.parse_location_info(load_json("location_info_koramangala.json"))
    assert info["serviceable"] is True
    assert info["postal_code"] == "560034"
    assert round(info["lat"], 3) == 12.935

    assert (
        parser.parse_location_info({"is_serviceable": False, "coordinate": {"lat": 0, "lon": 0}})["lat"]
        is None
    )
    assert parser.parse_eta(load_json("eta.json"))[0] == 11


def test_parse_autosuggest():
    out = parser.parse_autosuggest(load_json("autosuggest_koramangala.json"))
    assert out[0]["title"] == "Koramangala"
    assert out[0]["place_id"].startswith("ChIJ")


def test_card_parser_tolerates_missing_fields():
    assert parser.parse_product_card({}) is None
    p = parser.parse_product_card(
        {
            "identity": {"id": "42"},
            "name": {"text": "Thing"},
            "normal_price": {"text": "₹1,299"},
            "is_sold_out": True,
        }
    )
    assert p.price.selling == 1299 and p.price.mrp == 1299 and not p.in_stock


def test_category_tree_from_sitemaps():
    tree = build_category_tree(load_text("sitemap_categories.xml"), load_text("sitemap_index.xml"))
    assert len(tree) > 20
    dairy = next(c for c in tree if c.id == 14)
    assert any(s.id == 922 and s.slug == "milk" for s in dairy.subcategories)
    assert not dairy.name.startswith("Category ")  # got a readable name from the product index
    assert humanize("tea-coffee-and-more") == "Tea Coffee and More"
