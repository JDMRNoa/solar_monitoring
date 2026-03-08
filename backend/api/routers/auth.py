import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from backend.core.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASS", "admin123")
    op_user = os.getenv("OP_USER", "operador")
    op_pass = os.getenv("OP_PASS", "op123")
    
    if request.username == admin_user and request.password == admin_pass:
        role = "admin"
    elif request.username == op_user and request.password == op_pass:
        role = "operator"
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    access_token = create_access_token(data={"sub": request.username, "role": role})
    return {"access_token": access_token, "role": role}

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
