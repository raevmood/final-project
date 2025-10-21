"""
Authentication routes: register, login, user info
"""
from datetime import timedelta
from fastapi import APIRouter, HTTPException, status, Depends

from user_store import UserStore
from schemas import UserRegister, UserLogin, Token, UserResponse
from auth_utils import (
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_HOURS
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================
# REGISTER NEW USER
# ============================================================
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegister):
    """
    Register a new user account
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address (must be unique)
    - **password**: Strong password (minimum 8 characters)
    
    Returns the created user data (without password)
    """
    try:
        # Create user in memory
        user = UserStore.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password
        )
        
        print(f"✓ New user registered: {user['username']} ({user['email']})")
        
        # Return user data (excluding hashed_password)
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "is_active": user["is_active"],
            "created_at": user["created_at"],
            "last_login": user["last_login"],
            "search_count": user.get("search_count", 0)
        }
    
    except ValueError as e:
        # Username or email already exists
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================
# LOGIN AND GET JWT TOKEN
# ============================================================
@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login with username and password to receive JWT access token
    
    - **username**: Your username
    - **password**: Your password
    
    Returns a JWT token valid for 24 hours
    """
    # Authenticate user
    user = UserStore.authenticate_user(
        username=credentials.username,
        password=credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login timestamp
    UserStore.update_last_login(credentials.username)
    
    # Create JWT access token
    access_token_expires = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]},
        expires_delta=access_token_expires
    )
    
    print(f"✓ User logged in: {user['username']}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600  # Convert to seconds
    }


# ============================================================
# GET CURRENT USER INFO
# ============================================================
@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get information about the currently authenticated user
    
    Requires: Valid JWT token in Authorization header
    """
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "is_active": current_user["is_active"],
        "created_at": current_user["created_at"],
        "last_login": current_user["last_login"],
        "search_count": current_user.get("search_count", 0)
    }


# ============================================================
# TEST PROTECTED ROUTE
# ============================================================
@router.get("/test-protected")
async def test_protected_route(current_user: dict = Depends(get_current_user)):
    """
    Test endpoint to verify JWT authentication is working
    
    Requires: Valid JWT token in Authorization header
    """
    return {
        "message": f"Hello {current_user['username']}! Authentication is working perfectly.",
        "user_id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "total_searches": current_user.get("search_count", 0)
    }


# ============================================================
# ADMIN ENDPOINTS (Optional)
# ============================================================
@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    """
    Get statistics about registered users
    
    (In production, you might want to restrict this to admin users only)
    """
    return {
        "total_users": UserStore.get_user_count(),
        "your_searches": current_user.get("search_count", 0)
    }