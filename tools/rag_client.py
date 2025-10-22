"""
RAG Client for DeviceFinder.ai Chatbot
Fully async version — retrieves context from MCP server for chatbot queries
"""
import asyncio
import json
from typing import Dict, Any, Optional
import httpx


class RAGClient:
    """Async client for retrieving context from MCP RAG server"""

    def __init__(self, base_url: str = "https://mcp-final.onrender.com"):
        self.base_url = base_url.rstrip("/")
        self.timeout = 30.0
        print(f"→ RAGClient initialized with base_url: {self.base_url}")

    async def _send_mcp_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to MCP server."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }

        print(f"→ Sending MCP request: {method}")
        if params:
            param_preview = {
                k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v)
                for k, v in params.items()
            }
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
            raise Exception(f"Connection failed to {self.base_url}: {e}")
        except httpx.TimeoutException as e:
            raise Exception(f"Request timeout after {self.timeout}s: {e}")
        except httpx.RequestError as e:
            raise Exception(f"Request error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")

        if "error" in response_data:
            raise Exception(f"MCP Error: {response_data['error']}")

        return response_data.get("result", {})

    async def _send_direct_request(self, endpoint: str, payload: Dict) -> Dict[str, Any]:
        """Send direct request to FastAPI endpoint."""
        print(f"→ Sending direct request to {endpoint}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise Exception(f"Direct request to {endpoint} failed: {e}")

    async def retrieve_context(self, query: str, use_mcp: bool = True) -> Dict[str, Any]:
        """Retrieve context for a chatbot query."""
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

                        if "error" in parsed_result:
                            print(f"⚠️ MCP returned error: {parsed_result['error']}")
                            return {
                                "query": query,
                                "chunks_found": 0,
                                "context_chunks": [],
                                "warning": parsed_result["error"]
                            }

                        chunks_found = parsed_result.get("chunks_found", 0)
                        print(f"✓ Retrieved {chunks_found} context chunks via MCP")
                        print("=" * 60)
                        return parsed_result
                    else:
                        raise Exception("No content in MCP response")

                except Exception as mcp_error:
                    print(f"⚠️ MCP failed: {mcp_error}, trying direct API...")
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
            print(f"⚠️ Context retrieval failed: {str(e)}")
            print("=" * 60)
            return {
                "query": query,
                "chunks_found": 0,
                "context_chunks": [],
                "warning": str(e)
            }

    async def format_context_for_llm(self, context_data: Dict[str, Any]) -> str:
        """Format retrieved context for LLM consumption."""
        print("→ Formatting context for LLM")

        if context_data.get("chunks_found", 0) == 0:
            print("→ No context chunks available")
            return ""

        chunks = context_data.get("context_chunks", [])
        if not chunks:
            print("→ Empty chunks list")
            return ""

        formatted_chunks = [
            chunk.get("content", "").strip()
            for chunk in chunks if chunk.get("content", "").strip()
        ]

        if not formatted_chunks:
            print("→ No valid chunk content found")
            return ""

        formatted_context = (
            "Relevant context from knowledge base:\n\n" +
            "\n\n".join(formatted_chunks)
        )

        print(f"✓ Formatted context with {len(formatted_chunks)} chunks")
        return formatted_context


# Test the async client directly
if __name__ == "__main__":
    import sys

    print("\n" + "=" * 60)
    print("RAG Client Test Suite (Async)")
    print("=" * 60 + "\n")

    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    client = RAGClient(base_url=server_url)

    test_queries = [
        "What phones are available under 50000 KES?",
        "Tell me about gaming laptops",
        "What are the best wireless earbuds?"
    ]

    async def run_tests():
        for i, query in enumerate(test_queries, 1):
            print(f"\n{'=' * 60}")
            print(f"Test Query {i}: {query}")
            print('=' * 60)

            context_data = await client.retrieve_context(query)
            formatted_context = await client.format_context_for_llm(context_data)

            if formatted_context:
                print(f"\n--- Formatted Context for LLM ---")
                print(formatted_context)
                print(f"--- End of Context ---\n")
            else:
                print(f"\n--- No Context Retrieved ---\n")

    asyncio.run(run_tests())
    print("\n" + "=" * 60)
    print("✓ All tests completed")
    print("=" * 60 + "\n")
