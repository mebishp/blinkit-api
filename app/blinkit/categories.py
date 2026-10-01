"""Category tree built from Blinkit's public sitemaps.

`/sitemaps/categories.xml` lists every subcategory page as
`/cn/<l1-slug>/cid/<l0-id>/<l1-id>`. The product sitemap index
(`/sitemap.xml`) has paths `/sitemaps/products/<l0-slug>/<l1-slug>/...`, which
gives us the parent category's slug (and so a readable name).
"""

import re
from collections import Counter, defaultdict

from app.schemas import Category

_CID_RE = re.compile(r"<loc>https?://[^<]*/cn/([a-z0-9\-]+)/cid/(\d+)/(\d+)</loc>")
_PRODUCT_SITEMAP_RE = re.compile(r"/sitemaps/products/([a-z0-9\-]+)/([a-z0-9\-]+)/")

_SMALL_WORDS = {"and", "or", "of", "for", "the", "in", "a"}


def humanize(slug: str) -> str:
    words = slug.split("-")
    return " ".join(w if (i and w in _SMALL_WORDS) else w.capitalize() for i, w in enumerate(words))


def build_category_tree(categories_xml: str, sitemap_index_xml: str = "") -> list[Category]:
    l1_to_l0_slug = {l1: l0 for l0, l1 in _PRODUCT_SITEMAP_RE.findall(sitemap_index_xml)}

    children: dict[int, list[Category]] = defaultdict(list)
    l0_slug_votes: dict[int, Counter] = defaultdict(Counter)
    seen: set[tuple[int, int]] = set()

    for slug, l0, l1 in _CID_RE.findall(categories_xml):
        l0_id, l1_id = int(l0), int(l1)
        if (l0_id, l1_id) in seen:
            continue
        seen.add((l0_id, l1_id))
        children[l0_id].append(
            Category(
                id=l1_id,
                name=humanize(slug),
                slug=slug,
                url=f"https://blinkit.com/cn/{slug}/cid/{l0_id}/{l1_id}",
            )
        )
        if slug in l1_to_l0_slug:
            l0_slug_votes[l0_id][l1_to_l0_slug[slug]] += 1

    tree = []
    for l0_id, subs in children.items():
        votes = l0_slug_votes.get(l0_id)
        l0_slug = votes.most_common(1)[0][0] if votes else f"category-{l0_id}"
        tree.append(
            Category(
                id=l0_id,
                name=humanize(l0_slug) if votes else f"Category {l0_id}",
                slug=l0_slug,
                url=subs[0].url,
                subcategories=sorted(subs, key=lambda c: c.name),
            )
        )
    return sorted(tree, key=lambda c: c.name)
