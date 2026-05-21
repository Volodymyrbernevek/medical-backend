import os
from datetime import datetime, timedelta

import bcrypt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

load_dotenv()

router = APIRouter(prefix="/api/auth", tags=["Аутентифікація"])

# Секретні ключі для шифрування JWT токенів
SECRET_KEY = os.environ.get("SECRET_KEY").strip("'\"")
ALGORITHM = os.environ.get("ALGORITHM").strip("'\"")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Залежність (Dependency) для захисту інших ендпоінтів
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Недійсний токен доступу")
    except JWTError as err:
        raise HTTPException(status_code=401, detail="Недійсний токен доступу") from err

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Користувача не знайдено")
    return user


# 1. Ендпоінт реєстрації (пацієнт / лікар)
@router.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=400, detail="Користувач з таким email вже існує"
        )

    new_user = models.User(
        email=user.email,
        password_hash=hash_password(user.password),
        role_id=user.role_id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# 2. Ендпоінт входу (Login)
@router.post("/login", response_model=schemas.Token)
def login_for_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Неправильний email або пароль")

    role_name = "patient" if user.role_id == 1 else "doctor"
    token = create_access_token({"sub": user.email, "id": user.id, "role": role_name})
    return {"access_token": token, "token_type": "bearer", "role": role_name}


# 3. Редагування власного профілю
@router.put("/me", response_model=schemas.UserResponse)
def update_me(
    user_data: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for key, value in user_data.model_dump(exclude_unset=True).items():
        setattr(current_user, key, value)
    db.commit()
    db.refresh(current_user)
    return current_user


# 4. Видалення власного акаунту
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    db.delete(current_user)
    db.commit()
    return None


# 5. Отримання профілю поточного користувача
@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_profile(current_user: models.User = Depends(get_current_user)):
    return current_user
