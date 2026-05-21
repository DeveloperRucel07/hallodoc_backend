
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DBSession

from app.auth.auth_service import PatientAuthService, PhysicianAuthService
from app.models.database import get_db

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
def login_patient(req: LoginRequest, db: DBSession = Depends(get_db)):
    try:
        return patient_auth.login(db, req.email, req.password)
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
def login_physician(req: LoginRequest, db: DBSession = Depends(get_db)):
    try:
        return physician_auth.login(db, req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))