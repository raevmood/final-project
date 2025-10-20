"""
Manual agent implementation for DeviceFinder.AI system.
Simple, transparent agents with tool access.
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import re # <--- ADD THIS IMPORT

class BaseAgent:
    """Base agent class with tool registration and common utilities."""
    
    def __init__(self, llm):
        self.llm = llm
        self.tools = {}
    
    def register_tool(self, name, tool):
        """Register an external tool the agent can use."""
        if tool is None:
            raise ValueError(f"Cannot register None as tool '{name}'")
        self.tools[name] = tool
        print(f"✓ Registered tool: {name}")
    
    def contact(self, prompt):
        """Contact the LLM with a prompt."""
        result = self.llm.generate(prompt)
        return result

    def _extract_json_from_markdown(self, text: str) -> str:
        """
        Extracts a JSON string from text that might be wrapped in markdown code blocks.
        Assumes the first JSON block is the desired one.
        """
        match = re.search(r"```json\s*\n({.*})\n```", text, re.DOTALL)
        if match:
            return match.group(1)
        
        # If no markdown block, return original text (might still be valid JSON)
        return text


class PhoneAgent(BaseAgent):
    """Phone finder agent with vector DB and web search."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.phone_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]: 
        """Full reasoning pipeline with Vector DB first, then web search fallback."""
        try:
            # Step 1: Extract parameters from user request
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget from this request:
            {user_request_str}
            
            Return ONLY valid JSON in this format:
            {{"location": "City, Country", "budget": number}}
            """
            
            params_raw_llm_response = self.contact(extraction_prompt)
            params_raw_cleaned = self._extract_json_from_markdown(params_raw_llm_response)
            
            try:
                params = json.loads(params_raw_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except json.JSONDecodeError:
                print(f"WARNING: PhoneAgent - Failed to parse params_raw JSON (from LLM): {params_raw_llm_response[:200]}... Cleaned: {params_raw_cleaned[:200]}...")
                location = user_request.get("location", "")
                budget = user_request.get("budget")
            except Exception as e:
                print(f"ERROR: PhoneAgent - Error during parameter extraction: {e}. Raw LLM: {params_raw_llm_response[:200]}...")
                location = user_request.get("location", "")
                budget = user_request.get("budget")
            
            # Step 2: Try Vector DB first
            formatted_results = None
            source = None
            vector_tool = self.tools.get("vector_db")
            
            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="phone",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                
                # If we have good results (3+ devices), use them
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
            
            # Step 3: If Vector DB insufficient, use Serper
            if not formatted_results:
                search_decision_prompt = f"""
                Create a search query for finding phones based on:
                {user_request_str}
                
                Return ONLY valid JSON:
                {{"search_query": "your query here"}}
                """
                
                decision_raw_llm_response = self.contact(search_decision_prompt)
                decision_raw_cleaned = self._extract_json_from_markdown(decision_raw_llm_response)
                
                try:
                    decision = json.loads(decision_raw_cleaned)
                    search_query = decision.get("search_query", "")
                except json.JSONDecodeError:
                    print(f"WARNING: PhoneAgent - Failed to parse search_decision JSON (from LLM): {decision_raw_llm_response[:200]}... Cleaned: {decision_raw_cleaned[:200]}...")
                    # Fallback: construct query from request
                    specs = f"{user_request.get('ram', '')} {user_request.get('storage', '')} smartphone"
                    search_query = f"{specs} {location} under {budget}"
                except Exception as e:
                    print(f"ERROR: PhoneAgent - Error during search query decision: {e}. Raw LLM: {decision_raw_llm_response[:200]}...")
                    specs = f"{user_request.get('ram', '')} {user_request.get('storage', '')} smartphone"
                    search_query = f"{specs} {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"
            
            # Step 4: Generate final recommendation
            full_prompt = f"""
            {self.phone_prompt}
            
            User request:
            {user_request_str}
            
            Data source: {source}
            
            Retrieved information:
            {formatted_results}
            
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Now synthesize the final JSON recommendation output following the exact format specified in the prompt.
            Return ONLY valid JSON, no markdown or extra text.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: PhoneAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                # If the LLM consistently fails to return valid JSON, you might need to refine your prompt
                # or add more robust parsing/correction logic. For now, raise an error.
                raise ValueError("Final AI response was not valid JSON.")
            
        except Exception as e:
            # If any other error occurs during the handling, return a dictionary describing the error.
            # FastAPI will then correctly serialize this dictionary to JSON.
            return {
                "error": str(e),
                "status": "failed",
                "user_request": user_request
            }


