
import hashlib

from attrs.filters import include
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DBSession

from app.auth.auth_service import decode_token
from app.models.database import get_db
from app.models.models import Patient, Physician, PhysicianInvite, _now

bearer_scheme = HTTPBearer(auto_error=False)

def _hash_token(token: str) -> str:
    return hashlib.sha256(
        token.encode()
    ).hexdigest()

def _get_payload(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:

    token = credentials.credentials if credentials else request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ungültig oder abgelaufen.",
        )

    return payload


def get_current_patient(
    payload: dict = Depends(_get_payload),
    db: DBSession = Depends(get_db),
) -> Patient:

    if payload.get("role") != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token.",
        )

    patient = db.query(Patient).filter(
        Patient.id == user_id,
        Patient.is_active.is_(True),
    ).first()

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff.",
        )

    return patient


def get_current_physician(
    payload: dict = Depends(_get_payload),
    db: DBSession = Depends(get_db),
) -> Physician:
    """Only allows authenticated physicians."""
    if payload.get("role") != "physician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Ärzte haben Zugriff auf diesen Bereich.",
        )
    physician = db.query(Physician).filter(
        Physician.id == payload["sub"],
        Physician.is_active == True,
    ).first()
    if not physician:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Arzt nicht gefunden oder deaktiviert.",
        )
    return physician


def get_current_user(
    payload: dict = Depends(_get_payload),
    db: DBSession = Depends(get_db),
) -> Patient | Physician:
    """Allows both patients and physicians."""
    role = payload.get("role")
    if role == "patient":
        return db.query(Patient).filter(Patient.id == payload["sub"]).first()
    elif role == "physician":
        return db.query(Physician).filter(Physician.id == payload["sub"]).first()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültige Rolle.")


def validate_physician_invite(
    invite_token: str = Query(...),
    db: DBSession = Depends(get_db),
) -> PhysicianInvite:

    token_hash = _hash_token(
        invite_token
    )

    invite = (
        db.query(PhysicianInvite)
        .filter(
            PhysicianInvite.token_hash
            == token_hash
        )
        .first()
    )

    if not invite:
        raise HTTPException(
            status_code=401,
            detail="Invalid invite",
        )

    if invite.used_at:
        raise HTTPException(
            status_code=403,
            detail="Invite already used",
        )

    if invite.expires_at < _now():
        raise HTTPException(
            status_code=403,
            detail="Invite expired",
        )

    return invite

def has_role(physician,role: str) -> bool:
    return any(
        r.role == role
        for r in physician.roles
    )