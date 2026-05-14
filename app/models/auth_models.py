from pydantic import BaseModel, Field


class VerifyCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"