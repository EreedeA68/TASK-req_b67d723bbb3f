"""Tier rule + benefits JSON API (read-only for members/staff)."""
from flask import Blueprint, jsonify

from app.core.rbac import login_required
from app.models.tier_rule import TierRule

tiers_api_bp = Blueprint("tiers_api", __name__)


@tiers_api_bp.get("")
@login_required
def list_tiers():
    tiers = TierRule.query.order_by(TierRule.max_discount_pct).all()
    return jsonify({"results": [t.to_dict() for t in tiers]})


@tiers_api_bp.get("/<string:tier_name>")
@login_required
def get_tier(tier_name: str):
    tier = TierRule.query.filter_by(tier_name=tier_name).first()
    if tier is None:
        return jsonify({"error": "tier not found"}), 404
    return jsonify(tier.to_dict())