class LaptopAgent(BaseAgent):
    """Laptop finder agent with vector DB and web search."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.laptop_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        """Full reasoning pipeline with Vector DB first, then web search fallback."""
        try:
            user_request_str = json.dumps(user_request, indent=2)
            
            # Extract parameters
            extraction_prompt = f"""
            Extract location and budget from: {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw_llm_response = self.contact(extraction_prompt)
            params_raw_cleaned = self._extract_json_from_markdown(params_raw_llm_response)
            
            try:
                params = json.loads(params_raw_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except json.JSONDecodeError:
                print(f"WARNING: LaptopAgent - Failed to parse params_raw JSON (from LLM): {params_raw_llm_response[:200]}... Cleaned: {params_raw_cleaned[:200]}...")
                location = user_request.get("location", "")
                budget = user_request.get("budget")
            except Exception as e:
                print(f"ERROR: LaptopAgent - Error during parameter extraction: {e}. Raw LLM: {params_raw_llm_response[:200]}...")
                location = user_request.get("location", "")
                budget = user_request.get("budget")
            
            # Try Vector DB first
            formatted_results = None
            source = None
            vector_tool = self.tools.get("vector_db")
            
            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="laptop",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
            
            # Fallback to Serper
            if not formatted_results:
                search_decision_prompt = f"""
                Create a search query for finding laptops based on: {user_request_str}
                Return ONLY JSON: {{"search_query": "your query"}}
                """
                decision_raw_llm_response = self.contact(search_decision_prompt)
                decision_raw_cleaned = self._extract_json_from_markdown(decision_raw_llm_response)
                
                try:
                    decision = json.loads(decision_raw_cleaned)
                    search_query = decision.get("search_query", "")
                except json.JSONDecodeError:
                    print(f"WARNING: LaptopAgent - Failed to parse search_decision JSON (from LLM): {decision_raw_llm_response[:200]}... Cleaned: {decision_raw_cleaned[:200]}...")
                    usage = user_request.get("usage", "general")
                    search_query = f"{usage} laptop {location} under {budget}"
                except Exception as e:
                    print(f"ERROR: LaptopAgent - Error during search query decision: {e}. Raw LLM: {decision_raw_llm_response[:200]}...")
                    usage = user_request.get("usage", "general")
                    search_query = f"{usage} laptop {location} under {budget}"
                
                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"
            
            # Generate recommendation
            full_prompt = f"""
            {self.laptop_prompt}
            
            User request: {user_request_str}
            Data source: {source}
            Retrieved information: {formatted_results}
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Return ONLY valid JSON following the specified format.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: LaptopAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                raise ValueError("Final AI response for Laptop was not valid JSON.")
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "user_request": user_request
            }


class TabletAgent(BaseAgent):
    """Tablet finder agent."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.tablet_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_request_str = json.dumps(user_request, indent=2)
            
            # Tablet Agent extracts params without LLM, so no cleaning here for that specific step
            location = user_request.get("location", "")
            budget = user_request.get("budget")
            
            # Try Vector DB
            formatted_results = None
            source = None
            vector_tool = self.tools.get("vector_db")
            
            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="tablet",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
            
            # Fallback to Serper (no LLM for search query building here)
            if not formatted_results:
                search_query = f"tablet {user_request.get('display', '')} {location} under {budget}"
                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"
            
            full_prompt = f"""
            {self.tablet_prompt}
            
            User request: {user_request_str}
            Data source: {source}
            Retrieved information: {formatted_results}
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Return ONLY valid JSON.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: TabletAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                raise ValueError("Final AI response for Tablet was not valid JSON.")
            
        except Exception as e:
            return {"error": str(e), "status": "failed", "user_request": user_request}


class EarpieceAgent(BaseAgent):
    """Earpiece/headphone finder agent."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.earpiece_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_request_str = json.dumps(user_request, indent=2)
            
            # Earpiece Agent extracts params without LLM, so no cleaning here for that specific step
            location = user_request.get("location", "")
            budget = user_request.get("budget")
            
            # Try Vector DB
            formatted_results = None
            source = None
            vector_tool = self.tools.get("vector_db")
            
            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="earpiece",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
            
            # Fallback to Serper (no LLM for search query building here)
            if not formatted_results:
                earpiece_type = user_request.get("earpiece_type", "earbuds")
                search_query = f"{earpiece_type} {location} under {budget}"
                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"
            
            full_prompt = f"""
            {self.earpiece_prompt}
            
            User request: {user_request_str}
            Data source: {source}
            Retrieved information: {formatted_results}
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Return ONLY valid JSON.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: EarpieceAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                raise ValueError("Final AI response for Earpiece was not valid JSON.")
            
        except Exception as e:
            return {"error": str(e), "status": "failed", "user_request": user_request}


class PreBuiltPCAgent(BaseAgent):
    """Pre-built PC finder agent."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.pc_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_request_str = json.dumps(user_request, indent=2)
            
            # PreBuiltPCAgent extracts params without LLM, so no cleaning here for that specific step
            location = user_request.get("location", "")
            budget = user_request.get("budget")
            
            # Try Vector DB
            formatted_results = None
            source = None
            vector_tool = self.tools.get("vector_db")
            
            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="prebuilt_pc",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"
            
            # Fallback to Serper (no LLM for search query building here)
            if not formatted_results:
                usage = user_request.get("usage", "general")
                search_query = f"prebuilt {usage} PC {location} under {budget}"
                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"
            
            full_prompt = f"""
            {self.pc_prompt}
            
            User request: {user_request_str}
            Data source: {source}
            Retrieved information: {formatted_results}
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Return ONLY valid JSON.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: PreBuiltPCAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                raise ValueError("Final AI response for Pre-built PC was not valid JSON.")
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "user_request": user_request
            }


class PCBuilderAgent(BaseAgent):
    """PC builder agent for custom builds."""
    
    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.builder_prompt = prompt_template
    
    # Changed return type hint to Dict[str, Any]
    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_request_str = json.dumps(user_request, indent=2)
            # PCBuilderAgent extracts params without LLM, so no cleaning here for that specific step
            location = user_request.get("location", "")
            budget = user_request.get("budget")
            use_case = user_request.get("use_case", "general")
            
            # PC Builder always uses web search for component availability
            # No vector DB fallback for components (too many variations)
            
            search_queries = []
            components = ["CPU", "GPU", "motherboard", "RAM", "SSD", "PSU", "case"]
            
            # Build search queries for each component
            for component in components:
                query = f"{component} {use_case} {location} under {budget // len(components)}"
                search_queries.append({"component": component, "query": query})
            
            # Search for components
            search_tool = self.tools.get("serper")
            all_results = []
            
            if search_tool:
                for item in search_queries[:3]:  # Limit to top 3 components to save API calls
                    results = search_tool.get_organic_results(item["query"], num_results=3)
                    all_results.append({
                        "component": item["component"],
                        "results": results
                    })
            
            formatted_results = json.dumps(all_results, indent=2)
            
            full_prompt = f"""
            {self.builder_prompt}
            
            User request: {user_request_str}
            
            Component search results:
            {formatted_results}
            
            Current timestamp: {datetime.utcnow().isoformat()}Z
            
            Analyze the components, ensure compatibility, and return ONLY valid JSON following the specified format.
            """
            
            final_response_llm_output = self.contact(full_prompt)
            final_response_cleaned = self._extract_json_from_markdown(final_response_llm_output)
            
            # CRITICAL CHANGE: Parse the final JSON string into a Python dictionary HERE
            try:
                return json.loads(final_response_cleaned) 
            except json.JSONDecodeError:
                print(f"CRITICAL ERROR: PCBuilderAgent - Final LLM output was NOT valid JSON after cleaning: {final_response_cleaned[:500]}...")
                raise ValueError("Final AI response for PC Builder was not valid JSON.")
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "user_request": user_request
            }


# Factory functions for easy agent creation
def create_phone_agent(llm, vector_db, serper_tool):
    """Create and configure a phone agent."""
    from prompts import phone_prompt
    agent = PhoneAgent(llm, phone_prompt)
    agent.register_tool("vector_db", vector_db)
    agent.register_tool("serper", serper_tool)
    return agent


def create_laptop_agent(llm, vector_db, serper_tool):
    """Create and configure a laptop agent."""
    from prompts import laptop_prompt
    agent = LaptopAgent(llm, laptop_prompt)
    agent.register_tool("vector_db", vector_db)
    agent.register_tool("serper", serper_tool)
    return agent


def create_tablet_agent(llm, vector_db, serper_tool):
    """Create and configure a tablet agent."""
    from prompts import tablet_prompt
    agent = TabletAgent(llm, tablet_prompt)
    agent.register_tool("vector_db", vector_db)
    agent.register_tool("serper", serper_tool)
    return agent


def create_earpiece_agent(llm, vector_db, serper_tool):
    """Create and configure an earpiece agent."""
    from prompts import earpiece_prompt
    agent = EarpieceAgent(llm, earpiece_prompt)
    agent.register_tool("vector_db", vector_db)
    agent.register_tool("serper", serper_tool)
    return agent


def create_prebuilt_pc_agent(llm, vector_db, serper_tool):
    """Create and configure a pre-built PC agent."""
    from prompts import prebuilt_pc_prompt
    agent = PreBuiltPCAgent(llm, prebuilt_pc_prompt)
    agent.register_tool("vector_db", vector_db)
    agent.register_tool("serper", serper_tool)
    return agent


def create_pc_builder_agent(llm, serper_tool):
    """Create and configure a PC builder agent (no vector DB needed)."""
    from prompts import pc_builder_prompt
    agent = PCBuilderAgent(llm, pc_builder_prompt)
    agent.register_tool("serper", serper_tool)
    return agent


if __name__ == "__main__":
    from llm_provider import LLMProvider
    from vector_db_tool import VectorDBTool
    from serper_tool import SerperSearchTool
    
    # Initialize
    llm = LLMProvider()
    vector_db = VectorDBTool()
    serper = SerperSearchTool()
    
    # Create phone agent
    phone_agent = create_phone_agent(llm, vector_db, serper)
    
    # Test
    request = {
        "location": "Nairobi, Kenya",
        "budget": 45000,
        "ram": "8GB",
        "storage": "128GB",
        "user_base_prompt": "I need a good camera phone"
    }
    
    print("Testing Phone Agent...")
    result = phone_agent.handle_request(request)
    print(result)