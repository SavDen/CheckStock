from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.main import app


def write(client, path, data=None, method="POST", key=None):
    return client.request(method, path, json=data, headers={"Idempotency-Key": str(key or uuid4())})


def snapshot(client):
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    return response.json()


def balance(client, product=1, warehouse=1):
    return next(
        b for b in snapshot(client)["stocks"] if b["product_id"] == product and b["warehouse_id"] == warehouse
    )


def movement(client, kind="fbs", quantity=3, source=1, destination=None, product=1):
    body = {"kind": kind, "quantity": quantity, "source_id": source, "product_id": product}
    if destination:
        body["destination_id"] = destination
    return write(client, "/api/movements", body)


def transition(client, ident, action):
    return write(client, f"/api/movements/{ident}/{action}")


def assert_conserved(client):
    data = snapshot(client)
    for product in data["products"]:
        pid = product["id"]
        incoming = sum(
            e["quantity"] for e in data["events"] if e["action"] == "receipt" and e["product_id"] == pid
        )
        physical = sum(s["physical"] for s in data["stocks"] if s["product_id"] == pid)
        transit = sum(
            m["quantity"] for m in data["movements"] if m["product_id"] == pid and m["status"] == "transit"
        )
        external = sum(
            m["quantity"]
            for m in data["movements"]
            if m["product_id"] == pid and m["status"] == "completed" and m["kind"] in ("fbo", "fbs")
        )
        assert incoming == physical + transit + external
        for stock in [s for s in data["stocks"] if s["product_id"] == pid]:
            reserved = sum(
                m["quantity"]
                for m in data["movements"]
                if m["product_id"] == pid
                and m["source_id"] == stock["warehouse_id"]
                and m["status"] == "reserved"
            )
            assert 0 <= stock["reserved"] == reserved <= stock["physical"]
            assert stock["available"] == stock["physical"] - stock["reserved"]


def test_initial_data_and_seed_is_repeatable(client):
    from app.seed import seed

    seed()
    data = snapshot(client)
    assert len(data["products"]) == 3 and len(data["warehouses"]) == 2
    assert sum(s["physical"] for s in data["stocks"]) == 25
    assert len(data["events"]) == 4
    assert_conserved(client)


def test_receipt_idempotent_and_key_conflict(client):
    key = uuid4()
    body = {"product_id": 1, "warehouse_id": 1, "quantity": 5}
    first = write(client, "/api/receipts", body, key=key)
    assert first.status_code == 201
    assert write(client, "/api/receipts", body, key=key).json() == first.json()
    assert balance(client)["physical"] == 15
    assert write(client, "/api/receipts", {**body, "quantity": 6}, key=key).status_code == 409
    assert_conserved(client)


def test_fbs_reserve_cancel_and_send(client):
    ident = movement(client).json()["id"]
    b = balance(client)
    assert (b["physical"], b["available"], b["reserved"]) == (10, 7, 3)
    assert_conserved(client)
    assert transition(client, ident, "cancel").status_code == 200
    assert transition(client, ident, "cancel").json()["repeated"]
    assert balance(client)["available"] == 10
    ident = movement(client).json()["id"]
    assert transition(client, ident, "send").status_code == 200
    count = len(snapshot(client)["events"])
    assert transition(client, ident, "send").json()["repeated"]
    assert balance(client)["physical"] == 7 and balance(client)["reserved"] == 0
    assert len(snapshot(client)["events"]) == count
    assert_conserved(client)
    assert transition(client, ident, "receive").status_code == 200
    assert transition(client, ident, "receive").json()["repeated"]
    assert_conserved(client)


def test_transfer_in_transit_then_receipt(client):
    ident = movement(client, "transfer", 4, destination=2).json()["id"]
    assert balance(client)["physical"] == 6
    assert balance(client, warehouse=2)["physical"] == 6
    assert_conserved(client)
    assert transition(client, ident, "receive").status_code == 200
    assert transition(client, ident, "receive").json()["repeated"]
    assert balance(client, warehouse=2)["physical"] == 10
    assert_conserved(client)


def test_fbo_departure_and_receipt(client):
    ident = movement(client, "fbo", 6).json()["id"]
    assert balance(client)["physical"] == 4
    assert_conserved(client)
    assert transition(client, ident, "receive").status_code == 200
    assert balance(client)["physical"] == 4
    assert_conserved(client)


def test_local_shortage_with_enough_total(client):
    response = movement(client, "fbo", 12)
    assert response.status_code == 409
    assert response.json()["error"] == "insufficient_stock"
    assert response.json()["details"]["alternatives"][0]["available"] == 6
    assert balance(client)["physical"] == 10
    assert not snapshot(client)["movements"]
    assert_conserved(client)


