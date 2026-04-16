"""Tests for pinyin fuzzy search matching."""
from app.db import db
from app.models.catalog import CatalogItem


def _seed_catalog(app):
    """Seed catalog items for pinyin search testing."""
    items = [
        CatalogItem(name="Bengal Tiger Photo Package", category="photo_package",
                     taxonomy="mammals", region="asia", pinyin_name="mengjiala laohu",
                     price=29.99, active=True),
        CatalogItem(name="Eagle Viewing Tour", category="educational",
                     taxonomy="birds", region="north_america",
                     price=15.00, active=True),
        CatalogItem(name="Panda Plush Toy", category="product",
                     taxonomy="mammals", region="asia", pinyin_name="xiongmao",
                     price=19.99, active=True),
        CatalogItem(name="Lion Safari Hat", category="product",
                     taxonomy="mammals", region="africa", pinyin_name="shizi",
                     price=12.99, active=True),
    ]
    for item in items:
        db.session.add(item)
    db.session.commit()


def test_pinyin_laohu_finds_tiger(app, logged_in_staff, client):
    """Searching 'laohu' (pinyin for tiger) should find tiger items."""
    _seed_catalog(app)
    resp = client.get("/api/search?q=laohu")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data.get("catalog_items", [])
    names = [c["name"] for c in catalog]
    assert any("Tiger" in n for n in names)


def test_pinyin_niao_finds_birds(app, logged_in_staff, client):
    """Searching 'niao' (pinyin for bird) should find bird items."""
    _seed_catalog(app)
    resp = client.get("/api/search?q=niao")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data.get("catalog_items", [])
    # niao → bird → should match Eagle Viewing Tour via synonym chain
    expanded = data.get("query_expanded", [])
    assert "bird" in expanded or any("bird" in str(c).lower() for c in catalog)


def test_pinyin_xiongmao_finds_panda(app, logged_in_staff, client):
    """Searching 'xiongmao' should match via pinyin_name field."""
    _seed_catalog(app)
    resp = client.get("/api/search?q=xiongmao")
    assert resp.status_code == 200
    catalog = resp.get_json().get("catalog_items", [])
    names = [c["name"] for c in catalog]
    assert any("Panda" in n for n in names)


def test_pinyin_expansion_in_variants(app):
    """_expand_synonyms should include pinyin-resolved terms."""
    from app.services.search_service import _expand_synonyms

    variants = _expand_synonyms("laohu")
    assert "tiger" in variants

    variants2 = _expand_synonyms("niao")
    assert "bird" in variants2

    variants3 = _expand_synonyms("dongwu")
    assert "animal" in variants3 or "wildlife" in variants3


def test_pinyin_shizi_finds_lion(app, logged_in_staff, client):
    """Searching 'shizi' should find lion items via pinyin_name."""
    _seed_catalog(app)
    resp = client.get("/api/search?q=shizi")
    assert resp.status_code == 200
    catalog = resp.get_json().get("catalog_items", [])
    names = [c["name"] for c in catalog]
    assert any("Lion" in n for n in names)
