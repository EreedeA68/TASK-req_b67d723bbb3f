"""KDS JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import kds_service
from app.services.kds_service import KDSError

kds_api_bp = Blueprint("kds_api", __name__)


@kds_api_bp.get("")
@permission_required("kds", "view")
def list_tickets():
    station = request.args.get("station")
    status = request.args.get("status")
    tickets = kds_service.list_tickets(station=station, status=status)
    return jsonify({"results": [t.to_dict() for t in tickets]})


@kds_api_bp.post("/<int:ticket_id>/start")
@permission_required("kds", "start")
def start_ticket(ticket_id: int):
    ticket = kds_service.get_by_id(ticket_id)
    if ticket is None:
        return jsonify({"error": "ticket not found"}), 404
    actor = get_current_user()
    try:
        ticket = kds_service.start_ticket(
            ticket, actor_id=actor.id if actor else None
        )
    except KDSError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(ticket.to_dict())


@kds_api_bp.post("/<int:ticket_id>/complete")
@permission_required("kds", "complete")
def complete_ticket(ticket_id: int):
    ticket = kds_service.get_by_id(ticket_id)
    if ticket is None:
        return jsonify({"error": "ticket not found"}), 404
    actor = get_current_user()
    try:
        ticket = kds_service.complete_ticket(
            ticket, actor_id=actor.id if actor else None
        )
    except KDSError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(ticket.to_dict())
