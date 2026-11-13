from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product, Stock, Warehouse
from app.schemas import ReceiptInput
from app.service import lock_store, receipt


def seed():
    with SessionLocal.begin() as db:
        lock_store(db)
        if db.scalar(select(Product.id).limit(1)):
            return
        db.add_all(
            [
                Product(id=1, sku="SKU-101", name="Органайзер"),
                Product(id=2, sku="SKU-102", name="Контейнер"),
                Product(id=3, sku="SKU-103", name="Корзина"),
                Warehouse(id=1, name="Север"),
                Warehouse(id=2, name="Юг"),
            ]
        )
        db.flush()
        for product_id, quantities in [(1, [10, 6]), (2, [5, 0]), (3, [0, 4])]:
            for warehouse_id, quantity in enumerate(quantities, 1):
                if quantity:
                    receipt(
                        db, ReceiptInput(product_id=product_id, warehouse_id=warehouse_id, quantity=quantity)
                    )
                else:
                    db.add(Stock(product_id=product_id, warehouse_id=warehouse_id, physical=0, reserved=0))
        # Explicit IDs used for readable test data: advance PostgreSQL sequences.
        from sqlalchemy import text

        for table in ["products", "warehouses"]:
            db.execute(
                text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
            )


if __name__ == "__main__":
    seed()
    print("Демонстрационные данные готовы")