def test_reserves_block_other_operations(client):
    movement(client, quantity=8)
    assert movement(client, "fbo", 3).status_code == 409
    assert movement(client, "transfer", 3, destination=2).status_code == 409
    assert movement(client, quantity=3).status_code == 409
    assert_conserved(client)


def test_archive_keeps_stock_reservations_history_and_allows_evacuation(client):
    ident = movement(client).json()["id"]
    before = snapshot(client)
    assert write(client, "/api/warehouses/1", method="DELETE").status_code == 200
    after = snapshot(client)
    assert before["stocks"] == after["stocks"]
    assert after["warehouses"][0]["archived"]
    assert len(after["events"]) == len(before["events"]) + 1
    assert (
        write(client, "/api/receipts", {"product_id": 1, "warehouse_id": 1, "quantity": 1}).status_code == 409
    )
    assert movement(client, "fbs", 1).status_code == 409
    assert transition(client, ident, "send").status_code == 200
    transfer_id = movement(client, "transfer", 7, destination=2).json()["id"]
    assert transition(client, transfer_id, "receive").status_code == 200
    assert balance(client)["physical"] == 0
    assert_conserved(client)


def test_destination_archived_while_transfer_in_transit(client):
    ident = movement(client, "transfer", 4, destination=2).json()["id"]
    write(client, "/api/warehouses/2", method="DELETE")
    assert transition(client, ident, "receive").status_code == 200
    assert balance(client, warehouse=2)["physical"] == 10
    assert movement(client, "transfer", 1, destination=2).status_code == 409
    assert_conserved(client)


def test_warehouse_create_rename_and_frozen_history_labels(client):
    response = write(client, "/api/warehouses", {"name": "Восток"})
    assert response.status_code == 201
    ident = response.json()["id"]
    assert ident > 2
    assert write(client, f"/api/warehouses/{ident}", {"name": "Север"}, method="PATCH").status_code == 409
    assert write(client, "/api/warehouses/1", {"name": "Северный"}, method="PATCH").status_code == 200
    assert any(
        e["destination_label"] == "Север" for e in snapshot(client)["events"] if e["action"] == "receipt"
    )
    assert write(client, "/api/warehouses", {"name": "Северный"}).status_code == 409


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "3", True, 1000001])
def test_invalid_quantity_is_rejected(client, quantity):
    assert movement(client, quantity=quantity).status_code == 422
    assert_conserved(client)


def test_missing_key_and_invalid_reference(client):
    assert client.post("/api/warehouses", json={"name": "Запад"}).status_code == 422
    assert write(client, "/api/warehouses", {"name": "   "}).status_code == 422
    assert movement(client, product=999).status_code == 404
    assert movement(client, "transfer", destination=1).status_code == 409
    assert movement(client, "transfer").status_code == 409


def test_invalid_transition_rolls_back(client):
    ident = movement(client).json()["id"]
    count = len(snapshot(client)["events"])
    assert transition(client, ident, "receive").status_code == 409
    assert len(snapshot(client)["events"]) == count
    transition(client, ident, "send")
    assert transition(client, ident, "cancel").status_code == 409
    assert_conserved(client)


def test_simultaneous_reservations_never_oversell(client):
    def reserve(_):
        with TestClient(app) as other:
            return movement(other, quantity=7).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert sorted(results) == [201, 409]
    assert balance(client)["reserved"] == 7
    assert_conserved(client)


def test_simultaneous_same_request_applies_once(client):
    key = uuid4()
    body = {"product_id": 1, "warehouse_id": 1, "quantity": 5}

    def receive(_):
        with TestClient(app) as other:
            return write(other, "/api/receipts", body, key=key).json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(receive, range(4)))
    assert all(result == results[0] for result in results)
    assert balance(client)["physical"] == 15
    assert_conserved(client)


def test_simultaneous_double_confirmation_applies_once(client):
    ident = movement(client, "transfer", 4, destination=2).json()["id"]

    def receive(_):
        with TestClient(app) as other:
            return transition(other, ident, "receive").status_code

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(receive, range(3))) == [200, 200, 200]
    assert balance(client, warehouse=2)["physical"] == 10
    assert_conserved(client)


def test_database_rejects_negative_balance(client):
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.execute(text("UPDATE stocks SET physical=-1 WHERE product_id=1 AND warehouse_id=1"))
    assert balance(client)["physical"] == 10


def test_health_ui_and_api_documentation(client):
    assert client.get("/health").json()["database"] == "postgresql"
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "CheckStock"
