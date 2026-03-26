from fastapi import APIRouter

from app.patterns.registry import get_patterns

router = APIRouter(prefix="/v1", tags=["patterns"])


@router.get("/patterns")
async def list_patterns():
    patterns = get_patterns()
    return {
        "total": len(patterns),
        "patterns": [
            {"name": p.name, "protocol": p.protocol, "class": p.__class__.__name__}
            for p in patterns
        ],
    }
