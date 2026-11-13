from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

PositiveInt = Annotated[StrictInt, Field(gt=0, le=1_000_000)]


class WarehouseInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Укажите название склада")
        return value


class ReceiptInput(BaseModel):
    product_id: PositiveInt
    warehouse_id: PositiveInt
    quantity: PositiveInt


class MovementInput(BaseModel):
    kind: Literal["transfer", "fbs", "fbo"]
    product_id: PositiveInt
    source_id: PositiveInt
    destination_id: PositiveInt | None = None
    quantity: PositiveInt
    destination_label: str = Field(default="", max_length=100)

    @field_validator("destination_label")
    @classmethod
    def clean_label(cls, value):
        return value.strip()
