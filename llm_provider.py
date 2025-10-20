import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
load_dotenv()

class LLMProvider:
  def __init__(self):
    "Initialise LLM Selection"
    gemini_key = os.getenv("GOOGLE_API_KEY")

    if not gemini_key:
      raise ValueError("Gemini API key not set")
    
    self.backup_model = ChatGoogleGenerativeAI(
      model="gemini-2.5-flash",
      google_api_key=gemini_key,
      temperature=0.7,
      max_output_tokens=2048
    )

    groq_key = os.getenv("GROQ_API_KEY")

    if not groq_key:
      raise ValueError("Groq API key not set")
    
    self.main_model = ChatGroq(
      model="llama-3.1-8b-instant",
      groq_api_key=groq_key,
      temperature=0.7,
      max_tokens=2048
    )

  def generate(self, message: str):
    try:
      try:
        response = self.main_model.invoke(message)
        if response and response.content:
            return response.content
        else:
            print(f"Main model returned empty content for message: {message[:100]}...")
            raise ValueError("Main model returned empty content")
      except Exception as e_main:
        print(f"Main model Failure due to: {e_main}. Attempting with backup model...")
        
        try:
            response = self.backup_model.invoke(message)
            if response and response.content:
                return response.content
            else:
                print(f"Backup model returned empty content for message: {message[:100]}...")
                raise ValueError("Backup model returned empty content")
        except Exception as e_backup:
            print(f"Total Model Failure: Both main and backup models failed due to: {e_backup}")
            return "" 

    except Exception as e_outer:
      print(f"Unexpected error in LLMProvider.generate: {e_outer}")
      return "" 

if __name__ == "__main__":
  llm_provider_test = LLMProvider()
  result = llm_provider_test.generate("What is JSON? Reply in only 30 words")
  print(f"\nTest 1 (Good): Result length: {len(result) if result else 0}")
  print(f"Result content: {result[:200]}...")