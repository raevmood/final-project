# main.py
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, Field
from fastapi import Depends

from dotenv import load_dotenv
load_dotenv() # Load environment variables early
from fastapi.middleware.cors import CORSMiddleware
# Import your core components
from llm_provider import LLMProvider
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

app = FastAPI(
    title="DeviceFinder.AI API",
    description="AI-powered multi-agent system for finding and recommending electronic devices.",
    version="1.0.0"
)

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://raevmood.github.io/final-frontend/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origins],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

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

        print("All components and agents initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize components: {e}")
        # Depending on severity, you might want to re-raise or handle gracefully.
        # For a production system, this could prevent the app from starting.
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
    return {"message": "DeviceFinder.AI API is running. Visit /docs for API details."}

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


# --- Agent Endpoints ---

@app.post("/find_phone", summary="Find recommended phones")
async def find_phone(request: PhoneRequest):
    if not phone_agent:
        raise HTTPException(status_code=503, detail="Phone agent not initialized.")
    try:
        raw_result = phone_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Phone Agent: {str(e)}")

@app.post("/find_laptop", summary="Find recommended laptops")
async def find_laptop(request: LaptopRequest):
    if not laptop_agent:
        raise HTTPException(status_code=503, detail="Laptop agent not initialized.")
    try:
        raw_result = laptop_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Laptop Agent: {str(e)}")

@app.post("/find_tablet", summary="Find recommended tablets")
async def find_tablet(request: TabletRequest):
    if not tablet_agent:
        raise HTTPException(status_code=503, detail="Tablet agent not initialized.")
    try:
        raw_result = tablet_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Tablet Agent: {str(e)}")

@app.post("/find_earpiece", summary="Find recommended earpieces/headphones")
async def find_earpiece(request: EarpieceRequest):
    if not earpiece_agent:
        raise HTTPException(status_code=503, detail="Earpiece agent not initialized.")
    try:
        raw_result = earpiece_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Earpiece Agent: {str(e)}")

@app.post("/find_prebuilt_pc", summary="Find recommended pre-built PCs")
async def find_prebuilt_pc(request: PreBuiltPCRequest):
    if not prebuilt_pc_agent:
        raise HTTPException(status_code=503, detail="Pre-built PC agent not initialized.")
    try:
        raw_result = prebuilt_pc_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in Pre-built PC Agent: {str(e)}")

@app.post("/build_custom_pc", summary="Get recommendations for custom PC components")
async def build_custom_pc(request: PCBuilderRequest):
    if not pc_builder_agent:
        raise HTTPException(status_code=503, detail="PC Builder agent not initialized.")
    try:
        raw_result = pc_builder_agent.handle_request(request.dict(exclude_none=True))
        return json.loads(raw_result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Agent returned invalid JSON: {raw_result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in PC Builder Agent: {str(e)}")

# Add `Depends` for authentication
from fastapi import Depends

if __name__ == "__main__":
    import uvicorn
    # To run locally, you can specify host and port directly.
    # The reload=True argument is great for development as it restarts the server
    # automatically on code changes.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)