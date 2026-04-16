"""Search service — keyword/fuzzy, trending, recent, with synonym support."""
import hashlib
import re
import unicodedata

from sqlalchemy import func, or_

from app.core.encryption import decrypt
from app.db import db
from app.models.catalog import CatalogItem
from app.models.member import Member
from app.models.order import Order
from app.models.search import SearchLog, SearchTrend
from app.services import audit_service


class SearchError(Exception):
    """Error in search operations."""


# Synonym / alias map for fuzzy matching
SYNONYMS: dict[str, list[str]] = {
    "photo": ["photograph", "picture", "image", "portrait"],
    "gift": ["present", "souvenir", "memento"],
    "animal": ["wildlife", "creature", "species"],
    "bird": ["avian", "fowl"],
    "drink": ["beverage", "refreshment"],
}

# Pinyin-to-English map for wildlife/park-relevant terms.
# Allows Chinese-speaking visitors/staff to search using pinyin romanization.
PINYIN_MAP: dict[str, list[str]] = {
    "niao": ["bird", "avian"],
    "laohu": ["tiger"],
    "daxiongmao": ["panda", "giant panda"],
    "xiongmao": ["panda"],
    "she": ["snake", "serpent"],
    "yu": ["fish"],
    "hou": ["monkey"],
    "houzi": ["monkey"],
    "da": ["large", "big"],
    "xiao": ["small", "little"],
    "xiong": ["bear"],
    "lu": ["deer"],
    "lang": ["wolf"],
    "shi": ["lion"],
    "shizi": ["lion"],
    "ma": ["horse"],
    "zhu": ["pig"],
    "ji": ["chicken"],
    "ya": ["duck"],
    "e": ["goose"],
    "gou": ["dog"],
    "mao": ["cat"],
    "yang": ["sheep", "goat"],
    "niu": ["cow", "cattle"],
    "tu": ["rabbit"],
    "tuzi": ["rabbit"],
    "long": ["dragon"],
    "he": ["crane"],
    "ying": ["eagle", "hawk"],
    "hu": ["lake"],
    "shan": ["mountain"],
    "senlin": ["forest"],
    "haiyang": ["ocean"],
    "shamo": ["desert"],
    "caoyuan": ["savanna", "grassland"],
    "shipin": ["food"],
    "yinliao": ["drink", "beverage"],
    "liwu": ["gift", "present"],
    "zhaopian": ["photo", "photograph"],
    "tupian": ["picture", "image"],
    "dongwu": ["animal", "wildlife"],
    "zhiwu": ["plant"],
    "baohu": ["protection", "conservation"],
    "binwei": ["endangered"],
}


