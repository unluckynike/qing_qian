"""签文库接口:列表与单签详情。"""
from fastapi import APIRouter, HTTPException

from ..services.signstore import store

router = APIRouter(tags=["signs"])


@router.get("/signs")
def list_signs() -> dict:
    return {
        "meta": {
            "system": store.meta["system"],
            "temple": store.meta["temple"],
            "total": store.total,
            "source": store.meta["source"],
        },
        "signs": store.list_brief(),
    }


@router.get("/signs/{no}")
def get_sign(no: int) -> dict:
    sign = store.get(no)
    if sign is None:
        raise HTTPException(status_code=404, detail=f"第 {no} 签不存在")
    return sign
