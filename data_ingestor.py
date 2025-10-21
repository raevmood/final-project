# data_ingestor.py (Refactored)
import json
import re # For basic price extraction, replace with LLM as discussed
from datetime import datetime
from typing import List, Dict, Any, Optional

from vector_db_tool import VectorDBTool
from serper_tool import SerperSearchTool
from llm_provider import LLMProvider # Import your LLM provider
from config import PRESET_SEARCH_QUERIES
import time

# --- Helper function for LLM-based parsing (CRITICAL for robust ingestion) ---
def parse_serper_result_with_llm(llm_provider: LLMProvider, item: Dict[str, str], category: str) -> Optional[Dict[str, Any]]:
    """
    Uses LLM to parse a single Serper search result into a structured device dictionary.
    """
    prompt = f"""
    Analyze the following search result from a web search for a {category}:
    
    Title: {item.get('title', 'N/A')}
    Link: {item.get('link', 'N/A')}
    Snippet: {item.get('snippet', 'N/A')}
    
    Extract the following information as a JSON object:
    - `name`: The product name.
    - `brand`: The brand of the product.
    - `price`: The price (as a number, convert from any currency symbol if present, e.g., "KES 45,000" -> 45000). If not clearly stated, infer or set to 0.
    - `vendor`: The online vendor/store name.
    - `url`: The product's URL.
    - `specs`: A dictionary of key specifications (e.g., "ram", "storage", "processor", "display", "battery", "gpu"). Extract as much detail as possible from the snippet.
    - `physical_store`: Name of a physical store if mentioned, otherwise 'Online via the extracted vendor'.
    - `store_contact`: Phone or email for physical store if mentioned.

    If you cannot find a price or if the result does not appear to be a product listing (e.g., it's a review, news, or general info), return an empty JSON object {{}}.
    Return ONLY the JSON object. Do not add any conversational text or markdown.
    “Respond with only one valid JSON object, with no Markdown code fences, no extra text, and no multiple JSON blocks. Each field must have a value; if unknown, use an empty string "" instead of null.”
    """
    
    try:
        llm_response = llm_provider.generate(prompt)
        parsed_data = json.loads(llm_response)
        
        # Basic validation: ensure it's a product and has a name
        if not parsed_data or not parsed_data.get('name'):
            return None
        
        # Ensure price is a float
        if 'price' in parsed_data:
            try:
                parsed_data['price'] = float(parsed_data['price'])
            except (ValueError, TypeError):
                parsed_data['price'] = 0.0 # Default if parsing fails

        # Handle 'specs' if it was returned as a string or empty
        if isinstance(parsed_data.get('specs'), str):
            try:
                parsed_data['specs'] = json.loads(parsed_data['specs'])
            except json.JSONDecodeError:
                parsed_data['specs'] = {"raw_llm_extract": parsed_data['specs']} # Keep raw if malformed
        elif not isinstance(parsed_data.get('specs'), dict):
            parsed_data['specs'] = {} # Ensure it's a dictionary
            
        return parsed_data
    except json.JSONDecodeError as e:
        print(f"LLM parsing failed (JSON error): {e} for item: {item.get('title')}. LLM response: {llm_response[:500]}")
        return None
    except Exception as e:
        print(f"Error during LLM parsing: {e} for item: {item.get('title')}")
        return None


def run_daily_ingestion():
    """
    Fetches data using Serper for preset queries and adds/updates the vector database.
    This function will be called by the FastAPI endpoint.
    """
    print(f"Starting daily data ingestion via n8n trigger at {datetime.utcnow().isoformat()}Z")
    
    serper_tool = SerperSearchTool()
    vector_db_tool = VectorDBTool()
    llm_provider = LLMProvider() # Initialize LLM for parsing Serper results

    total_added_devices = 0
    
    for category, queries in PRESET_SEARCH_QUERIES.items():
        print(f"\n--- Ingesting data for category: {category} ---")
        vector_db_tool.cleanup_old_devices(category, days_old=7) # Clean up old data before adding new

        for q_item in queries:
            query_str = q_item["query"]
            location = q_item["location"]
            price_max_filter = q_item.get("price_max")

            print(f"  Searching for: '{query_str}' in '{location}' (price_max: {price_max_filter})...")
            
            raw_serper_results = serper_tool.search_devices(
                category=category,
                specifications=query_str,
                location=location,
                price_range=f"under {price_max_filter} KES" if price_max_filter else None,
                num_results=10
            )

            if not raw_serper_results:
                print(f"    No Serper results for '{query_str}'. Skipping.")
                time.sleep(1) # Still rate limit even on no results
                continue
            
            processed_devices: List[Dict[str, Any]] = []
            for item in raw_serper_results:
                # Use LLM to parse each serper result
                parsed_device = parse_serper_result_with_llm(llm_provider, item, category)
                if parsed_device:
                    processed_devices.append(parsed_device)

            if processed_devices:
                added_count = vector_db_tool.add_devices(processed_devices, category, location)
                total_added_devices += added_count
                print(f"    Added {added_count} devices to DB for query: '{query_str}'")
            time.sleep(serper_tool.min_request_interval) # Respect serper tool's internal rate limit

    print(f"\nFinished daily data ingestion. Total devices added/updated: {total_added_devices}")
    return {"status": "success", "total_devices_ingested": total_added_devices}

if __name__ == "__main__":
    # For local testing of the ingestion function directly
    result = run_daily_ingestion()
    print(result)