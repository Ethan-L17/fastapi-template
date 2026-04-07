from fastapi import APIRouter, HTTPException

from app.schemas.item import ItemCreate, ItemResponse

router = APIRouter(prefix="/items", tags=["items"])

fake_db: dict[int, dict] = {}
_counter = 0


@router.get("/", response_model=list[ItemResponse])
async def list_items():
    return [{"id": k, **v} for k, v in fake_db.items()]


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int):
    if item_id not in fake_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, **fake_db[item_id]}


@router.post("/", response_model=ItemResponse, status_code=201)
async def create_item(item: ItemCreate):
    global _counter
    _counter += 1
    fake_db[_counter] = item.model_dump()
    return {"id": _counter, **fake_db[_counter]}


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int):
    if item_id not in fake_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del fake_db[item_id]
