"""KDS (Kitchen Display System) views — HTMX polling."""
from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import kds_service
from app.services.kds_service import KDSError

kds_view_bp = Blueprint("kds_view", __name__)


@kds_view_bp.get("/kds")
@permission_required("kds", "view")
def kds_page():
    station = request.args.get("station")
    tickets = kds_service.list_tickets(station=station)
    return render_template(
        "kds.html",
        tickets=tickets,
        station=station,
        user=get_current_user(),
    )


@kds_view_bp.get("/kds/tickets")
@permission_required("kds", "view")
def kds_tickets_partial():
    """HTMX partial: polled every few seconds."""
    station = request.args.get("station")
    status = request.args.get("status")
    tickets = kds_service.list_tickets(station=station, status=status)
    return render_template("partials/kds_tickets.html", tickets=tickets)


@kds_view_bp.post("/kds/<int:ticket_id>/start")
@permission_required("kds", "start")
def do_start(ticket_id: int):
    ticket = kds_service.get_by_id(ticket_id)
    if ticket is None:
        return render_template("partials/kds_error.html", error="ticket not found"), 404
    actor = get_current_user()
    try:
        ticket = kds_service.start_ticket(
            ticket, actor_id=actor.id if actor else None
        )
    except KDSError as exc:
        return render_template("partials/kds_error.html", error=str(exc)), 400
    return render_template("partials/kds_ticket_row.html", ticket=ticket)


@kds_view_bp.post("/kds/<int:ticket_id>/complete")
@permission_required("kds", "complete")
def do_complete(ticket_id: int):
    ticket = kds_service.get_by_id(ticket_id)
    if ticket is None:
        return render_template("partials/kds_error.html", error="ticket not found"), 404
    actor = get_current_user()
    try:
        ticket = kds_service.complete_ticket(
            ticket, actor_id=actor.id if actor else None
        )
    except KDSError as exc:
        return render_template("partials/kds_error.html", error=str(exc)), 400
    return render_template("partials/kds_ticket_row.html", ticket=ticket)
