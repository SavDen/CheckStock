"""All stock mutations run inside one transaction with a store-level PostgreSQL row lock."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Movement, Product, Stock, Store, Warehouse


class DomainError(Exception):
    def __init__(self, message: str, code="invalid_operation", details=None, status=409):
        self.message, self.code, self.details, self.status = message, code, details or {}, status


def lock_store(db: Session, *, read=False):
    store = db.scalar(select(Store).where(Store.id == 1).with_for_update(read=read))
    if store is None:
        raise DomainError("Магазин ещё не создан. Выполните миграции и загрузку данных.", status=503)


def warehouse(db, ident, *, active=False):
    item = db.get(Warehouse, ident)
    if item is None:
        raise DomainError("Склад не найден", "not_found", status=404)
    if active and item.archived:
        raise DomainError(
            "Склад удалён. Можно завершить старые операции или вывести остаток, но нельзя создавать новые поступления.",
            "archived_warehouse",
        )
    return item


def product(db, ident):
    item = db.get(Product, ident)
    if item is None:
        raise DomainError("Товар не найден", "not_found", status=404)
    return item


def stock(db, product_id, warehouse_id):
    item = db.scalar(select(Stock).where(Stock.product_id == product_id, Stock.warehouse_id == warehouse_id))
    if item is None:
        item = Stock(product_id=product_id, warehouse_id=warehouse_id, physical=0, reserved=0)
        db.add(item)
        db.flush()
    return item


def event(
    db,
    action,
    *,
    item=None,
    quantity=0,
    source=None,
    destination=None,
    label="",
    movement=None,
    physical_delta=0,
    reserved_delta=0,
    note="",
):
    db.add(
        Event(
            action=action,
            product_id=item.id if item else None,
            quantity=quantity,
            source_id=source.id if source else None,
            destination_id=destination.id if destination else None,
            source_label=source.name if source else "Поставщик" if action == "receipt" else "",
            destination_label=destination.name if destination else label,
            movement_id=movement.id if movement else None,
            physical_delta=physical_delta,
            reserved_delta=reserved_delta,
            note=note,
        )
    )


def require_available(db, balance, quantity):
    available = balance.physical - balance.reserved
    if quantity > available:
        balances = db.scalars(select(Stock).where(Stock.product_id == balance.product_id)).all()
        alternatives = []
        for b in balances:
            w = warehouse(db, b.warehouse_id)
            if b.warehouse_id != balance.warehouse_id and b.physical > b.reserved:
                alternatives.append(
                    {
                        "warehouse_id": w.id,
                        "name": w.name,
                        "available": b.physical - b.reserved,
                        "archived": w.archived,
                    }
                )
        raise DomainError(
            f"На выбранном ФФ доступно {available} шт., требуется {quantity}. Выберите другой склад или сначала оформите перемещение.",
            "insufficient_stock",
            {"available": available, "requested": quantity, "alternatives": alternatives},
        )


def create_warehouse(db, name):
    if db.scalar(select(Warehouse).where(Warehouse.name == name, Warehouse.archived.is_(False))):
        raise DomainError("Действующий склад с таким названием уже существует", "duplicate_name")
    w = Warehouse(name=name)
    db.add(w)
    db.flush()
    event(db, "warehouse_created", destination=w, note="Создан склад")
    return {"id": w.id, "name": w.name}


def rename_warehouse(db, ident, name):
    w = warehouse(db, ident, active=True)
    if db.scalar(
        select(Warehouse).where(Warehouse.name == name, Warehouse.id != ident, Warehouse.archived.is_(False))
    ):
        raise DomainError("Действующий склад с таким названием уже существует", "duplicate_name")
    old = w.name
    w.name = name
    event(db, "warehouse_renamed", destination=w, note=f"{old} → {name}")
    return {"id": w.id, "name": w.name}


def archive_warehouse(db, ident):
    w = warehouse(db, ident)
    if not w.archived:
        w.archived = True
        event(db, "warehouse_archived", source=w, note="Склад удалён из активных; товар и история сохранены")
    return {"id": w.id, "archived": True}


def receipt(db, data):
    p, w = product(db, data.product_id), warehouse(db, data.warehouse_id, active=True)
    balance = stock(db, p.id, w.id)
    balance.physical += data.quantity
    event(db, "receipt", item=p, quantity=data.quantity, destination=w, physical_delta=data.quantity)
    return {
        "warehouse_id": w.id,
        "product_id": p.id,
        "physical": balance.physical,
        "reserved": balance.reserved,
    }


def create_movement(db, data):
    p = product(db, data.product_id)
    # Evacuation transfers may leave archived FFs; new sales may not.
    source = warehouse(db, data.source_id, active=data.kind != "transfer")
    destination = None
    if data.kind == "transfer":
        if not data.destination_id or data.destination_id == source.id:
            raise DomainError("Выберите другой склад назначения", "invalid_destination")
        destination = warehouse(db, data.destination_id, active=True)
    elif data.destination_id is not None:
        raise DomainError("Для FBS/FBO укажите получателя, а не склад ФФ", "invalid_destination")
    balance = stock(db, p.id, source.id)
    require_available(db, balance, data.quantity)
    label = (
        destination.name
        if destination
        else data.destination_label or ("Клиент FBS" if data.kind == "fbs" else "Маркетплейс FBO")
    )
    m = Movement(
        kind=data.kind,
        status="reserved" if data.kind == "fbs" else "transit",
        product_id=p.id,
        source_id=source.id,
        destination_id=destination.id if destination else None,
        destination_label=label,
        quantity=data.quantity,
    )
    db.add(m)
    db.flush()
    if data.kind == "fbs":
        balance.reserved += data.quantity
        action, pd, rd = "fbs_reserved", 0, data.quantity
    else:
        balance.physical -= data.quantity
        action, pd, rd = f"{data.kind}_sent", -data.quantity, 0
    event(
        db,
        action,
        item=p,
        quantity=data.quantity,
        source=source,
        destination=destination,
        label=label,
        movement=m,
        physical_delta=pd,
        reserved_delta=rd,
    )
    return {"id": m.id, "status": m.status}


def transition(db, ident, action):
    m = db.get(Movement, ident)
    if m is None:
        raise DomainError("Операция не найдена", "not_found", status=404)
    p, source = product(db, m.product_id), warehouse(db, m.source_id)
    destination = warehouse(db, m.destination_id) if m.destination_id else None
    balance = stock(db, p.id, source.id)
    pd = rd = 0
    # Terminal repetitions are harmless even with a different request key.
    if action == "send" and m.kind == "fbs" and m.status in ("transit", "completed"):
        return {"id": m.id, "status": m.status, "repeated": True}
    if action == "receive" and m.status == "completed":
        return {"id": m.id, "status": m.status, "repeated": True}
    if action == "cancel" and m.status == "cancelled":
        return {"id": m.id, "status": m.status, "repeated": True}
    if action == "send" and m.kind == "fbs" and m.status == "reserved":
        balance.reserved -= m.quantity
        balance.physical -= m.quantity
        pd = rd = -m.quantity
        m.status, event_action = "transit", "fbs_sent"
    elif action == "cancel" and m.kind == "fbs" and m.status == "reserved":
        balance.reserved -= m.quantity
        rd = -m.quantity
        m.status, event_action = "cancelled", "fbs_cancelled"
    elif action == "receive" and m.status == "transit":
        if m.kind == "transfer":
            # A shipment sent before destination deletion still arrives there, visibly in archive.
            stock(db, p.id, destination.id).physical += m.quantity
            pd = m.quantity
        m.status, event_action = "completed", f"{m.kind}_received"
    else:
        raise DomainError("Действие недоступно для текущего статуса операции", "invalid_transition")
    event(
        db,
        event_action,
        item=p,
        quantity=m.quantity,
        source=source,
        destination=destination,
        label=m.destination_label,
        movement=m,
        physical_delta=pd,
        reserved_delta=rd,
    )
    return {"id": m.id, "status": m.status}
