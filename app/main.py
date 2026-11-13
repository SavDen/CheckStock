import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app import service
from app.db import SessionLocal
from app.models import Event, Idempotency, Movement, Product, Stock, Store, Warehouse
from app.schemas import MovementInput, ReceiptInput, WarehouseInput

ROOT = Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    if os.getenv("SEED_DEMO", "true").lower() == "true":
        from app.seed import seed

        seed()
    yield


app = FastAPI(
    title="CheckStock",
    version="1.0.0",
    lifespan=lifespan,
    description="Складской прототип: остатки, перемещения, FBS и FBO. Один магазин.",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
Key = Annotated[
    UUID, Header(alias="Idempotency-Key", description="Новый UUID для новой команды; тот же UUID для повтора")
]


@app.exception_handler(service.DomainError)
async def domain_error(request, exc):
    return JSONResponse(
        status_code=exc.status, content={"error": exc.code, "message": exc.message, "details": exc.details}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Проверьте поля: количество — целое число от 1 до 1 000 000; для изменения нужен Idempotency-Key (UUID).",
            "details": {"fields": [".".join(map(str, e["loc"])) for e in exc.errors()]},
        },
    )


def mutate(key, command, payload, operation):
    fingerprint = hashlib.sha256(
        json.dumps([command, payload], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    with SessionLocal.begin() as db:
        service.lock_store(db)
        existing = db.get(Idempotency, str(key))
        if existing:
            if existing.fingerprint != fingerprint:
                raise service.DomainError(
                    "Этот ключ уже использован для другой команды. Создайте новый ключ.",
                    "idempotency_conflict",
                )
            return existing.response
        result = operation(db)
        db.add(Idempotency(key=str(key), fingerprint=fingerprint, response=result))
        return result


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "templates" / "index.html")


@app.get("/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "postgresql"}


@app.get("/api/snapshot")
def snapshot():
    with SessionLocal.begin() as db:
        # Shared row lock keeps all sections of the response in the same business state.
        service.lock_store(db, read=True)
        warehouses = db.scalars(select(Warehouse).order_by(Warehouse.id)).all()
        products = db.scalars(select(Product).order_by(Product.id)).all()
        stocks = db.scalars(select(Stock)).all()
        movements = db.scalars(select(Movement).order_by(Movement.created_at.desc(), Movement.id)).all()
        events = db.scalars(select(Event).order_by(Event.id.desc())).all()
        return {
            "store": db.get(Store, 1).name,
            "warehouses": [{"id": w.id, "name": w.name, "archived": w.archived} for w in warehouses],
            "products": [{"id": p.id, "sku": p.sku, "name": p.name} for p in products],
            "stocks": [
                {
                    "product_id": b.product_id,
                    "warehouse_id": b.warehouse_id,
                    "physical": b.physical,
                    "reserved": b.reserved,
                    "available": b.physical - b.reserved,
                }
                for b in stocks
            ],
            "movements": [
                {
                    "id": m.id,
                    "kind": m.kind,
                    "status": m.status,
                    "product_id": m.product_id,
                    "source_id": m.source_id,
                    "destination_id": m.destination_id,
                    "destination_label": m.destination_label,
                    "quantity": m.quantity,
                    "created_at": m.created_at.isoformat(),
                }
                for m in movements
            ],
            "events": [
                {
                    "id": e.id,
                    "action": e.action,
                    "product_id": e.product_id,
                    "quantity": e.quantity,
                    "source_id": e.source_id,
                    "destination_id": e.destination_id,
                    "source_label": e.source_label,
                    "destination_label": e.destination_label,
                    "movement_id": e.movement_id,
                    "physical_delta": e.physical_delta,
                    "reserved_delta": e.reserved_delta,
                    "note": e.note,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }


@app.post("/api/warehouses", status_code=201)
def create_warehouse(data: WarehouseInput, key: Key):
    return mutate(
        key, "warehouse.create", data.model_dump(), lambda db: service.create_warehouse(db, data.name)
    )


@app.patch("/api/warehouses/{ident}")
def rename_warehouse(ident: int, data: WarehouseInput, key: Key):
    return mutate(
        key,
        f"warehouse.rename:{ident}",
        data.model_dump(),
        lambda db: service.rename_warehouse(db, ident, data.name),
    )


@app.delete("/api/warehouses/{ident}")
def delete_warehouse(ident: int, key: Key):
    return mutate(key, f"warehouse.archive:{ident}", {}, lambda db: service.archive_warehouse(db, ident))


@app.post("/api/receipts", status_code=201)
def receipt(data: ReceiptInput, key: Key):
    return mutate(key, "receipt", data.model_dump(), lambda db: service.receipt(db, data))


@app.post("/api/movements", status_code=201)
def movement(data: MovementInput, key: Key):
    return mutate(key, "movement", data.model_dump(), lambda db: service.create_movement(db, data))


@app.post("/api/movements/{ident}/{action}")
def transition(ident: str, action: Literal["send", "receive", "cancel"], key: Key):
    return mutate(key, f"movement.{action}:{ident}", {}, lambda db: service.transition(db, ident, action))
