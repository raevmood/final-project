import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from requests import status_codes

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends, status
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
load_dotenv() # Load environment variables early

# Import authentication components (NEW)
import auth_routes
from auth_utils import get_current_user
from user_store import UserStore

# Import your core components
from llm_provider import LLMProvider, RateLimitExceeded # Added RateLimitExceeded
from vector_db_tool import VectorDBTool
from serper_tool import SerperSearchTool
from device_agents import (
    create_phone_agent,
    create_laptop_agent,
    create_tablet_agent,
    create_earpiece_agent,
    create_prebuilt_pc_agent,
    create_pc_builder_agent
)
from data_ingestor import run_daily_ingestion # The refactored ingestion function

# Import chatbot components (NEW)
from chatbot import DeviceFinderChatbot
from memory import DeviceFinderMemory

app = FastAPI(
    title="DeviceFinder.AI API",
    description="AI-powered multi-agent system for finding and recommending electronic devices with JWT authentication.",
    version="2.0.0"
)

origins = [
    "http://localhost:8000",
    "https://raevmood.github.io/final-frontend",
    "https://raevmood.github.io/final-frontend/",
    "https://raevmood.github.io"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# Include authentication routes (NEW)
app.include_router(auth_routes.router)

llm_instance: Optional[LLMProvider] = None
vector_db_instance: Optional[VectorDBTool] = None
serper_instance: Optional[SerperSearchTool] = None

phone_agent = None
laptop_agent = None
tablet_agent = None
earpiece_agent = None
prebuilt_pc_agent = None
pc_builder_agent = None

@app.on_event("startup")
async def startup_event():
    global llm_instance, vector_db_instance, serper_instance
    global phone_agent, laptop_agent, tablet_agent, earpiece_agent, prebuilt_pc_agent, pc_builder_agent

    print("=" * 60)
    print("DeviceFinder.AI - Starting Up")
    print("=" * 60)
    
    # Initialize test user for development (NEW)
    from user_store import initialize_test_users
    initialize_test_users()
    print(f"✓ Total registered users: {UserStore.get_user_count()}")

    print("Initializing core components...")
    try:
        llm_instance = LLMProvider()
        vector_db_instance = VectorDBTool()
        serper_instance = SerperSearchTool()

        # Initialize agents
        phone_agent = create_phone_agent(llm_instance, vector_db_instance, serper_instance)
        laptop_agent = create_laptop_agent(llm_instance, vector_db_instance, serper_instance)
        tablet_agent = create_tablet_agent(llm_instance, vector_db_instance, serper_instance)
        earpiece_agent = create_earpiece_agent(llm_instance, vector_db_instance, serper_instance)
        prebuilt_pc_agent = create_prebuilt_pc_agent(llm_instance, vector_db_instance, serper_instance)
        pc_builder_agent = create_pc_builder_agent(llm_instance, serper_instance) # PC Builder doesn't use vector_db

        print("✓ All components and agents initialized successfully.")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Failed to initialize components: {e}")
        raise RuntimeError(f"Application startup failed: {e}") from e

# --- Security for Ingestion Endpoint ---
INGESTION_API_KEY = os.getenv("INGESTION_API_KEY") # Ensure this is set in Render env vars

def authenticate_ingestion_request(x_api_key: str = Header(None)):
    if not INGESTION_API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: Ingestion API Key not set.")
    if x_api_key != INGESTION_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key for ingestion.")
    return True

# --- API Endpoints ---

@app.get("/", summary="Root endpoint for API status")
async def root():
    return {
        "message": "DeviceFinder.AI API is running",
        "version": "2.0.0",
        "authentication": "JWT-based (in-memory)",
        "docs": "/docs",
        "register": "/auth/register",
        "login": "/auth/login",
        "total_users": UserStore.get_user_count()
    }

# --- Ingestion Endpoint ---
@app.post(
    "/ingest_daily_data",
    summary="Trigger daily data ingestion for vector database",
    description="This endpoint is designed to be called by an external scheduler (e.g., n8n) to populate the vector database with fresh search results. Requires authentication via X-API-KEY header."
)
async def trigger_daily_ingestion_endpoint(
    background_tasks: BackgroundTasks,
    authenticated: bool = Depends(authenticate_ingestion_request) # Apply security here
):
    print(f"API endpoint /ingest_daily_data called at {datetime.utcnow().isoformat()}Z")
    
    # Run the ingestion in a background task to immediately return a response
    background_tasks.add_task(run_daily_ingestion)
    
    return {"message": "Daily data ingestion initiated in the background.", "timestamp": datetime.utcnow().isoformat() + "Z"}

# --- Pydantic Models for Agent Requests ---
class DeviceRequest(BaseModel):
    user_base_prompt: str = Field(..., description="The user's primary request or question.")
    location: str = Field(..., description="Geographical location for device search (e.g., 'Nairobi, Kenya').")
    budget: Optional[float] = Field(None, description="Maximum budget for the device.")
    # Add common optional fields that all or most agents might use
    brand: Optional[str] = None
    os_preference: Optional[str] = None
    colour: Optional[str] = None
    
class PhoneRequest(DeviceRequest):
    ram: Optional[str] = None
    storage: Optional[str] = None
    processor: Optional[str] = None
    battery: Optional[str] = None
    display: Optional[str] = None
    camera_priority: Optional[str] = None
    preferred_brands: Optional[List[str]] = None

class LaptopRequest(DeviceRequest):
    ram: Optional[str] = None
    storage: Optional[str] = None
    processor: Optional[str] = None
    gpu: Optional[str] = None
    display: Optional[str] = None
    battery: Optional[str] = None
    weight: Optional[str] = None
    build: Optional[str] = None # e.g., "rugged", "slim", "convertible"
    usage: Optional[str] = None # e.g., "gaming", "business", "student"
    preferred_brands: Optional[List[str]] = None

class TabletRequest(DeviceRequest):
    ram: Optional[str] = None
    storage: Optional[str] = None
    processor: Optional[str] = None
    display: Optional[str] = None
    battery: Optional[str] = None
    stylus_support: Optional[bool] = None
    connectivity: Optional[str] = None # e.g., "WiFi", "5G", "LTE"
    usage: Optional[str] = None
    preferred_brands: Optional[List[str]] = None
    camera_priority: Optional[str] = None

class EarpieceRequest(DeviceRequest):
    earpiece_type: Optional[str] = None # e.g., "headphones", "earbuds", "gaming headset"
    connectivity: Optional[str] = None # e.g., "wireless", "Bluetooth 5.3", "wired"
    battery_life: Optional[str] = None
    noise_cancellation: Optional[str] = None # "yes", "no", "high priority"
    mic_quality: Optional[str] = None # "high", "moderate", "not important"
    sound_profile: Optional[str] = None # "bass-heavy", "balanced", "vocal clarity"
    preferred_brands: Optional[List[str]] = None

class PreBuiltPCRequest(DeviceRequest):
    usage: Optional[str] = None # "gaming", "video editing", "office", "general"
    cpu_preference: Optional[str] = None # "Intel", "AMD", "no preference"
    gpu_requirement: Optional[str] = None # "high", "medium", "low", "integrated"
    ram_capacity: Optional[str] = None # "8GB", "16GB", "32GB"
    storage_size: Optional[str] = None # "512GB", "1TB", "2TB"
    preferred_brands: Optional[List[str]] = None
    monitor_included: Optional[bool] = None

class PCBuilderRequest(DeviceRequest):
    use_case: Optional[str] = None # "gaming", "video editing", "3D rendering", "office productivity", "general use"
    preferred_brands: Optional[List[str]] = None
    cpu_preference: Optional[str] = None
    gpu_preference: Optional[str] = None
    ram_capacity: Optional[str] = None
    ram_type: Optional[str] = None # "DDR4", "DDR5"
    storage_preference: Optional[str] = None # "speed", "capacity", "balanced"
    ssd_size_preference: Optional[str] = None # "512GB", "1TB"
    power_supply_preference: Optional[str] = None # "modular", "80+ Bronze"
    form_factor: Optional[str] = None # "ATX", "Micro-ATX", "Mini-ITX"
    cooling_type: Optional[str] = None # "air", "liquid"
    monitor_refresh_rate: Optional[str] = None # "60Hz", "144Hz"
    monitor_quality: Optional[str] = None # "IPS", "VA", "OLED"
    aesthetic_preference: Optional[str] = None # "RGB", "minimalist"
    peripherals_included: Optional[bool] = None


# --- UPDATED: Protected Agent Endpoints (Now require JWT) ---

@app.post("/find_phone", summary="Find recommended phones (Requires Auth)")
async def find_phone(
    request: PhoneRequest,
    current_user: dict = Depends(get_current_user)  # NEW: Require authentication
):
    # Ensure llm_instance is initialized
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not phone_agent:
        raise HTTPException(status_code=503, detail="Phone agent not initialized.")
    
    # Log authenticated user activity
    print(f"[AUTH] User '{current_user['username']}' searching for phones")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = phone_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id'])
            )
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Phone Agent processing: {str(e)}")

