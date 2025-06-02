from fastapi import Depends, HTTPException, status, APIRouter, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal, User, Role
from jose import JWTError, jwt
import os
from sqlalchemy.exc import IntegrityError
from pydantic import EmailStr

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define credentials_exception at the module level
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    return user

def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    return current_user

def get_current_manager(current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    return current_user

def get_current_cook(current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.COOK]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Cook or Admin access required",
        )
    return current_user

@router.post("/register")
async def register(full_name: str = Form(...), email: EmailStr = Form(...), password: str = Form(...), role: str = Form(...), db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    try:
        hashed_password = get_password_hash(password)
        new_user = User(full_name=full_name, email=email, password=hashed_password, role=role.upper())
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "User registered successfully", "user_id": new_user.id}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Database error: Email already exists or invalid data")

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}