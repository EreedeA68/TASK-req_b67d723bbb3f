"""Tier-based discount rule model."""
from app.db import db


class TierRule(db.Model):
    __tablename__ = "tier_rules"

    id = db.Column(db.Integer, primary_key=True)
    tier_name = db.Column(db.String(32), unique=True, nullable=False)
    max_discount_pct = db.Column(db.Float, nullable=False, default=0.0)  # e.g., 0.10 for 10%
    description = db.Column(db.String(255), nullable=True)
    # Semicolon-separated list of human-readable tier benefits (e.g.
    # "Priority pickup;Free photo reprint;Member events").  Stored as a
    # single column for simplicity; split on render.
    benefits = db.Column(db.Text, nullable=True)

    def benefits_list(self) -> list[str]:
        if not self.benefits:
            return []
        return [b.strip() for b in self.benefits.split(";") if b.strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tier_name": self.tier_name,
            "max_discount_pct": self.max_discount_pct,
            "description": self.description,
            "benefits": self.benefits_list(),
        }
