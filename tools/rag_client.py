import aiohttp
import asyncio
from typing import List, Dict, Any, Optional


class RAGClient:
    def __init__(self, api_url: str, embedding_model: Any, db_client: Any):
        self.api_url = api_url
        self.embedding_model = embedding_model
        self.db_client = db_client

    async def embed_query(self, query: str) -> List[float]:
        """Embed a query asynchronously using the embedding model."""
        return await self.embedding_model.embed_query(query)

    async def retrieve_context(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieve relevant context documents from the database."""
        try:
            query_vector = await self.embed_query(query)
            results = await self.db_client.similarity_search(query_vector, limit=limit)
            return results
        except Exception as e:
            print(f"[RAG] Error retrieving context: {e}")
            return []

    async def format_context_for_llm(self, docs: List[Dict[str, Any]]) -> str:
        """Format retrieved context into a single text block for LLM input."""
        if not docs:
            return "No relevant context found."
        formatted = "\n\n".join([f"Context {i+1}:\n{doc.get('content', '')}" for i, doc in enumerate(docs)])
        return f"Retrieved Context:\n{formatted}"

    async def retrieve_formatted_context(self, query: str) -> str:
        """Helper that combines retrieval and formatting into one call."""
        docs = await self.retrieve_context(query)
        return await self.format_context_for_llm(docs)


