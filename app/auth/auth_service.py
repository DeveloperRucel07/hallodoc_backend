
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session as DBSession

from app.models.models import Patient, Physician, Practice
from app.core.config import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(data: dict, expires_minutes: int = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or config.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload["exp"] = expire
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload["type"] = "access"
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=7)
    payload["type"] = "refresh"
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None
    



class PatientAuthService:

    def register(
        self,
        db: DBSession,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        practice_code: str,
        date_of_birth: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Patient:
        practice = db.query(Practice).filter(
            Practice.code == practice_code,
            Practice.is_active == True,
        ).first()
        if not practice:
            raise ValueError(f"Praxis-Code '{practice_code}' ist ungültig oder inaktiv.")

        if db.query(Patient).filter(Patient.email == email).first():
            raise ValueError("Diese E-Mail-Adresse ist bereits registriert.")

        dob = None
        if date_of_birth:
            try:
                dob = date.fromisoformat(date_of_birth)
            except ValueError:
                raise ValueError("date_of_birth muss im Format YYYY-MM-DD sein.")

        patient = Patient(
            practice_id=practice.id,
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            phone=phone,
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        return patient

    def login(self, db: DBSession, email: str, password: str) -> dict:
        patient = db.query(Patient).filter(
            Patient.email == email.lower().strip(),
            Patient.is_active == True,
        ).first()

        if not patient or not verify_password(password, patient.hashed_password):
            raise ValueError("E-Mail oder Passwort ist falsch.")

        token = create_access_token({
            "sub": patient.id,
            "role": "patient",
            "practice_id": patient.practice_id,
        })
        return {
            "access_token": token,
            "refresh_token": create_refresh_token({
                "sub": patient.id,
                "role": "patient",
                "practice_id": patient.practice_id,
            }),
            "token_type": "bearer",
            "patient_id": patient.id,
            "full_name": patient.full_name,
            "practice_id": patient.practice_id,
        }


class PhysicianAuthService:

    def register(
        self,
        db: DBSession,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        practice_id: str,
        title: Optional[str] = None,
        specialty: Optional[str] = None,
    ) -> Physician:
        practice = db.query(Practice).filter(
            Practice.id == practice_id,
            Practice.is_active == True,
        ).first()
        if not practice:
            raise ValueError("Praxis nicht gefunden.")

        if db.query(Physician).filter(Physician.email == email).first():
            raise ValueError("Diese E-Mail-Adresse ist bereits registriert.")

        physician = Physician(
            practice_id=practice_id,
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            title=title,
            specialty=specialty,
        )
        db.add(physician)
        db.commit()
        db.refresh(physician)
        return physician

    def login(self, db: DBSession, email: str, password: str) -> dict:
        physician = db.query(Physician).filter(
            Physician.email == email.lower().strip(),
            Physician.is_active == True,
        ).first()

        if not physician or not verify_password(password, physician.hashed_password):
            raise ValueError("E-Mail oder Passwort ist falsch.")

        token = create_access_token({
            "sub": physician.id,
            "role": "physician",
            "practice_id": physician.practice_id,
        })
        return {
            "access_token": token,
            "refresh_token": create_refresh_token({
                "sub": physician.id,
                "role": "physician",
                "practice_id": physician.practice_id,
            }),
            "token_type": "bearer",
            "physician_id": physician.id,
            "full_name": physician.full_name,
            "practice_id": physician.practice_id,
            "specialty": physician.specialty,
        }