from pydantic import BaseModel, Field
from typing import List


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    sources: List[str]


class SummaryResponse(BaseModel):
    summary: str