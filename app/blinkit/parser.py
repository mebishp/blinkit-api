"""Turn Blinkit's widget/snippet layout JSON into flat models.

The layout format is UI-oriented and changes often, so every accessor here is
defensive: a missing field yields None rather than an exception.
"""

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.schemas import CategoryRef, Price, Product, ProductDetail, Rating

_PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _get(obj: Any, *path: str | int) -> Any:
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return None
    return obj


def _money(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text.split("|")[-1])
    return float(m.group().replace(",", "")) if m else None


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "product"


def product_url(product_id: str, name: str) -> str:
    return f"https://blinkit.com/prn/{slugify(name)}/prid/{product_id}"


def _discount(selling: float | None, mrp: float | None) -> float:
    if selling is None or not mrp or mrp <= selling:
        return 0.0
    return round((mrp - selling) / mrp * 100, 1)


def _cart_item(data: dict) -> dict:
    for path in (
        ("atc_action", "add_to_cart", "cart_item"),
        ("rfc_action", "remove_from_cart", "cart_item"),
        ("atc_actions_v2", "default", 0, "add_to_cart", "cart_item"),
        ("stepper_data_v2", "increment_actions", "default", 0, "add_to_cart", "cart_item"),
    ):
        ci = _get(data, *path)
        if isinstance(ci, dict):
            return ci
    return {}


def parse_product_card(data: dict, tracking: dict | None = None) -> Product | None:
    """Parse a product card snippet's `data` (search, listing, PDP rails)."""
    tracking = tracking or {}
    ci = _cart_item(data)
    attrs = _get(tracking, "common_attributes") or _get(tracking, "click_map") or {}

    pid = (
        ci.get("product_id")
        or data.get("product_id")
        or _get(data, "identity", "id")
        or attrs.get("product_id")
    )
    if pid is None or not str(pid).isdigit():
        return None
    pid = str(pid)

    name = (
        ci.get("display_name")
        or ci.get("product_name")
        or _get(data, "display_name", "text")
        or _get(data, "name", "text")
        or attrs.get("name")
    )
    if not name:
        return None

    selling = _num(ci.get("price")) or _num(attrs.get("price")) or _money(_get(data, "normal_price", "text"))
    mrp = _num(ci.get("mrp")) or _num(attrs.get("mrp")) or _money(_get(data, "mrp", "text")) or selling

    inventory = ci.get("inventory", data.get("inventory", attrs.get("inventory")))
    inventory = int(inventory) if isinstance(inventory, (int, float)) else None
    state = data.get("product_state") or attrs.get("state")
    in_stock = (
        not data.get("is_sold_out", False)
        and state in (None, "available")
        and (inventory is None or inventory > 0)
    )

    rating_val = _num(_get(data, "rating", "bar", "value")) or _num(attrs.get("rating"))
    rating_val = round(rating_val, 2) if rating_val is not None else None
    rating_count = _get(data, "rating", "bar", "title", "text")
    rating = Rating(value=rating_val, count=rating_count) if rating_val or rating_count else None

    merchant_id = ci.get("merchant_id") or data.get("merchant_id") or _get(data, "meta", "merchant_id")

    return Product(
        id=pid,
        name=name,
        brand=ci.get("brand") or _get(data, "brand_name", "text") or attrs.get("brand") or None,
        unit=ci.get("unit") or _get(data, "variant", "text"),
        price=Price(selling=selling, mrp=mrp, discount_pct=_discount(selling, mrp)),
        in_stock=in_stock,
        inventory=inventory,
        image=ci.get("image_url") or _get(data, "image", "url"),
        rating=rating,
        product_type=attrs.get("ptype") or None,
        merchant_id=str(merchant_id) if merchant_id is not None else None,
        merchant_type=ci.get("merchant_type") or data.get("merchant_type"),
        group_id=ci.get("group_id") or data.get("group_id"),
        is_sponsored=bool(attrs.get("ads_type")) or attrs.get("badge") == "AD",
        url=product_url(pid, name),
    )


def iter_product_snippets(snippets: list[dict] | None) -> Iterator[tuple[dict, dict]]:
    for sn in snippets or []:
        wt = sn.get("widget_type") or ""
        if wt.startswith("product_card"):
            yield sn.get("data") or {}, sn.get("tracking") or {}


