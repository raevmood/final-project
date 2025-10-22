"""
DeviceFinder.ai Chatbot with Async RAG Context Retrieval
"""
import asyncio
from typing import Optional
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate
)
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from utils.prompts import chatbot_prompt
from utils.memory import DeviceFinderMemory
from utils.llm_provider import LLMProvider
from tools.rag_client import RAGClient


class DeviceFinderChatbot:
    def __init__(self, user_id: int, llm_provider: LLMProvider, rag_client: Optional[RAGClient] = None):
        """
        Initialize the DeviceFinder chatbot.
        """
        self.user_id = user_id
        self.llm_provider = llm_provider
        self.rag_client = rag_client
        self.memory = DeviceFinderMemory(session_id=user_id, max_messages=6)
        self.system_prompt_content = chatbot_prompt

        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(self.system_prompt_content),
                MessagesPlaceholder(variable_name="chat_history"),
                HumanMessagePromptTemplate.from_template("{user_input}")
            ]
        )

    async def get_response(self, user_input: str) -> str:
        """
        Generates a response from the LLM, incorporating memory, RAG context, and system prompt.
        """
        # Add user message to memory
        self.memory.add_user_message(user_input)

        # Retrieve RAG context (async)
        rag_context = ""
        if self.rag_client:
            try:
                print(f"[RAG] Retrieving context for user {self.user_id}")
                rag_context = await self.rag_client.retrieve_formatted_context(user_input)

                if rag_context:
                    print(f"[RAG] Context retrieved successfully ({len(rag_context)} chars)")
                else:
                    print(f"[RAG] No relevant context found")

            except Exception as e:
                print(f"[RAG] Error retrieving context: {e}")
                rag_context = ""
        else:
            print(f"[RAG] RAG client not available for user {self.user_id}")

        # Get recent chat history
        chat_history = self.memory.get_recent_messages_for_prompt()

        # Format the full prompt
        formatted_prompt = self.prompt_template.format_messages(
            chat_history=chat_history[:-1],
            user_input=user_input
        )

        try:
            # Build the message string for LLM input
            message_parts = []
            for msg in formatted_prompt:
                if isinstance(msg, SystemMessage):
                    message_parts.append(f"System: {msg.content}")
                elif isinstance(msg, HumanMessage):
                    message_parts.append(f"User: {msg.content}")
                elif isinstance(msg, AIMessage):
                    message_parts.append(f"Assistant: {msg.content}")

            # Insert RAG context (after system message)
            if rag_context and len(message_parts) > 0:
                rag_section = f"\n[Knowledge Base Context]\n{rag_context}\n[End Context]\n"
                message_parts.insert(1, rag_section)

            message_string = "\n".join(message_parts)

            # Generate response asynchronously (in case llm_provider is sync)
            llm_response_content = await asyncio.to_thread(
                self.llm_provider.generate, message_string, str(self.user_id)
            )

            # Add AI response to memory
            self.memory.add_ai_message(llm_response_content)

            return llm_response_content

        except Exception as e:
            print(f"Error generating LLM response for user {self.user_id}: {e}")
            # Roll back last user message if generation failed
            if self.memory.messages and self.memory.messages[-1].type == "human":
                self.memory.messages.pop()
                self.memory.save_memory()

            return (
                "I’m sorry — I’m having trouble generating a response right now. "
                "Please try again in a moment."
            )


if __name__ == "__main__":
    print(chatbot_prompt)
