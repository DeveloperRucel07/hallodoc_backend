
from app.models.database import init_db, SessionLocal
from app.models.models import Practice
from app.auth.auth_service import PatientAuthService, PhysicianAuthService
from app.core.config import config


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
                role="admin",
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