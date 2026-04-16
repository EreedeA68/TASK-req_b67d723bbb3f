"""Catalog item model for products, photo packages, and educational items."""
from datetime import datetime

from app.db import db


class CatalogItem(db.Model):
    __tablename__ = "catalog_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(64), nullable=False, index=True)  # product, photo_package, educational
    taxonomy = db.Column(db.String(100), nullable=True)  # e.g., "mammals", "birds"
    region = db.Column(db.String(100), nullable=True)
    habitat = db.Column(db.String(100), nullable=True)
    size_range = db.Column(db.String(50), nullable=True)  # small, medium, large
    protection_level = db.Column(db.String(50), nullable=True)  # endangered, vulnerable, etc.
    price = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text, nullable=True)
    pinyin_name = db.Column(db.String(200), nullable=True, index=True)  # pinyin transliteration for fuzzy search
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "taxonomy": self.taxonomy,
            "region": self.region,
            "habitat": self.habitat,
            "size_range": self.size_range,
            "protection_level": self.protection_level,
            "price": self.price,
            "description": self.description,
            "pinyin_name": self.pinyin_name,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
