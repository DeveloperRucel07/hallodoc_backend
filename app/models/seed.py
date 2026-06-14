
from app.models.database import init_db, SessionLocal
from app.models.models import Practice, Role
from app.auth.auth_service import PatientAuthService, PhysicianAuthService
from app.core.config import config


DEFAULT_ROLES = [
    {
        "name": "physician",
        "description":"Standard physician access"
    },
    {
        "name": "admin",
        "description":"Practice administration"
    },
    {
        "name": "supervisor",
        "description":"Clinical supervision"
    },
    {
        "name": "triage_reviewer",
        "description":"Reviews AI triage"
    },
]

def seed():
    init_db()
    db = SessionLocal()

    try:
        practice = db.query(Practice).filter(
            Practice.code == config.PRACTICE_CODE
        ).first()

        if not practice:
            practice = Practice(
                code=config.PRACTICE_CODE,
                name="HalloDOC Testpraxis",
                address="Musterstraße 1, 10115 Berlin",
                phone="+49 30 12345678",
                email="praxis@hallodoc.de",
            )
            db.add(practice)
            db.commit()
            db.refresh(practice)
            print(f"✓ Practice created: '{practice.name}' (code: {practice.code})")
        else:
            print(f"  Practice already exists: {practice.name}")

        # Seed default roles
        for role_data in DEFAULT_ROLES:
            role = db.query(Role).filter(
                Role.name == role_data["name"]
            ).first()
            if not role:
                role = Role(
                    name=role_data["name"],
                    description=role_data["description"],
                )
                db.add(role)
                print(f"✓ Role created: {role.name}")
            else:
                print(f"  Role already exists: {role.name}")
        db.commit()


        physician_svc = PhysicianAuthService()
        try:
            physician = physician_svc.register(
                db=db,
                email="arzt@hallodoc.de",
                password="Test1234!",
                first_name="Rucel",
                last_name="Mustermann",
                practice_id=practice.id,
                title="Prof. Dr.",
                specialty="Allgemeinmedizin",
                roles=[
                    db.query(Role).filter(Role.name == "physician").first(),
                    db.query(Role).filter(Role.name == "admin").first(),
                ]
            )
            print(f"✓ Test physician: {physician.full_name} (arzt@hallodoc.de / Test1234!)")
        except ValueError:
            print("  Test physician already exists")

        # Test patient
        patient_svc = PatientAuthService()
        try:
            patient = patient_svc.register(
                db=db,
                email="patient@hallodoc.de",
                password="Test1234!",
                first_name="Max",
                last_name="Muster",
                practice_code=config.PRACTICE_CODE,
                date_of_birth="1990-05-15",
                phone="+49 170 1234567",
                gender ="male",
            )
            print(f"✓ Test patient: {patient.full_name} (patient@hallodoc.de / Test1234!)")
        except ValueError:
            print("  Test patient already exists")

        print("\n✅ Seed complete.")
        print(f"   Practice code for patient registration: {config.PRACTICE_CODE}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()