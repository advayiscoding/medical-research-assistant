"""Research history — the user's past searches. Chat history already lives at
GET /api/chat/sessions; this covers the search side of the History page."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import SearchHistory

router = APIRouter(prefix="/history", tags=["history"])


class SearchHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    result_count: int
    created_at: datetime


@router.get("/searches", response_model=list[SearchHistoryRead])
async def list_searches(user: CurrentUserDep, db: DbDep) -> list[SearchHistoryRead]:
    result = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(50)
    )
    return [SearchHistoryRead.model_validate(r) for r in result.scalars().all()]