@app.post("/find_laptop", summary="Find recommended laptops (Requires Auth)")
async def find_laptop(
    request: LaptopRequest,
    current_user: dict = Depends(get_current_user)  # NEW
):
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not laptop_agent:
        raise HTTPException(status_code=503, detail="Laptop agent not initialized.")
    
    print(f"[AUTH] User '{current_user['username']}' searching for laptops")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = laptop_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id']))
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Laptop Agent processing: {str(e)}")

@app.post("/find_tablet", summary="Find recommended tablets (Requires Auth)")
async def find_tablet(
    request: TabletRequest,
    current_user: dict = Depends(get_current_user)  # NEW
):
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not tablet_agent:
        raise HTTPException(status_code=503, detail="Tablet agent not initialized.")
    
    print(f"[AUTH] User '{current_user['username']}' searching for tablets")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = tablet_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id']))
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Tablet Agent processing: {str(e)}")

@app.post("/find_earpiece", summary="Find recommended earpieces/headphones (Requires Auth)")
async def find_earpiece(
    request: EarpieceRequest,
    current_user: dict = Depends(get_current_user)  # NEW
):
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not earpiece_agent:
        raise HTTPException(status_code=503, detail="Earpiece agent not initialized.")
    
    print(f"[AUTH] User '{current_user['username']}' searching for earpieces")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = earpiece_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id']))
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Earpiece Agent processing: {str(e)}")

