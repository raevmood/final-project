"""
RAG Client for DeviceFinder.ai Chatbot
Retrieves context from MCP server for chatbot queries
"""
import asyncio
import json
from typing import Dict, Any, Optional, List
import httpx


class RAGClient:
    """Client for retrieving context from MCP RAG server"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        """
        Initialize RAG client.
        
        Args:
            base_url: Base URL of the MCP RAG server
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = 30.0
        print(f"→ RAGClient initialized with base_url: {self.base_url}")
    
    async def _send_mcp_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send JSON-RPC request to MCP server.
        
        Args:
            method: MCP method name
            params: Method parameters
        
        Returns:
            MCP response result
        """
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        
        print(f"→ Sending MCP request: {method}")
        if params:
            param_preview = {k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v) 
                           for k, v in params.items()}
            print(f"→ Params preview: {param_preview}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/mcp/tools/call",
                    json=request
                )
                response.raise_for_status()
                response_data = response.json()
            
            print(f"✓ MCP request completed successfully")
            
        except httpx.ConnectError as e:
            error_msg = f"Connection failed to {self.base_url}: {e}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout after {self.timeout}s: {e}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        
        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        
        # Check for JSON-RPC error
        if "error" in response_data:
            error_msg = f"MCP Error: {response_data['error']}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        
        return response_data.get("result", {})
    
    async def _send_direct_request(self, endpoint: str, payload: Dict) -> Dict[str, Any]:
        """
        Send direct request to FastAPI endpoints (non-MCP).
        
        Args:
            endpoint: API endpoint path
            payload: Request payload
        
        Returns:
            Response data
        """
        print(f"→ Sending direct request to {endpoint}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    json=payload
                )
                response.raise_for_status()
                response_data = response.json()
            
            print(f"✓ Direct request completed successfully")
            return response_data
        
        except Exception as e:
            error_msg = f"Direct request to {endpoint} failed: {e}"
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
    
    async def retrieve_context(self, query: str, use_mcp: bool = True) -> Dict[str, Any]:
        """
        Retrieve context for a chatbot query.
        
        Args:
            query: User's query or message
            use_mcp: Use MCP protocol (True) or direct API (False)
        
        Returns:
            Dict with context chunks and metadata. 
            Always returns a dict with: {"query": str, "chunks_found": int, "context_chunks": list}
        """
        print("=" * 60)
        print(f"→ Retrieving context for query: '{query[:100]}...'")
        print(f"→ Using {'MCP protocol' if use_mcp else 'direct API'}")
        
        try:
            if use_mcp:
                try:
                    result = await self._send_mcp_request(
                        "tools/call",
                        {
                            "name": "retrieve_context",
                            "arguments": {"query": query}
                        }
                    )
                    
                    if "content" in result and len(result["content"]) > 0:
                        content_text = result["content"][0].get("text", "{}")
                        parsed_result = json.loads(content_text)
                        
                        # Check if MCP returned an error in the content
                        if "error" in parsed_result:
                            print(f"⚠️  MCP returned error: {parsed_result['error']}")
                            return {
                                "query": query,
                                "chunks_found": 0,
                                "context_chunks": [],
                                "warning": parsed_result['error']
                            }
                        
                        chunks_found = parsed_result.get("chunks_found", 0)
                        print(f"✓ Retrieved {chunks_found} context chunks via MCP")
                        print("=" * 60)
                        return parsed_result
                    else:
                        raise Exception("No content in MCP response")
                
                except Exception as mcp_error:
                    print(f"⚠️  MCP failed: {mcp_error}, trying direct API...")
                    use_mcp = False
            
            if not use_mcp:
                direct_result = await self._send_direct_request(
                    "/retrieve_context",
                    {"query": query}
                )
                
                chunks_found = direct_result.get("chunks_found", 0)
                print(f"✓ Retrieved {chunks_found} context chunks via direct API")
                print("=" * 60)
                return direct_result
        
        except Exception as e:
            error_msg = f"Context retrieval failed: {str(e)}"
            print(f"⚠️  {error_msg}")
            print("=" * 60)
            # Return empty result - chatbot continues without context
            return {
                "query": query,
                "chunks_found": 0, 
                "context_chunks": [],
                "warning": error_msg
            }
    
    async def format_context_for_llm(self, context_data: Dict[str, Any]) -> str:
        """
        Format retrieved context for LLM consumption.
        
        Args:
            context_data: Context data from retrieve_context
        
        Returns:
            Formatted string ready for LLM prompt. Returns empty string if no context.
        """
        print("→ Formatting context for LLM")
        
        # Check if there's any context
        if context_data.get("chunks_found", 0) == 0:
            print("→ No context chunks available")
            return ""
        
        chunks = context_data.get("context_chunks", [])
        if not chunks:
            print("→ Empty chunks list")
            return ""
        
        # Extract and format valid chunks
        formatted_chunks = []
        for chunk in chunks:
            content = chunk.get("content", "").strip()
            if content:
                formatted_chunks.append(content)
        
        if not formatted_chunks:
            print("→ No valid chunk content found")
            return ""
        
        # Build formatted context
        query = context_data.get("query", "")
        formatted_context = f"Relevant context from knowledge base:\n\n"
        formatted_context += "\n\n".join(formatted_chunks)
        
        print(f"✓ Formatted context with {len(formatted_chunks)} chunks")
        return formatted_context
    
    def retrieve_context_sync(self, query: str) -> str:
        """
        Synchronous wrapper for context retrieval and formatting.
        Returns empty string if no context found or on error.
        
        Args:
            query: User's query
        
        Returns:
            Formatted context string (empty if no context or error)
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            context_data = loop.run_until_complete(self.retrieve_context(query))
            formatted_context = loop.run_until_complete(self.format_context_for_llm(context_data))
            
            loop.close()
            return formatted_context
        
        except Exception as e:
            print(f"✗ Error in sync context retrieval: {e}")
            return ""


