# memory.py
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from typing import List
import json
import os
from datetime import datetime

class DeviceFinderMemory:
    def __init__(self, session_id: str, max_messages: int = 6, persist_path: str = "./chat_memory"):
        """Initialize memory manager"""
        self.session_id = str(session_id) # Ensure session_id is string
        self.max_messages = max_messages # Now stores 3 user and 3 AI messages
        self.persist_path = persist_path
        self.messages: List[BaseMessage] = []
        
        # Create memory directory
        os.makedirs(persist_path, exist_ok=True)
        
        # Load existing conversation
        self.load_memory()
    
    def add_message(self, message: BaseMessage) -> None:
        """Add message to memory"""
        self.messages.append(message)
        
        # Keep only recent messages (max_messages will represent 3 user + 3 AI)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        # Auto-save
        self.save_memory()
    
    def add_user_message(self, content: str) -> None:
        """Add user message"""
        self.add_message(HumanMessage(content=content))
    
    def add_ai_message(self, content: str) -> None:
        """Add AI response"""
        self.add_message(AIMessage(content=content))
    
    def get_messages(self) -> List[BaseMessage]:
        """Get all messages"""
        return self.messages.copy()
    
    def get_recent_messages_for_prompt(self, count: int = 6) -> List[BaseMessage]:
        """
        Get recent messages suitable for LangChain's `MessagesPlaceholder`
        Adjusted to retrieve exactly `count` messages if available.
        """
        return self.messages[-count:]
    
    def clear_memory(self) -> None:
        """Clear conversation history"""
        self.messages = []
        self.save_memory()
    
    def save_memory(self) -> None:
        """Save memory to file"""
        try:
            file_path = os.path.join(self.persist_path, f"{self.session_id}.json")
            
            data = {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "messages": []
            }
            
            for msg in self.messages:
                data["messages"].append({
                    "type": msg.type,
                    "content": msg.content
                })
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"DeviceFinderMemory save error for session {self.session_id}: {e}")
    
    def load_memory(self) -> None:
        """Load memory from file"""
        try:
            file_path = os.path.join(self.persist_path, f"{self.session_id}.json")
            
            if not os.path.exists(file_path):
                self.messages = [] # Ensure messages are empty if no file exists
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.messages = []
            for msg_data in data.get("messages", []):
                if msg_data["type"] == "human":
                    self.messages.append(HumanMessage(content=msg_data["content"]))
                elif msg_data["type"] == "ai":
                    self.messages.append(AIMessage(content=msg_data["content"]))
                    
        except Exception as e:
            print(f"DeviceFinderMemory load error for session {self.session_id}: {e}")
            self.messages = [] # Proceed without memory if load fails