@app.post("/find_prebuilt_pc", summary="Find recommended pre-built PCs (Requires Auth)")
async def find_prebuilt_pc(
    request: PreBuiltPCRequest,
    current_user: dict = Depends(get_current_user)  # NEW
):
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not prebuilt_pc_agent:
        raise HTTPException(status_code=503, detail="Pre-built PC agent not initialized.")
    
    print(f"[AUTH] User '{current_user['username']}' searching for pre-built PCs")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = prebuilt_pc_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id']))
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Pre-built PC Agent processing: {str(e)}")

@app.post("/build_custom_pc", summary="Get recommendations for custom PC components (Requires Auth)")
async def build_custom_pc(
    request: PCBuilderRequest,
    current_user: dict = Depends(get_current_user)  # NEW
):
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")
    if not pc_builder_agent:
        raise HTTPException(status_code=503, detail="PC Builder agent not initialized.")
    
    print(f"[AUTH] User '{current_user['username']}' building a custom PC")
    UserStore.increment_search_count(current_user['username'])
    
    try:
        result_dict = pc_builder_agent.handle_request(
            request.dict(exclude_none=True),
            user_id=str(current_user['id']))
        return result_dict
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Agent could not produce valid final JSON: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in PC Builder Agent: {str(e)}")


# --- Chatbot Endpoint (NEW) ---
class ChatMessage(BaseModel):
    message: str

@app.post("/chat", summary="Interact with the DeviceFinder.ai chatbot (Requires Auth)")
async def chat_with_devicefinder(
    chat_message: ChatMessage,
    current_user: dict = Depends(get_current_user) # Authenticate user
):
    """
    Interact with the DeviceFinder.ai chatbot.
    
    This endpoint takes a user message, processes it through the chatbot,
    and returns a guided response. Memory is maintained per authenticated user.
    """
    if not llm_instance:
        raise HTTPException(status_code=503, detail="LLM Provider not initialized.")

    user_id = current_user["id"] # Get user ID from the authenticated user
    username = current_user["username"] # For logging/context

    print(f"Chatbot - User {username} ({user_id}) sent message: {chat_message.message[:100]}...")

    try:
        # Create a new chatbot instance per request.
        # It will automatically load memory based on user_id.
        chatbot = DeviceFinderChatbot(user_id=user_id, llm_provider=llm_instance)
        
        # Get response from the chatbot
        ai_response = chatbot.get_response(chat_message.message)
        
        return {"response": ai_response}

    except RateLimitExceeded as e:
        print(f"Chatbot - Rate limit exceeded for user {username} ({user_id}): {e.message}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{e.message}. Please try again after {e.retry_after} seconds."
        )
    except Exception as e:
        print(f"Chatbot - An unexpected error occurred for user {username} ({user_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing your request. Please try again."
        )

# --- Optional: Endpoint to clear user's chat history ---
@app.delete("/chat/clear_history", summary="Clear chat history for current user (Requires Auth)")
async def clear_chat_history(
    current_user: dict = Depends(get_current_user)
):
    """
    Clears the chat history for the currently authenticated user.
    """
    user_id = current_user["id"]
    username = current_user["username"]

    try:
        memory = DeviceFinderMemory(session_id=user_id)
        memory.clear_memory()
        print(f"Chatbot - Chat history cleared for user {username} ({user_id}).")
        return {"message": "Chat history cleared successfully."}
    except Exception as e:
        print(f"Chatbot - Error clearing chat history for user {username} ({user_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while clearing chat history."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)