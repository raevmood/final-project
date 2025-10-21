# device_finder_chatbot.py
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from prompts import chatbot_prompt
from memory import DeviceFinderMemory
from llm_provider import LLMProvider 

class DeviceFinderChatbot:
    def __init__(self, user_id: int, llm_provider: LLMProvider):
        self.user_id = user_id
        self.llm_provider = llm_provider
        self.memory = DeviceFinderMemory(session_id=user_id, max_messages=6) 
        self.system_prompt_content = chatbot_prompt

        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(self.system_prompt_content),
                MessagesPlaceholder(variable_name="chat_history"),
                HumanMessagePromptTemplate.from_template("{user_input}")
            ]
        )

    def get_response(self, user_input: str) -> str:
        """
        Generates a response from the LLM, incorporating memory and system prompt.
        
        Args:
            user_input: The current message from the user.
            
        Returns:
            The chatbot's generated response.
        """
        self.memory.add_user_message(user_input)
        chat_history = self.memory.get_recent_messages_for_prompt()
        
        formatted_prompt = self.prompt_template.format_messages(
            chat_history=chat_history[:-1], 
            user_input=user_input
        )
        
        try:
            
            message_string = ""
            for msg in formatted_prompt:
                if isinstance(msg, SystemMessagePromptTemplate):
                    message_string += f"System: {msg.content}\n"
                elif isinstance(msg, HumanMessage):
                    message_string += f"User: {msg.content}\n"
                elif isinstance(msg, AIMessage):
                    message_string += f"Assistant: {msg.content}\n"
            
            llm_response_content = self.llm_provider.generate(message_string, user_id=str(self.user_id))
            self.memory.add_ai_message(llm_response_content)
            return llm_response_content

        except Exception as e:
            print(f"Error generating LLM response for user {self.user_id}: {e}")
            if self.memory.messages and self.memory.messages[-1].type == "human":
                self.memory.messages.pop()
                self.memory.save_memory() 
            return "I apologize, but I'm having trouble connecting right now. Please try again in a moment."