from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from src.core.db import get_db_connection
import psycopg2
from src.core.security import create_access_token

router = APIRouter()

class RegisterRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest):
    conn = None
    try:
        req_data = data.model_dump()
        print(f"DEBUG: Register request payload: {req_data}")
        
        name = req_data.get('name')
        email = req_data.get('email')
        password = req_data.get('password')
        
        if not all([name, email, password]):
            print("ERROR: Missing required fields (name, email, password)")
            # Return JSON error response with 400
            raise HTTPException(status_code=400, detail="Missing name, email, or password")
            
        conn = get_db_connection()
        if not conn:
             print("ERROR: Database connection failed")
             raise HTTPException(status_code=500, detail="Database connection failed")
            
        cur = conn.cursor()
        
        # Check if user exists
        print(f"DEBUG: Checking if user with email {email} exists...")
        cur.execute("SELECT user_id FROM \"user\" WHERE email_id = %s", (email,))
        if cur.fetchone():
            print(f"DEBUG: User with email {email} already exists.")
            cur.close()
            conn.close()
            raise HTTPException(status_code=409, detail="User with this email already exists")
            
        # Insert new user
        print(f"DEBUG: Inserting new user: {name}, {email}")
        cur.execute(
            "INSERT INTO \"user\" (name, email_id, password) VALUES (%s, %s, %s) RETURNING user_id, name, email_id",
            (name, email, password)
        )
        new_user = cur.fetchone()
        conn.commit()
        
        user_response = {
            "id": new_user[0],
            "name": new_user[1],
            "email": new_user[2],
            "joinedAt": "Just now" 
        }
        
        # Issue JWT Token
        token = create_access_token({"sub": str(new_user[0]), "email": new_user[2]})
        user_response["access_token"] = token
        user_response["token_type"] = "bearer"

        print(f"DEBUG: Registration successful: {user_response}")
        
        cur.close()
        conn.close()
        
        return {"message": "Registration successful", "user": user_response}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"CRITICAL ERROR in /register: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", status_code=status.HTTP_200_OK)
def login(data: LoginRequest):
    conn = None
    try:
        req_data = data.model_dump()
        print(f"DEBUG: Login request payload: {req_data}")
        
        email = req_data.get('email')
        password = req_data.get('password')
        
        if not all([email, password]):
            print("ERROR: Missing email or password")
            raise HTTPException(status_code=400, detail="Missing email or password")
            
        conn = get_db_connection()
        if not conn:
            print("ERROR: Database connection failed")
            raise HTTPException(status_code=500, detail="Database connection failed")
            
        cur = conn.cursor()
        
        print(f"DEBUG: Attempting login for {email}...")
        cur.execute("SELECT user_id, name, email_id FROM \"user\" WHERE email_id = %s AND password = %s", (email, password))
        user = cur.fetchone()
        
        if user:
            user_response = {
                "id": user[0],
                "name": user[1],
                "email": user[2],
                "joinedAt": "Unknown" 
            }
            
            # Issue JWT Token
            token = create_access_token({"sub": str(user[0]), "email": user[2]})
            user_response["access_token"] = token
            user_response["token_type"] = "bearer"

            print(f"DEBUG: Login successful for user: {user_response}")
            cur.close()
            conn.close()
            return {"message": "Login successful", "user": user_response}
        else:
            print(f"DEBUG: Login failed for {email} - Invalid credentials")
            cur.close()
            conn.close()
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"CRITICAL ERROR in /login: {str(e)}")
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))
