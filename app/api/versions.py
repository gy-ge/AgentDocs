from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["versions"])


@router.get("/health")
def health_check():
    return {"ok": True, "data": {"status": "healthy"}}
