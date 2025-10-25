"""
In-memory user storage for DeviceFinder.AI
Simple dictionary-based storage - perfect for MVP/demo
"""
from datetime import datetime
from typing import Optional, Dict
from passlib.context import CryptContext
import json
from pathlib import Path

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory storage
# Structure: {username: user_data_dict}
USERS_DB: Dict[str, dict] = {}

# Auto-increment ID counter
_user_id_counter = 1

# Persistent storage file
USERS_FILE = Path("users_data.json")


def _load_users_from_disk():
    """Load users from JSON file on startup"""
    global USERS_DB, _user_id_counter
    
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                USERS_DB = data.get('users', {})
                _user_id_counter = data.get('next_id', 1)
            print(f"✓ Loaded {len(USERS_DB)} users from disk")
        except Exception as e:
            print(f"⚠️  Could not load users from disk: {e}")
            USERS_DB = {}
            _user_id_counter = 1
    else:
        print("ℹ️  No existing users file found, starting fresh")


def _save_users_to_disk():
    """Save users to JSON file"""
    try:
        data = {
            'users': USERS_DB,
            'next_id': _user_id_counter
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save users to disk: {e}")


_load_users_from_disk()

class UserStore:
    """Manages in-memory user storage"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plain password"""
        # Bcrypt has a 72-byte limit, truncate if necessary
        if len(password.encode('utf-8')) > 72:
            password = password[:72]
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_user(username: str, email: str, password: str) -> dict:
        """
        Create a new user and store in memory
        
        Returns:
            User dictionary with id, username, email, etc.
        
        Raises:
            ValueError: If username or email already exists or password too long
        """
        global _user_id_counter
        
        # Validate password length (bcrypt limit)
        if len(password.encode('utf-8')) > 72:
            raise ValueError("Password too long (max 72 bytes)")
        
        # Check if username exists
        if username in USERS_DB:
            raise ValueError("Username already exists")
        
        # Check if email exists
        for user in USERS_DB.values():
            if user["email"] == email:
                raise ValueError("Email already exists")
        
        # Create new user
        user_data = {
            "id": _user_id_counter,
            "username": username,
            "email": email,
            "hashed_password": UserStore.hash_password(password),
            "is_active": True,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "last_login": None,
            "search_count": 0
        }
        
        USERS_DB[username] = user_data
        _user_id_counter += 1
        _save_users_to_disk()  # ADD THIS LINE
        
        return user_data
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[dict]:
        """Get user by username"""
        return USERS_DB.get(username)
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[dict]:
        """Get user by email"""
        for user in USERS_DB.values():
            if user["email"] == email:
                return user
        return None
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[dict]:
        """Get user by ID"""
        for user in USERS_DB.values():
            if user["id"] == user_id:
                return user
        return None
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[dict]:
        """
        Authenticate user with username and password
        
        Returns:
            User dict if authentication successful, None otherwise
        """
        user = UserStore.get_user_by_username(username)
        if not user:
            return None
        
        if not UserStore.verify_password(password, user["hashed_password"]):
            return None
        
        return user
    
    @staticmethod
    def update_last_login(username: str):
        """Update user's last login timestamp"""
        if username in USERS_DB:
            USERS_DB[username]["last_login"] = datetime.utcnow().isoformat() + "Z"
            _save_users_to_disk()  # ADD THIS LINE

    @staticmethod
    def increment_search_count(username: str):
        """Increment user's search count (optional tracking)"""
        if username in USERS_DB:
            USERS_DB[username]["search_count"] += 1
            _save_users_to_disk()  # ADD THIS LINE
    @staticmethod
    def get_all_users() -> list:
        """Get all users (for admin purposes)"""
        return list(USERS_DB.values())
    
    @staticmethod
    def get_user_count() -> int:
        """Get total number of registered users"""
        return len(USERS_DB)
    
    @staticmethod
    def delete_user(username: str) -> bool:
        """Delete a user (for admin purposes)"""
        if username in USERS_DB:
            del USERS_DB[username]
            _save_users_to_disk()  # ADD THIS LINE
            return True
        return False


# ============================================================
# OPTIONAL: Pre-populate with test users (for development)
# ============================================================
def initialize_test_users():
    """
    Create test users for development/demo purposes.
    Comment this out in production or after first real user registers.
    """
    try:
        # Create a test user
        UserStore.create_user(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        print("✓ Test user created: testuser / password123")
    except ValueError:
        # User already exists
        pass


# Uncomment this line to create test user on startup:
# initialize_test_users()