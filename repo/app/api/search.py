"""Search JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import search_service
from app.services.search_service import SearchError

search_api_bp = Blueprint("search_api", __name__)


@search_api_bp.get("")
@permission_required("search", "perform")
def search():
    query = (request.args.get("q") or "").strip()
    category = request.args.get("category")
    taxonomy = request.args.get("taxonomy") or None
    region = request.args.get("region") or None
    habitat = request.args.get("habitat") or None
    size_range = request.args.get("size_range") or None
    protection_level = request.args.get("protection_level") or None
    if not query:
        return jsonify({"error": "query 'q' must not be empty"}), 400
    actor = get_current_user()
    is_admin = actor is not None and actor.has_role("admin")
    device_id = request.headers.get("X-Device-ID") or None
    try:
        results = search_service.perform_search(
            query,
            category=category,
            taxonomy=taxonomy,
            region=region,
            habitat=habitat,
            size_range=size_range,
            protection_level=protection_level,
            user_id=actor.id if actor else None,
            actor_id=actor.id if actor else None,
            is_admin=is_admin,
            actor=actor,
            device_id=device_id,
        )
    except SearchError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(results)


@search_api_bp.get("/recent")
@permission_required("search", "perform")
def recent():
    actor = get_current_user()
    limit = request.args.get("limit", 10, type=int)
    device_id = request.headers.get("X-Device-ID") or None
    entries = search_service.get_recent(
        user_id=actor.id if actor else None, device_id=device_id, limit=limit
    )
    return jsonify({"results": [e.to_dict() for e in entries]})


@search_api_bp.get("/trending")
@permission_required("search", "trending")
def trending():
    limit = request.args.get("limit", 10, type=int)
    device_id = request.headers.get("X-Device-ID") or None
    trends = search_service.get_trending(limit=limit, device_id=device_id)
    return jsonify({"results": [t.to_dict() for t in trends]})
