from llm_provider import LLMProvider as LLM
from prompts import phone_prompt, laptop_prompt, tablet_prompt, earpiece_prompt, pc_builder_prompt
import json

class BaseAgent:
    def __init__(self, llm):
        self.llm = llm
        self.tools = {}

    def register_tool(self, name, tool):
        """Register an external tool the agent can use."""
        self.tools[name] = tool

    def contact(self, prompt):
        result = self.llm.generate(prompt)
        return result

class PhoneAgent(BaseAgent):
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.phone_prompt = prompt_template


    def handle_request(self, user_request: str):
        """Full reasoning pipeline with Vector DB first, then web search."""
        
        # Step 1: Try Vector DB first
        vector_tool = self.tools.get("vector_db")
        if vector_tool:
            extraction_prompt = f"""
            Extract location and budget from: "{user_request}"
            Return JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            try:
                params = json.loads(params_raw)
                vector_results = vector_tool.query_devices(
                    query=user_request,
                    category="phone",
                    location=params.get("location", ""),
                    price_max=params.get("budget"),
                    top_k=5
                )
                
                if len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
                else:
                    vector_results = None
            except:
                vector_results = None
        if not vector_results or len(vector_results) < 3:
            search_decision_prompt = f"""
            You are a phone-finding assistant. The user asked: "{user_request}".
            Create a search query for finding phones. Return JSON:
            {{"search_query": "<query string>"}}
            """
            decision_raw = self.contact(search_decision_prompt)
            try:
                decision = json.loads(decision_raw)
                search_query = decision.get("search_query")
            except:
                search_query = user_request
            
            search_tool = self.tools.get("serper")
            search_results = search_tool.get_organic_results(search_query, num_results=5)
            formatted_results = search_tool.format_results(search_results)
            source = "Web Search"
        full_prompt = f"""
        {self.phone_prompt}
        
        User request: {user_request}
        Data source: {source}
        
        Retrieved information:
        {formatted_results}
        
        Now synthesize the final JSON recommendation output following the exact format specified.
        """
        
        response = self.contact(full_prompt)
        return response