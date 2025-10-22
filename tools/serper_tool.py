"""
Enhanced Serper Search Tool with structured result extraction.
"""
import requests
import json
import os
from typing import Optional, Dict, Any, List
import time
from dotenv import load_dotenv
load_dotenv()


class SerperSearchTool:
    """Enhanced search tool using Serper API with result validation."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Serper search tool."""
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("Serper API key not found. Set SERPER_API_KEY environment variable.")
        
        self.base_url = "https://google.serper.dev/search"
        self.last_request_time = 0
        self.min_request_interval = 1.0 

    def _rate_limit(self):
        """Implement simple rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()

    def search(
        self,
        query: str,
        num_results: int = 10,
        gl: Optional[str] = None,
        hl: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform a search using Serper with location awareness.
        
        Args:
            query: Search query string
            num_results: Number of results to return
            gl: Country code (e.g. 'us', 'ke')
            hl: Language code (e.g. 'en')
            location: Location to append to query (e.g. "Nairobi, Kenya")
        """
        self._rate_limit()
        enhanced_query = f"{query} {location}" if location else query
        
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {"q": enhanced_query, "num": num_results}
        if gl:
            payload["gl"] = gl
        if hl:
            payload["hl"] = hl

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "status": "failed"}

    def search_devices(
        self,
        category: str,
        specifications: str,
        location: str,
        price_range: Optional[str] = None,
        num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for devices with structured query building.
        
        Args:
            category: Device category (phone, laptop, tablet, etc.)
            specifications: Required specs (e.g., "8GB RAM 256GB storage")
            location: Location for search
            price_range: Optional price range (e.g., "under 50000")
            num_results: Number of results
            
        Returns:
            List of search results with title, link, snippet
        """
        query_parts = [category, specifications]
        if price_range:
            query_parts.append(price_range)
        query_parts.extend(["buy", "price", location])
        
        query = " ".join(query_parts)
        country_codes = {
            "Kenya": "ke",
            "Nairobi": "ke",
            "Uganda": "ug",
            "Tanzania": "tz"
        }
        gl = next((code for loc, code in country_codes.items() if loc in location), None)
        
        results = self.search(query, num_results=num_results, gl=gl, location=location)
        
        if "error" in results:
            return []
        organic = results.get("organic", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "position": item.get("position", 0)
            }
            for item in organic
        ]

    def get_organic_results(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """Get only the organic search results (backward compatible)."""
        results = self.search(query, num_results)
        if "error" in results:
            return []
        return results.get("organic", [])

    def format_results(self, results: List[Dict[str, str]]) -> str:
        """Format search results as a readable string."""
        if not results:
            return "No results found."

        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. {result.get('title', 'No title')}\n"
                f"   URL: {result.get('link', 'No link')}\n"
                f"   {result.get('snippet', 'No snippet')}\n"
            )
        return "\n".join(formatted)
    
    def validate_result_quality(self, results: List[Dict[str, Any]]) -> bool:
        """
        Check if search results contain sufficient product information.
        
        Returns True if results seem to contain product listings.
        """
        if not results:
            return False
        product_keywords = ["price", "buy", "ksh", "$", "shop", "store", "specifications"]
        
        relevant_count = 0
        for result in results[:5]: 
            snippet = result.get("snippet", "").lower()
            if any(keyword in snippet for keyword in product_keywords):
                relevant_count += 1
        
        return relevant_count >= 2 


if __name__ == "__main__":
    tool = SerperSearchTool()
    results = tool.search_devices(
        category="smartphone",
        specifications="8GB RAM 128GB storage",
        location="Nairobi, Kenya",
        price_range="under 50000 KES",
        num_results=5
    )
    
    print(f"Found {len(results)} results")
    print("\nValidation:", tool.validate_result_quality(results))
    print("\nFormatted results:")
    print(tool.format_results(results))

    