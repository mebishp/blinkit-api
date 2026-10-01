from app.schemas import Price, Product, Rating, SortOption
from app.services.query import ListingQuery, apply


def mk(id, price, mrp=None, brand="A", in_stock=True, rating=None, sponsored=False, name=None):
    mrp = mrp or price
    disc = round((mrp - price) / mrp * 100, 1) if mrp > price else 0.0
    return Product(
        id=str(id),
        name=name or f"P{id}",
        brand=brand,
        price=Price(selling=price, mrp=mrp, discount_pct=disc),
        in_stock=in_stock,
        rating=Rating(value=rating) if rating else None,
        is_sponsored=sponsored,
        url="u",
    )


ITEMS = [
    mk(1, 50, 60, brand="Amul", rating=4.1),
    mk(2, 20, brand="Nandini", rating=4.6),
    mk(3, 80, 160, brand="amul", in_stock=False),
    mk(4, 35, brand="Heritage", sponsored=True),
]


def ids(ps):
    return [p.id for p in ps]


def test_relevance_keeps_upstream_order():
    assert ids(apply(ITEMS, ListingQuery())) == ["1", "2", "3", "4"]
    assert not ListingQuery().needs_full_scan


def test_sorts():
    assert ids(apply(ITEMS, ListingQuery(sort=SortOption.price_asc))) == ["2", "4", "1", "3"]
    assert ids(apply(ITEMS, ListingQuery(sort=SortOption.price_desc))) == ["3", "1", "4", "2"]
    assert ids(apply(ITEMS, ListingQuery(sort=SortOption.discount_desc)))[:2] == ["3", "1"]
    assert ids(apply(ITEMS, ListingQuery(sort=SortOption.rating_desc)))[:2] == ["2", "1"]


def test_filters():
    assert ids(apply(ITEMS, ListingQuery(brands=["AMUL"]))) == ["1", "3"]
    assert ids(apply(ITEMS, ListingQuery(min_price=30, max_price=60))) == ["1", "4"]
    assert ids(apply(ITEMS, ListingQuery(in_stock=True, brands=["amul"]))) == ["1"]
    assert ids(apply(ITEMS, ListingQuery(in_stock=False))) == ["3"]
    assert ids(apply(ITEMS, ListingQuery(min_discount=40))) == ["3"]
    assert ids(apply(ITEMS, ListingQuery(min_rating=4.5))) == ["2"]
    assert ids(apply(ITEMS, ListingQuery(exclude_sponsored=True))) == ["1", "2", "3"]
    assert ListingQuery(in_stock=True).needs_full_scan


def test_page_bounds():
    q = ListingQuery(page=3, page_size=10)
    assert (q.start, q.end) == (20, 30)
