"""Catalog/product search tests — name search, filter by taxonomy, region, combined."""

from app.db import db
from app.models.catalog import CatalogItem


def _seed_catalog(app):
    """Seed a few catalog items for testing."""
    items = [
        CatalogItem(
            name="African Elephant Photo Package",
            category="photo_package",
            taxonomy="mammals",
            region="africa",
            habitat="savanna",
            size_range="large",
            protection_level="endangered",
            price=49.99,
            description="Stunning elephant photography experience",
            active=True,
        ),
        CatalogItem(
            name="Bald Eagle Educational Kit",
            category="educational",
            taxonomy="birds",
            region="north_america",
            habitat="forest",
            size_range="medium",
            protection_level="least_concern",
            price=29.99,
            description="Learn about the majestic bald eagle",
            active=True,
        ),
        CatalogItem(
            name="Komodo Dragon Poster",
            category="product",
            taxonomy="reptiles",
            region="asia",
            habitat="forest",
            size_range="large",
            protection_level="vulnerable",
            price=14.99,
            description="High quality poster of the komodo dragon",
            active=True,
        ),
        CatalogItem(
            name="Wildlife Safari T-Shirt",
            category="product",
            taxonomy=None,
            region=None,
            habitat=None,
            size_range=None,
            protection_level=None,
            price=24.99,
            description="Comfortable cotton t-shirt with wildlife print",
            active=True,
        ),
        CatalogItem(
            name="Inactive Old Item",
            category="product",
            taxonomy="mammals",
            region="africa",
            habitat="savanna",
            size_range="small",
            protection_level="endangered",
            price=9.99,
            description="This item is inactive",
            active=False,
        ),
    ]
    for item in items:
        db.session.add(item)
    db.session.commit()
    return items


def test_search_catalog_by_name(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=Elephant")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert any("Elephant" in item["name"] for item in catalog)


def test_search_catalog_excludes_inactive(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=Inactive")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) == 0


def test_search_catalog_filter_by_taxonomy(client, logged_in_staff, app):
    _seed_catalog(app)
    # Search for broad term but filter by birds taxonomy
    resp = client.get("/api/search?q=eagle&taxonomy=birds")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert all(item["taxonomy"] == "birds" for item in catalog)


def test_search_catalog_filter_by_region(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=photo&region=africa")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert all(item["region"] == "africa" for item in catalog)


def test_search_catalog_combined_filters(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get(
        "/api/search?q=poster&taxonomy=reptiles&region=asia"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert catalog[0]["name"] == "Komodo Dragon Poster"


def test_search_catalog_filter_no_results(client, logged_in_staff, app):
    _seed_catalog(app)
    # Search for elephant but filter by birds — should not match
    resp = client.get("/api/search?q=Elephant&taxonomy=birds")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) == 0


def test_search_catalog_highlighted(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=Eagle")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    highlighted = catalog[0].get("name_highlighted", "")
    assert "<mark>" in highlighted


def test_search_catalog_by_description(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=cotton")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert any("T-Shirt" in item["name"] for item in catalog)


def test_search_catalog_filter_by_protection_level(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=photo&protection_level=endangered")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert all(item["protection_level"] == "endangered" for item in catalog)


def test_search_catalog_filter_by_habitat(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=kit&habitat=forest")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert all(item["habitat"] == "forest" for item in catalog)


def test_search_catalog_filter_by_size_range(client, logged_in_staff, app):
    _seed_catalog(app)
    resp = client.get("/api/search?q=photo&size_range=large")
    assert resp.status_code == 200
    data = resp.get_json()
    catalog = data["catalog_items"]
    assert len(catalog) >= 1
    assert all(item["size_range"] == "large" for item in catalog)
