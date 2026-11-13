# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Python 3.12, FastAPI, PostgreSQL — required by the assignment. SQLAlchemy, Alembic, plain HTML/CSS/JavaScript chosen for a compact, inspectable prototype.

## Users
Warehouse manager for one store with multiple fulfillment warehouses.

## Product Purpose
Show the location and availability of every SKU, including reservations and goods in transit. Every accepted operation must preserve inventory consistency.

## Capabilities and Constraints
Receipts, FF transfers, FBS reserve/send/cancel/deliver, FBO send/receive, warehouse create/rename/archive, immutable operation history. Archived warehouses retain stock and existing obligations. No marketplace integration or forecast module in this assignment. Demo application is local, without authentication.

## Evidence on Hand
Assignment: sources/test-assignment.pdf. Project context: sources/project.pdf. Exactly three supplied products, two FFs, one store, total starting inventory 25 units. No real customer data.

## Product Principles
- Every unit has a visible location.
- Available stock excludes reservations.
- Failed or repeated requests cannot silently change stock.
- Errors explain a recovery action.