# Legacy function for backwards compatibility
def retrieve_context_sync(client: RAGClient, query: str) -> str:
    """
    Legacy synchronous wrapper - use RAGClient.retrieve_context_sync() instead.
    
    Args:
        client: RAGClient instance
        query: User's query
    
    Returns:
        Formatted context string (empty if no context or error)
    """
    return client.retrieve_context_sync(query)


if __name__ == "__main__":
    """Test the RAG client"""
    import sys
    
    print("\n" + "=" * 60)
    print("RAG Client Test Suite")
    print("=" * 60 + "\n")
    
    # Get MCP server URL
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    else:
        server_url = "http://localhost:8001"
        print(f"Using default server URL: {server_url}")
        print("Usage: python rag_client.py <server_url>\n")
    
    # Initialize client
    client = RAGClient(base_url=server_url)
    
    # Test queries
    test_queries = [
        "What phones are available under 50000 KES?",
        "Tell me about gaming laptops",
        "What are the best wireless earbuds?"
    ]
    
    print("Running test queries...\n")
    
    async def run_tests():
        for i, query in enumerate(test_queries, 1):
            print(f"\n{'=' * 60}")
            print(f"Test Query {i}: {query}")
            print('=' * 60)
            
            # Retrieve context
            context_data = await client.retrieve_context(query)
            
            # Format for LLM
            formatted_context = await client.format_context_for_llm(context_data)
            
            if formatted_context:
                print(f"\n--- Formatted Context for LLM ---")
                print(formatted_context)
                print(f"--- End of Context ---\n")
            else:
                print(f"\n--- No Context Retrieved ---\n")
    
    # Run tests
    try:
        asyncio.run(run_tests())
        print("\n" + "=" * 60)
        print("✓ All tests completed")
        print("=" * 60 + "\n")
    except KeyboardInterrupt:
        print("\n\n✗ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n✗ Tests failed with error: {e}")
        import traceback
        traceback.print_exc()