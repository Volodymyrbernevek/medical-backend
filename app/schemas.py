from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr


# Схеми для Користувачів
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role_id: int  # 1 - пацієнт, 2 - лікар
    first_name: str
    last_name: str
    phone: Optional[str] = None


# Схема для Токена
class Token(BaseModel):
    access_token: str
    token_type: str
    role: str


# Схеми для Медичних Записів (Файлів)
class MedicalRecordResponse(BaseModel):
    id: int
    case_id: int
    title: str
    file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


# Схеми для Історії хвороб (Кейсів)
class MedicalCaseCreate(BaseModel):
    case_name: str
    description: Optional[str] = None
    treatment: Optional[str] = None


class MedicalCaseResponse(BaseModel):
    id: int
    patient_id: int
    case_name: str
    description: Optional[str] = None
    treatment: Optional[str] = None
    created_at: datetime
    records: List[MedicalRecordResponse] = []

    class Config:
        from_attributes = True


# Схема для оновлення профілю користувача
class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


# Схема для оновлення медичної картки хвороби
class MedicalCaseUpdate(BaseModel):
    case_name: Optional[str] = None
    description: Optional[str] = None
    treatment: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    role_id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True
