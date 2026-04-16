"""KDS (Kitchen Display System) service."""
from app.db import db
from app.models.kds import KDSTicket
from app.models.order import Order
from app.services import audit_service


class KDSError(Exception):
    """Error in KDS operations."""


# Simple station mapping — maps a category keyword to a KDS station.
DEFAULT_STATION = "grill"
STATION_MAP = {
    "drink": "bar",
    "beverage": "bar",
    "dessert": "pastry",
    "cake": "pastry",
    "salad": "cold",
    "soup": "hot",
    "grill": "grill",
}


def generate_tickets(
    order: Order,
    *,
    stations: list[str] | None = None,
    priority: int = 0,
    eta_minutes: int = 15,
    allergy_flag: bool = False,
    actor_id: int | None = None,
) -> list[KDSTicket]:
    """Generate KDS tickets for an order that has entered 'in_prep'.

    If *stations* is not supplied, a single ticket on the default station
    is created.
    """
    if order is None:
        raise KDSError("order is required")
    if order.status != "in_prep":
        raise KDSError(
            f"KDS tickets can only be generated for orders in 'in_prep' "
            f"(current: '{order.status}')"
        )
    if eta_minutes is not None and eta_minutes < 0:
        raise KDSError("eta_minutes must be >= 0")

    target_stations = stations or [DEFAULT_STATION]
    tickets: list[KDSTicket] = []
    for station in target_stations:
        ticket = KDSTicket(
            order_id=order.id,
            station=station,
            status="pending",
            priority=priority,
            eta_minutes=eta_minutes or 15,
            allergy_flag=allergy_flag,
        )
        db.session.add(ticket)
        tickets.append(ticket)

    db.session.commit()

    for ticket in tickets:
        audit_service.log(
            actor_id=actor_id,
            action="kds_ticket_created",
            resource=f"kds_ticket:{ticket.id}",
            metadata={
                "order_id": order.id,
                "station": ticket.station,
            },
        )
    return tickets


def start_ticket(
    ticket: KDSTicket,
    *,
    actor_id: int | None = None,
) -> KDSTicket:
    if ticket is None:
        raise KDSError("ticket is required")
    if ticket.status != "pending":
        raise KDSError(f"can only start 'pending' tickets (current: '{ticket.status}')")
    ticket.status = "in_progress"
    db.session.commit()
    return ticket


def complete_ticket(
    ticket: KDSTicket,
    *,
    actor_id: int | None = None,
) -> KDSTicket:
    if ticket is None:
        raise KDSError("ticket is required")
    if ticket.status not in ("pending", "in_progress"):
        raise KDSError(
            f"can only complete 'pending' or 'in_progress' tickets "
            f"(current: '{ticket.status}')"
        )
    ticket.status = "done"
    db.session.commit()

    # Write back completion to order event pipeline
    from app.models.order import OrderEvent
    db.session.add(OrderEvent(
        order_id=ticket.order_id,
        status=f"kds_completed:{ticket.station}",
        actor_id=actor_id,
    ))
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="kds_ticket_completed",
        resource=f"kds_ticket:{ticket.id}",
        metadata={"order_id": ticket.order_id, "station": ticket.station},
    )

    # If all tickets for this order are done, auto-advance order to "ready"
    from app.models.kds import KDSTicket as KDS
    pending = KDS.query.filter(
        KDS.order_id == ticket.order_id,
        KDS.status != "done",
    ).count()
    if pending == 0:
        try:
            order = db.session.get(Order, ticket.order_id)
            if order and order.status == "in_prep":
                from app.services import order_service
                order_service.transition(order, "ready", actor_id=actor_id)
        except Exception:
            pass

    return ticket


def get_by_id(ticket_id: int) -> KDSTicket | None:
    return db.session.get(KDSTicket, ticket_id)


def list_tickets(
    *,
    station: str | None = None,
    status: str | None = None,
) -> list[KDSTicket]:
    query = KDSTicket.query
    if station is not None:
        query = query.filter_by(station=station)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(
        KDSTicket.priority.desc(), KDSTicket.created_at
    ).all()


def map_station(category: str) -> str:
    """Map a category keyword to a KDS station name."""
    return STATION_MAP.get((category or "").lower().strip(), DEFAULT_STATION)
