"""系统健康检查 API。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """系统健康检查（应用运行中即返回正常）。"""
    from src.scheduler.health import get_system_health
    from src.scheduler.scheduler import get_scheduler_manager

    manager = get_scheduler_manager()
    health = await get_system_health(manager)
    return health
