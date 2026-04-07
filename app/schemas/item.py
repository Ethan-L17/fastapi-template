from pydantic import BaseModel


class ItemBase(BaseModel):
    name: str
    description: str | None = None
    price: float


class ItemCreate(ItemBase):
    pass


class ItemResponse(ItemBase):
    id: int

    class Config:
        from_attributes = True
