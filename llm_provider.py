import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

load_dotenv()


class RateLimitExceeded(Exception):
    """Custom exception for rate limit violations"""
    def __init__(self, message: str, retry_after: int):
        self.message = message
        self.retry_after = retry_after  # seconds until reset
        super().__init__(self.message)


class RateLimiter:
    """
    In-memory rate limiter for tracking user requests.
    
    For production with multiple workers, use Redis instead.
    """
    def __init__(self, max_requests: int = 100, window_minutes: int = 60):
        """
        Args:
            max_requests: Maximum requests allowed per window
            window_minutes: Time window in minutes
        """
        self.max_requests = max_requests
        self.window_minutes = window_minutes
        self.user_requests: Dict[str, list] = {}  # {user_id: [timestamp1, timestamp2, ...]}
    
    def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user has exceeded rate limit.
        
        Args:
            user_id: Unique user identifier (from JWT)
        
        Returns:
            True if within limit, False if exceeded
        
        Raises:
            RateLimitExceeded: If limit is exceeded
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.window_minutes)
        
        # Get user's request history
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Remove old requests outside the time window
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > window_start
        ]
        
        # Check if limit exceeded
        current_count = len(self.user_requests[user_id])
        if current_count >= self.max_requests:
            # Calculate seconds until oldest request expires
            oldest_request = min(self.user_requests[user_id])
            retry_after = int((oldest_request + timedelta(minutes=self.window_minutes) - now).total_seconds())
            
            raise RateLimitExceeded(
                f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_minutes} minutes. "
                f"Current: {current_count}/{self.max_requests}",
                retry_after=max(retry_after, 1)
            )
        
        # Record this request
        self.user_requests[user_id].append(now)
        return True
    
    def get_remaining_requests(self, user_id: str) -> int:
        """Get number of remaining requests for a user"""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.window_minutes)
        
        if user_id not in self.user_requests:
            return self.max_requests
        
        # Count requests in current window
        recent_requests = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > window_start
        ]
        
        return max(0, self.max_requests - len(recent_requests))
    
    def reset_user(self, user_id: str):
        """Reset rate limit for a specific user (admin function)"""
        if user_id in self.user_requests:
            del self.user_requests[user_id]


class LLMProvider:
    """
    LLM Provider with per-user rate limiting.
    
    Rate Limits (configurable):
    - Default: 100 requests per hour per user
    - Can be adjusted via environment variables
    """
    def __init__(self):
        """Initialise LLM Selection with Rate Limiting"""
        
        # Initialize rate limiter
        max_requests = int(os.getenv("LLM_MAX_REQUESTS_PER_HOUR", "100"))
        window_minutes = int(os.getenv("LLM_RATE_LIMIT_WINDOW_MINUTES", "60"))
        self.rate_limiter = RateLimiter(max_requests=max_requests, window_minutes=window_minutes)
        
        # Initialize Gemini (backup)
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if not gemini_key:
            raise ValueError("Gemini API key not set")
        
        self.backup_model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            google_api_key=gemini_key,
            temperature=0.7,
            max_output_tokens=2048
        )

        # Initialize Groq (main)
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("Groq API key not set")
        
        self.main_model = ChatGroq(
            model="llama-3.1-8b-instant",
            groq_api_key=groq_key,
            temperature=0.7,
            max_tokens=2048
        )
        
        print(f"✓ LLM Provider initialized with rate limiting: {max_requests} requests per {window_minutes} minutes")

    def generate(self, message: str, user_id: Optional[str] = None) -> str:
        """
        Generate LLM response with rate limiting.
        
        Args:
            message: The prompt/message to send to LLM
            user_id: User identifier from JWT token (required for rate limiting)
        
        Returns:
            Generated text response
        
        Raises:
            RateLimitExceeded: If user has exceeded their rate limit
        """
        # Check rate limit if user_id provided
        if user_id:
            self.rate_limiter.check_rate_limit(user_id)
        
        try:
            # Try main model first (Groq)
            try:
                response = self.main_model.invoke(message)
                if response and response.content:
                    return response.content
                else:
                    print(f"Main model returned empty content for message: {message[:100]}...")
                    raise ValueError("Main model returned empty content")
            
            except Exception as e_main:
                print(f"Main model failure: {e_main}. Attempting backup model...")
                
                # Try backup model (Gemini)
                try:
                    response = self.backup_model.invoke(message)
                    if response and response.content:
                        return response.content
                    else:
                        print(f"Backup model returned empty content for message: {message[:100]}...")
                        raise ValueError("Backup model returned empty content")
                
                except Exception as e_backup:
                    print(f"Total model failure: {e_backup}")
                    return ""

        except Exception as e_outer:
            print(f"Unexpected error in LLMProvider.generate: {e_outer}")
            return ""
    
    def get_user_rate_limit_status(self, user_id: str) -> dict:
        """
        Get rate limit status for a user.
        
        Returns:
            Dictionary with limit info: {remaining, limit, window_minutes}
        """
        remaining = self.rate_limiter.get_remaining_requests(user_id)
        return {
            "remaining_requests": remaining,
            "max_requests": self.rate_limiter.max_requests,
            "window_minutes": self.rate_limiter.window_minutes,
            "reset_info": f"Limit resets on a rolling {self.rate_limiter.window_minutes}-minute window"
        }


# Example usage for testing
if __name__ == "__main__":
    llm_provider_test = LLMProvider()
    
    # Test with user_id
    test_user_id = "user_123"
    
    print("\n=== Test 1: Normal Request ===")
    try:
        result = llm_provider_test.generate(
            "What is JSON? Reply in only 30 words",
            user_id=test_user_id
        )
        print(f"Result length: {len(result) if result else 0}")
        print(f"Result: {result[:200]}...")
        
        # Check remaining requests
        status = llm_provider_test.get_user_rate_limit_status(test_user_id)
        print(f"\nRate limit status: {status}")
    
    except RateLimitExceeded as e:
        print(f"Rate limit error: {e.message}")
        print(f"Retry after: {e.retry_after} seconds")
    
    print("\n=== Test 2: Multiple Requests ===")
    for i in range(5):
        try:
            result = llm_provider_test.generate(
                f"Count to {i+1}",
                user_id=test_user_id
            )
            status = llm_provider_test.get_user_rate_limit_status(test_user_id)
            print(f"Request {i+1}: Success. Remaining: {status['remaining_requests']}")
        except RateLimitExceeded as e:
            print(f"Request {i+1}: Rate limited - {e.message}")
            break