def _clean(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize(text: str) -> str:
    """Normalize text: strip accents and lowercase for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _expand_pinyin(query: str) -> list[str]:
    """Expand a pinyin query to English equivalents."""
    q_lower = query.lower().strip()
    matches = PINYIN_MAP.get(q_lower, [])
    return list(matches)


def _expand_synonyms(query: str) -> list[str]:
    """Expand a query with synonyms and pinyin transliterations."""
    q_lower = query.lower().strip()
    variants = [q_lower]

    # Synonym expansion
    for key, syns in SYNONYMS.items():
        if q_lower == key or q_lower in syns:
            variants.extend([key] + syns)

    # Pinyin expansion
    pinyin_matches = _expand_pinyin(q_lower)
    if pinyin_matches:
        variants.extend(pinyin_matches)
        # Also expand synonym chains for pinyin-resolved terms
        for pm in pinyin_matches:
            for key, syns in SYNONYMS.items():
                if pm == key or pm in syns:
                    variants.extend([key] + syns)

    return list(set(variants))


def _highlight(text: str, query: str) -> str:
    """Wrap matched portions in <mark> tags for highlighted display.

    HTML-escapes text first to prevent XSS if text or query contain markup.
    """
    from markupsafe import escape

    if not text or not query:
        return str(escape(text or ""))
    escaped_text = str(escape(text))
    escaped_q = str(escape(query))
    pattern = re.compile(re.escape(escaped_q), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group()}</mark>", escaped_text)


def perform_search(
    query: str,
    *,
    category: str | None = None,
    tier: str | None = None,
    taxonomy: str | None = None,
    region: str | None = None,
    habitat: str | None = None,
    size_range: str | None = None,
    protection_level: str | None = None,
    user_id: int | None = None,
    actor_id: int | None = None,
    is_admin: bool = False,
    actor=None,
    device_id: str | None = None,
) -> dict:
    """Run a keyword search with fuzzy/synonym matching.

    Searches across members (name, phone, member_id), orders (id, status),
    and catalog items (name, category) with filter support.
    Returns ``{"members": [...], "orders": [...], "catalog_items": [...], "query_expanded": [...]}``.
    Member PII is masked for non-admin callers.
    Results include hit-highlighted name fields.
    """
    q = _clean(query)
    if not q:
        raise SearchError("query must not be empty")

    # Expand query with synonyms for fuzzy matching
    variants = _expand_synonyms(q)
    q_normalized = _normalize(q)

    # Build LIKE clauses for all variants
    like_clauses = []
    for v in variants:
        like = f"%{v}%"
        like_clauses.append(Member.name.ilike(like))
        like_clauses.append(Member.member_id.ilike(like))

    # Member search — name and member_id are not encrypted, so LIKE works.
    member_query = Member.query.filter(or_(*like_clauses))
    if tier:
        member_query = member_query.filter(Member.tier.ilike(f"%{tier}%"))
    members = list(member_query.limit(50).all())

    # Scan decrypted phone numbers for partial matches (fuzzy)
    seen_ids = {m.id for m in members}
    for m in Member.query.all():
        if m.id not in seen_ids:
            decrypted = decrypt(m.phone_number or "")
            if decrypted and q_normalized in _normalize(decrypted):
                members.append(m)
                if len(members) >= 50:
                    break

    # Order search — gated by order:view permission + object-level access.
    # Users with search:perform but no order:view (e.g. photographers) see
    # no order results; others see only orders check_access allows.
    orders: list[Order] = []
    if actor is not None:
        from app.core.rbac import has_permission
        from app.services.order_service import OrderAccessDenied, check_access

        if has_permission(actor, "order", "view"):
            order_like_clauses = [Order.id == _safe_int(q)]
            for v in variants:
                order_like_clauses.append(Order.status.ilike(f"%{v}%"))
            candidates = Order.query.filter(or_(*order_like_clauses)).limit(50).all()
            for o in candidates:
                try:
                    check_access(o, actor.id)
                    orders.append(o)
                except OrderAccessDenied:
                    continue

    # Catalog item search — LIKE on name, description, and pinyin_name
    catalog_like_clauses = []
    for v in variants:
        catalog_like_clauses.append(CatalogItem.name.ilike(f"%{v}%"))
        catalog_like_clauses.append(CatalogItem.description.ilike(f"%{v}%"))
        catalog_like_clauses.append(CatalogItem.pinyin_name.ilike(f"%{v}%"))
    catalog_query = CatalogItem.query.filter(
        CatalogItem.active.is_(True),
        or_(*catalog_like_clauses),
    )
    if category:
        catalog_query = catalog_query.filter(CatalogItem.category.ilike(f"%{category}%"))
    if taxonomy:
        catalog_query = catalog_query.filter(CatalogItem.taxonomy.ilike(f"%{taxonomy}%"))
    if region:
        catalog_query = catalog_query.filter(CatalogItem.region.ilike(f"%{region}%"))
    if habitat:
        catalog_query = catalog_query.filter(CatalogItem.habitat.ilike(f"%{habitat}%"))
    if size_range:
        catalog_query = catalog_query.filter(CatalogItem.size_range.ilike(f"%{size_range}%"))
    if protection_level:
        catalog_query = catalog_query.filter(CatalogItem.protection_level.ilike(f"%{protection_level}%"))
    catalog_items = catalog_query.limit(50).all()

    # Record the search
    _record_search(q, user_id=user_id, device_id=device_id)

    audit_service.log(
        actor_id=actor_id,
        action="search_performed",
        resource="search",
        metadata={
            "query_hash": hashlib.sha256(q.encode()).hexdigest()[:16],
            "member_hits": len(members),
            "order_hits": len(orders),
            "catalog_hits": len(catalog_items),
        },
    )

    from app.services import permission_service
    from app.services.member_service import member_to_dict

    allowed_member_fields = permission_service.get_allowed_fields(
        actor, "member", "view",
    ) if actor else set()

    # Build highlighted results
    member_results = []
    for m in members:
        d = member_to_dict(m, is_admin=is_admin, allowed_fields=allowed_member_fields)
        d["name_highlighted"] = _highlight(d["name"], q)
        member_results.append(d)

    order_results = []
    for o in orders:
        d = o.to_dict()
        d["status_highlighted"] = _highlight(d["status"], q)
        order_results.append(d)

    catalog_results = []
    for item in catalog_items:
        d = item.to_dict()
        d["name_highlighted"] = _highlight(d["name"], q)
        catalog_results.append(d)

    return {
        "members": member_results,
        "orders": order_results,
        "catalog_items": catalog_results,
        "query_expanded": variants if len(variants) > 1 else [],
    }


def _safe_int(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return -1


def _redact_term(term: str) -> str:
    """Redact PII from search terms. Hash phone-like queries."""
    stripped = term.strip()
    if stripped.isdigit() and len(stripped) >= 7:
        return f"phone:{hashlib.sha256(stripped.encode()).hexdigest()[:16]}"
    return stripped.lower()


def _record_search(query: str, *, user_id: int | None = None, device_id: str | None = None) -> None:
    """Append to SearchLog and increment SearchTrend."""
    normalized = _redact_term(query)
    db.session.add(SearchLog(term=normalized, user_id=user_id, device_id=device_id))

    trend = SearchTrend.query.filter_by(term=normalized).first()
    if trend is None:
        trend = SearchTrend(term=normalized, count=1)
        db.session.add(trend)
    else:
        trend.count += 1
    db.session.commit()


def get_trending(limit: int = 10, *, device_id: str | None = None) -> list[SearchTrend]:
    """Return trending terms. When device_id is given, scope to that device's history."""
    if device_id is not None:
        from sqlalchemy import func
        subq = (
            db.session.query(SearchLog.term, func.count(SearchLog.id).label("cnt"))
            .filter(SearchLog.device_id == device_id)
            .group_by(SearchLog.term)
            .order_by(func.count(SearchLog.id).desc())
            .limit(limit)
            .subquery()
        )
        rows = db.session.query(subq).all()
        return [SearchTrend(term=r.term, count=r.cnt) for r in rows]
    return (
        SearchTrend.query
        .order_by(SearchTrend.count.desc())
        .limit(limit)
        .all()
    )


def get_recent(*, user_id: int | None = None, device_id: str | None = None, limit: int = 10) -> list[SearchLog]:
    query = SearchLog.query
    if device_id is not None:
        query = query.filter(SearchLog.device_id == device_id)
    elif user_id is not None:
        query = query.filter(SearchLog.user_id == user_id)
    return query.order_by(SearchLog.created_at.desc()).limit(limit).all()