def parse_listing(response: dict) -> tuple[list[Product], str | None, int | None]:
    """Parse a search/listing layout response.

    Returns (products, next_url, upstream_total).
    """
    products = []
    seen: set[str] = set()
    for data, tracking in iter_product_snippets(response.get("snippets")):
        p = parse_product_card(data, tracking)
        if p and p.id not in seen:
            seen.add(p.id)
            products.append(p)

    next_url = _get(response, "pagination", "next_url") or None
    total = None
    if next_url:
        qs = parse_qs(urlparse(next_url).query)
        for key in ("total_pagination_items", "search_count"):
            if key in qs and qs[key][0].isdigit():
                total = int(qs[key][0])
                break
    return products, next_url, total


def parse_product_detail(response: dict, product_id: int) -> ProductDetail | None:
    seo = _get(response, "tracking", "le_meta", "custom_data", "seo") or {}
    snippets = response.get("snippets") or []

    atc = next((s.get("data") or {} for s in snippets if s.get("widget_type") == "product_atc_strip"), {})
    base = parse_product_card(atc) if atc else None

    name = seo.get("product_name") or (base.name if base else None)
    if not name:
        return None

    attributes: dict[str, str] = {}
    for a in seo.get("attributes") or []:
        key = a.get("name") or a.get("attribute_name")
        val = a.get("value")
        if key and val not in (None, "") and not key.islower():  # lowercase keys are internal flags
            attributes[key] = str(val)

    categories = {}
    for level, key in (("l0", "L0Cat"), ("l1", "L1Cat"), ("l2", "L2Cat")):
        cat = _get(seo, "categories", key)
        if isinstance(cat, dict) and cat.get("ID"):
            categories[level] = CategoryRef(id=cat["ID"], name=cat.get("Name") or None)

    breadcrumbs: list[str] = []
    for s in snippets:
        if s.get("widget_type") == "horizontal_text_list_snippet":
            for i, item in enumerate(_get(s, "data", "horizontal_item_list") or []):
                text = _get(item, "title", "text")
                if not text:
                    continue
                breadcrumbs.append(text)
                if i < 3 and f"l{i}" in categories and not categories[f"l{i}"].name:
                    categories[f"l{i}"].name = text
            break

    similar: list[Product] = []
    seen = {str(product_id)}
    for s in snippets:
        if s.get("widget_type") != "horizontal_list":
            continue
        for item in _get(s, "data", "horizontal_item_list") or []:
            p = parse_product_card(item.get("data") or {}, item.get("tracking"))
            if p and p.id not in seen:
                seen.add(p.id)
                similar.append(p)

    selling = _num(seo.get("price")) or (base.price.selling if base else None)
    mrp = _num(seo.get("mrp")) or (base.price.mrp if base else None) or selling
    inventory = (
        seo.get("inventory") if isinstance(seo.get("inventory"), int) else (base.inventory if base else None)
    )
    images = [u for u in seo.get("images") or [] if u]
    in_stock = base.in_stock if base else bool(inventory)

    return ProductDetail(
        id=str(product_id),
        name=name,
        brand=seo.get("brand") or (base.brand if base else None),
        unit=(base.unit if base else None) or attributes.get("Unit"),
        price=Price(selling=selling, mrp=mrp, discount_pct=_discount(selling, mrp)),
        in_stock=in_stock,
        inventory=inventory,
        image=images[0] if images else (base.image if base else None),
        rating=base.rating if base else None,
        product_type=None,
        merchant_id=base.merchant_id if base else None,
        merchant_type=base.merchant_type if base else None,
        group_id=base.group_id if base else None,
        url=product_url(str(product_id), name),
        images=images,
        categories=categories,
        breadcrumbs=breadcrumbs,
        description=attributes.get("Description"),
        attributes=attributes,
        similar=similar,
    )


def parse_eta(data: dict) -> tuple[int | None, str | None]:
    eta = data.get("eta_in_minutes")
    return (int(eta) if isinstance(eta, (int, float)) and eta > 0 else None), data.get("title") or None


def parse_autosuggest(data: dict) -> list[dict]:
    out = []
    for s in _get(data, "ui_data", "suggestions") or []:
        pid = _get(s, "meta", "place_id")
        title = _get(s, "title", "text")
        if pid and title:
            out.append({"title": title, "subtitle": _get(s, "subtitle", "text"), "place_id": pid})
    return out


def parse_location_info(data: dict) -> dict:
    coord = data.get("coordinate") or {}
    info = data.get("location_info") or {}
    lat, lon = coord.get("lat"), coord.get("lon")
    return {
        "lat": lat if lat else None,
        "lon": lon if lon else None,
        "serviceable": bool(data.get("is_serviceable")),
        "address": info.get("formatted_address") or _get(data, "display_address", "address_line") or None,
        "locality": data.get("locality") or None,
        "city": data.get("city") or info.get("city") or None,
        "state": info.get("state") or None,
        "postal_code": info.get("postal_code") or None,
    }
