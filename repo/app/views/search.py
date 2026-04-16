"""Search views — HTMX live search."""
from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import search_service
from app.services.search_service import SearchError

search_view_bp = Blueprint("search_view", __name__)


@search_view_bp.get("/search")
@permission_required("search", "perform")
def search_page():
    return render_template(
        "search.html",
        user=get_current_user(),
    )


@search_view_bp.get("/search/results")
@permission_required("search", "perform")
def search_results_partial():
    """HTMX partial: live search results."""
    query = (request.args.get("q") or "").strip()
    category = request.args.get("category")
    taxonomy = request.args.get("taxonomy") or None
    region = request.args.get("region") or None
    habitat = request.args.get("habitat") or None
    size_range = request.args.get("size_range") or None
    protection_level = request.args.get("protection_level") or None
    actor = get_current_user()

    if not query:
        return render_template(
            "partials/search_results.html",
            query=query,
            members=[],
            orders=[],
            catalog_items=[],
        )

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
            actor=actor,
            device_id=device_id,
        )
    except SearchError:
        return render_template(
            "partials/search_results.html",
            query=query,
            members=[],
            orders=[],
            catalog_items=[],
        )

    return render_template(
        "partials/search_results.html",
        query=query,
        members=results["members"],
        orders=results["orders"],
        catalog_items=results.get("catalog_items", []),
    )


@search_view_bp.get("/search/suggestions")
@permission_required("search", "perform")
def suggestions():
    actor = get_current_user()
    device_id = request.headers.get("X-Device-ID") or None
    recent = search_service.get_recent(user_id=actor.id if actor else None, device_id=device_id, limit=5)
    trending = search_service.get_trending(limit=5, device_id=device_id)
    return render_template("partials/search_suggestions.html", recent=recent, trending=trending)
