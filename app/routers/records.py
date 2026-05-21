import os
from typing import List

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from .auth import get_current_user

load_dotenv()

router = APIRouter(prefix="/api/records", tags=["Медичні записи"])
UPLOAD_DIR = "uploads"

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_NAME").strip("'\""),
    api_key=os.environ.get("CLOUDINARY_API_KEY").strip("'\""),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET").strip("'\""),
    secure=True,
)


# 1. Створення картки хвороби (Доступно тільки Пацієнту для себе)
@router.post("/cases", response_model=schemas.MedicalCaseResponse)
def create_medical_case(
    case: schemas.MedicalCaseCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role_id != 1:  # 1 - пацієнт
        raise HTTPException(
            status_code=403,
            detail="Тільки пацієнти можуть відкривати нові записи хвороб",
        )

    new_case = models.MedicalCase(
        patient_id=current_user.id,
        case_name=case.case_name,
        description=case.description,
        treatment=case.treatment,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    return new_case


# 2. Вкладення файлу (PDF/Зображення) до конкретної хвороби
@router.post("/cases/{case_id}/upload", response_model=schemas.MedicalRecordResponse)
async def upload_file_to_case(
    case_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role_id != 1:
        raise HTTPException(
            status_code=403, detail="Завантажувати документи може лише пацієнт"
        )

    case = (
        db.query(models.MedicalCase)
        .filter(
            models.MedicalCase.id == case_id,
            models.MedicalCase.patient_id == current_user.id,
        )
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=404, detail="Медичний випадок не знайдено або доступ заборонено"
        )

    try:
        upload_result = cloudinary.uploader.upload(file.file, resource_type="auto")

        cloud_url = upload_result.get("secure_url")

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Помилка завантаження в хмару",
        ) from None

    new_record = models.MedicalRecord(case_id=case_id, title=title, file_path=cloud_url)

    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record


# 3. Перегляд пацієнтом своєї власної історії хвороб у кабінеті
@router.get("/my-history", response_model=List[schemas.MedicalCaseResponse])
def get_my_history(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role_id != 1:
        raise HTTPException(status_code=403, detail="Доступно тільки для пацієнтів")

    cases = (
        db.query(models.MedicalCase)
        .filter(models.MedicalCase.patient_id == current_user.id)
        .all()
    )

    for case in cases:
        case.records = (
            db.query(models.MedicalRecord)
            .filter(models.MedicalRecord.case_id == case.id)
            .all()
        )
    return cases


# 4. Перегляд лікарем ПОВНОЇ історії хвороб пацієнта по його ID + запис у журнал
@router.get(
    "/doctor/patient/{patient_id}/history",
    response_model=List[schemas.MedicalCaseResponse],
)
def doctor_view_patient_history(
    patient_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role_id != 2:  # 2 - лікар
        raise HTTPException(
            status_code=403, detail="Цей ендпоінт призначений виключно для лікарів"
        )

    patient = (
        db.query(models.User)
        .filter(models.User.id == patient_id, models.User.role_id == 1)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Пацієнта не знайдено")

    log = models.AccessLog(patient_id=patient_id, doctor_id=current_user.id)
    db.add(log)
    db.commit()

    cases = (
        db.query(models.MedicalCase)
        .filter(models.MedicalCase.patient_id == patient_id)
        .all()
    )

    for case in cases:
        case.records = (
            db.query(models.MedicalRecord)
            .filter(models.MedicalRecord.case_id == case.id)
            .all()
        )

    return cases


# 5. Перегляд пацієнтом журналу безпеки: хто і коли дивився його медичну картку
@router.get("/my-card-logs")
def get_transparent_logs(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role_id != 1:  # 1 - пацієнт
        raise HTTPException(
            status_code=403,
            detail="Тільки пацієнти можуть переглядати логи своєї картки",
        )

    logs = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.patient_id == current_user.id)
        .all()
    )

    formatted_logs = []
    for log in logs:
        doctor = db.query(models.User).filter(models.User.id == log.doctor_id).first()
        formatted_logs.append(
            {
                "accessed_at": log.accessed_at,
                "doctor_name": f"{doctor.first_name} {doctor.last_name}"
                if doctor
                else "Невідомий лікар",
            }
        )
    return formatted_logs


# 6. Редагування картки хвороби (Доступно пацієнту-власнику ТА будь-якому лікарю)
# ОНОВЛЕНО: Лікар тепер має повне право змінювати будь-який кейс
@router.put("/cases/{case_id}", response_model=schemas.MedicalCaseResponse)
def update_medical_case(
    case_id: int,
    case_data: schemas.MedicalCaseUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(models.MedicalCase).filter(models.MedicalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Медичний випадок не знайдено")

    # Перевірка доступу:
    # Якщо це пацієнт (role_id == 1) і кейс належить не йому — викидаємо помилку 403
    if current_user.role_id == 1 and case.patient_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="У вас немає прав на редагування цього запису"
        )

    # Якщо це лікар (role_id == 2) — перевірка вище ігнорується,
    # і він може редагувать дані хвороби

    for key, value in case_data.model_dump(exclude_unset=True).items():
        setattr(case, key, value)

    db.commit()
    db.refresh(case)
    return case


# 7. Видалення картки хвороби (Доступно пацієнту-власнику ТА будь-якому лікарю)
# ОНОВЛЕНО: Лікар тепер теж може видалити будь-який медичний випадок
@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medical_case(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(models.MedicalCase).filter(models.MedicalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Медичний випадок не знайдено")

    # Перевірка доступу:
    # Якщо це пацієнт (role_id == 1) і він намагається видалити ЧУЖИЙ кейс — блокуємо
    if current_user.role_id == 1 and case.patient_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="У вас немає прав на видалення цього запису"
        )

    # Якщо це лікар (role_id == 2) — перевірка вище пропускається,
    # і він може видалити кейс

    # Оскільки ми видаляємо весь кейс, правильним кроком буде також видалити
    # всі пов'язані з цим кейсом медичні файли (якщо вони є)
    db.delete(case)
    db.commit()
    return None


# 8. Видалення окремого медичного файлу/фото пацієнтом
@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medical_record(
    record_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role_id != 1:
        raise HTTPException(
            status_code=403, detail="Тільки пацієнти можуть видаляти свої файли"
        )

    # Шукаємо запис про файл у базі даних
    record = (
        db.query(models.MedicalRecord)
        .filter(models.MedicalRecord.id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Файл не знайдено")

    # Перевіряємо, чи цей файл належить саме цьому пацієнту через зв'язок з MedicalCase
    case = (
        db.query(models.MedicalCase)
        .filter(models.MedicalCase.id == record.case_id)
        .first()
    )
    if not case or case.patient_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Ви не маєте доступу до видалення цього файлу"
        )

    # Видаляємо запис з бази даних
    db.delete(record)
    db.commit()
    return None
