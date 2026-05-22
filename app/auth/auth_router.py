
from typing import Optional
from urllib import response
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DBSession

from app.auth.auth_service import PatientAuthService, PhysicianAuthService, create_refresh_token, create_access_token, decode_token
from app.models.database import get_db
from app.core.config import config
router = APIRouter(prefix="/auth", tags=["Auth"])

patient_auth   = PatientAuthService()
physician_auth = PhysicianAuthService()


class PatientRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    practice_code: str          # e.g. "123456" from config
    date_of_birth: Optional[str] = None   # "YYYY-MM-DD"
    phone: Optional[str] = None


class PhysicianRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    practice_id: str
    title: Optional[str] = None       # "Dr.", "Prof. Dr."
    specialty: Optional[str] = None   # "Allgemeinmedizin"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

def _set_auth_cookies(response: Response, token_data: dict) -> None:
    """Set access + refresh tokens as HTTP-only cookies."""
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
 
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        max_age=60 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 7,   # 7 days in seconds
    )


@router.post("/patient/register", status_code=201)
def register_patient(req: PatientRegisterRequest, db: DBSession = Depends(get_db)):
    try:
        patient = patient_auth.register(
            db=db,
            email=req.email,
            password=req.password,
            first_name=req.first_name,
            last_name=req.last_name,
            practice_code=req.practice_code,
            date_of_birth=req.date_of_birth,
            phone=req.phone,
        )
        return {
            "message": f"Willkommen, {patient.full_name}!",
            "patient_id": patient.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/patient/login")
def login_patient(req: LoginRequest,response: Response, db: DBSession = Depends(get_db)):
    try:
        patient_login = patient_auth.login(db, req.email, req.password)
        _set_auth_cookies(response, {
            "sub": patient_login["patient_id"],
            "role": "patient",
            "practice_id": patient_login["practice_id"],
        })
        return patient_login

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/physician/register", status_code=201)
def register_physician(req: PhysicianRegisterRequest, db: DBSession = Depends(get_db)):
    try:
        physician = physician_auth.register(
            db=db,
            email=req.email,
            password=req.password,
            first_name=req.first_name,
            last_name=req.last_name,
            practice_id=req.practice_id,
            title=req.title,
            specialty=req.specialty,
        )
        return {
            "message": f"Arzt {physician.full_name} erfolgreich registriert.",
            "physician_id": physician.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/physician/login")
def login_physician(req: LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    try:
        physician_login = physician_auth.login(db, req.email, req.password)
        _set_auth_cookies(response, {
            "sub": physician_login["physician_id"],
            "role": "physician",
            "practice_id": physician_login["practice_id"],
        })
        return physician_login
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))




 
@router.post("/refresh")
def refresh(request: Request, response: Response):
    """
    Use the refresh_token cookie to get a new access_token.
    Call this when the access_token expires (401 response).
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Kein Refresh-Token vorhanden.")
 
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh-Token ungültig oder abgelaufen.")
 
    # Issue a new access token with same identity
    token_data = {
        "sub":         payload["sub"],
        "role":        payload["role"],
        "practice_id": payload.get("practice_id"),
    }
    new_access = create_access_token(token_data)
 
    response.set_cookie(
        key="access_token",
        value=new_access,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        max_age=60 * 60,
    )
    return {"message": "Token erneuert.", "access_token": new_access}
 
 
@router.post("/logout")
def logout(response: Response):
    """Clear both cookies."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Erfolgreich abgemeldet."}