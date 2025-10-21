"""
Manual agent implementation for DeviceFinder.AI system.
Simple, transparent agents with tool access and JSON-safe parsing.
"""

import json
import re
from datetime import datetime
from typing import Dict, Any


# ============================================================
# BASE AGENT
# ============================================================
class BaseAgent:
    """Base agent class with shared utilities and tool registration."""

    def __init__(self, llm):
        self.llm = llm
        self.tools = {}

    def register_tool(self, name, tool):
        """Register an external tool."""
        if tool is None:
            raise ValueError(f"Cannot register None as tool '{name}'")
        self.tools[name] = tool
        print(f"✓ Registered tool: {name}")

    def contact(self, prompt):
        """Query the connected LLM."""
        return self.llm.generate(prompt)

    # ---------------------------
    # JSON Handling Utilities
    # ---------------------------

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON whether it’s inside markdown or plain text."""
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            candidate = match.group(1).strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return match.group(0)
        return text.strip()

    def _clean_json_text(self, text: str) -> str:
        """Fixes common JSON formatting issues in LLM output."""
        import re

        # Normalize quotes
        text = text.replace("“", '"').replace("”", '"').replace("’", "'")

        # Fix stray commas before closing braces/brackets
        text = re.sub(r",\s*([\]}])", r"\1", text)

        # Fix unescaped inch marks like 27" Monitor → 27\" Monitor
        text = re.sub(r'(\d)"(?=[^:,\}\]])', r'\1\\"', text)

        # Fix quotes that break after URLs (missing closing quote)
        # Example: "url": "https://something.com/  →  "url": "https://something.com/"
        text = re.sub(
            r'("url"\s*:\s*")([^"]+)(?=\s*[\r\n,}])',
            lambda m: m.group(1) + m.group(2).rstrip("/") + '"/',
            text
        )
        text = text.replace('"/', '"')  # cleanup from regex above

        # Fix stray double quotes immediately following a URL (like https://foo.com")
        text = re.sub(r'(https?:\/\/[^\s"]+)"', r'\1', text)

        return text.strip()


    @staticmethod
    def safe_json_loads(text):
        """Attempts to load JSON safely, even with minor LLM formatting issues."""
        try:
            # Extract the JSON portion if extra text exists
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                text = match.group(1)

            # Attempt normal JSON parse
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[WARN] JSON parsing failed: {e}\nTrying to auto-fix...")

            # Auto-fix common issues like unescaped quotes or trailing commas
            fixed = re.sub(r',\s*([\]}])', r'\1', text)
            fixed = re.sub(r'(?<=\d)"(?=[^:,\}\]])', '\\"', fixed)
            try:
                return json.loads(fixed)
            except Exception as e2:
                print(f"[ERROR] Final parse failed: {e2}\nRaw text:\n{text}\n")
                return None
        except Exception as e:
            print(f"[ERROR] Unexpected JSON error: {e}\nRaw text:\n{text}\n")
            return None



# ============================================================
# PHONE AGENT
# ============================================================
class PhoneAgent(BaseAgent):
    """Handles smartphone recommendations with DB-first fallback search."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.phone_prompt = prompt_template

    def handle_request(self, user_request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_request_str = json.dumps(user_request, indent=2)

            # Step 1: Extract location and budget
            extraction_prompt = f"""
            Extract location and budget from this request:
            {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))

            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget")

            # Step 2: Query Vector DB
            formatted_results, source = None, None
            vector_tool = self.tools.get("vector_db")

            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=user_request.get("user_base_prompt", str(user_request)),
                    category="phone",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"

            # Step 3: Fallback to Serper
            if not formatted_results:
                search_prompt = f"""
                Create a search query for finding phones based on:
                {user_request_str}
                Return ONLY JSON: {{"search_query": "query"}}
                """
                decision_raw = self.contact(search_prompt)
                decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
                try:
                    decision = self.safe_json_loads(decision_cleaned)
                    search_query = decision.get("search_query", "")
                except Exception:
                    specs = f"{user_request.get('ram', '')} {user_request.get('storage', '')} smartphone"
                    search_query = f"{specs} {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"

            # Step 4: Final recommendation
            final_prompt = f"""
            {self.phone_prompt}

            User request:
            {user_request_str}

            Data source: {source}
            Retrieved information: {formatted_results}
            Current timestamp: {datetime.utcnow().isoformat()}Z

            Return ONLY valid JSON.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)

        except Exception as e:
            return {"error": str(e), "status": "failed", "user_request": user_request}


# ============================================================
# LAPTOP AGENT
# ============================================================
class LaptopAgent(BaseAgent):
    """Laptop finder with DB-first and Serper fallback."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.laptop_prompt = prompt_template

    def handle_request(self, user_request):
        try:
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget from this request:
            {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))

            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget")

            formatted_results, source = None, None
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

            if not formatted_results:
                search_prompt = f"""
                Create a search query for finding laptops based on:
                {user_request_str}
                Return ONLY JSON: {{"search_query": "query"}}
                """
                decision_raw = self.contact(search_prompt)
                decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
                try:
                    decision = self.safe_json_loads(decision_cleaned)
                    search_query = decision.get("search_query", "")
                except Exception:
                    usage = user_request.get("usage", "general")
                    search_query = f"{usage} laptop {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"

            final_prompt = f"""
            {self.laptop_prompt}
            User request: {user_request_str}
            Data source: {source}
            Retrieved: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z
            Return ONLY JSON.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)

        except Exception as e:
            return {"error": str(e), "status": "failed", "user_request": user_request}


# ============================================================
# TABLET AGENT
# ============================================================
class TabletAgent(BaseAgent):
    """Tablet search and recommendation agent."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.tablet_prompt = prompt_template

    def handle_request(self, user_request):
        try:
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget from: {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))
            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget")

            formatted_results, source = None, None
            vector_tool = self.tools.get("vector_db")

            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=str(user_request),
                    category="tablet",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"

            if not formatted_results:
                search_prompt = f"""
                Create a search query for tablets:
                {user_request_str}
                Return ONLY JSON: {{"search_query": "query"}}
                """
                decision_raw = self.contact(search_prompt)
                decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
                try:
                    decision = self.safe_json_loads(decision_cleaned)
                    search_query = decision.get("search_query", "")
                except Exception:
                    search_query = f"tablet {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"

            final_prompt = f"""
            {self.tablet_prompt}
            User request: {user_request_str}
            Data source: {source}
            Data: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z
            Return ONLY JSON.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)
        except Exception as e:
            return {"error": str(e), "status": "failed"}


# ============================================================
# EARPIECE AGENT
# ============================================================
class EarpieceAgent(BaseAgent):
    """Earpiece recommendation agent."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.earpiece_prompt = prompt_template

    def handle_request(self, user_request):
        try:
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget from: {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))
            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget")

            formatted_results, source = None, None
            vector_tool = self.tools.get("vector_db")

            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=str(user_request),
                    category="earpiece",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"

            if not formatted_results:
                search_prompt = f"""
                Create search query for earpieces:
                {user_request_str}
                Return ONLY JSON: {{"search_query": "query"}}
                """
                decision_raw = self.contact(search_prompt)
                decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
                try:
                    decision = self.safe_json_loads(decision_cleaned)
                    search_query = decision.get("search_query", "")
                except Exception:
                    search_query = f"earpiece {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"

            final_prompt = f"""
            {self.earpiece_prompt}
            User request: {user_request_str}
            Source: {source}
            Data: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z
            Return ONLY JSON.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)
        except Exception as e:
            return {"error": str(e), "status": "failed"}


# ============================================================
# PREBUILT PC AGENT
# ============================================================
class PreBuiltPCAgent(BaseAgent):
    """Handles prebuilt PC searches."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.pc_prompt = prompt_template

    def handle_request(self, user_request):
        try:
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget:
            {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))
            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget")

            formatted_results, source = None, None
            vector_tool = self.tools.get("vector_db")

            if vector_tool and location:
                vector_results = vector_tool.query_devices(
                    query=str(user_request),
                    category="prebuilt_pc",
                    location=location,
                    price_max=budget,
                    top_k=5
                )
                if vector_results and len(vector_results) >= 3:
                    formatted_results = json.dumps(vector_results, indent=2)
                    source = "Vector Database"

            if not formatted_results:
                search_prompt = f"""
                Create search query for prebuilt PCs:
                {user_request_str}
                Return ONLY JSON: {{"search_query": "query"}}
                """
                decision_raw = self.contact(search_prompt)
                decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
                try:
                    decision = self.safe_json_loads(decision_cleaned)
                    search_query = decision.get("search_query", "")
                except Exception:
                    search_query = f"prebuilt gaming PC {location} under {budget}"

                search_tool = self.tools.get("serper")
                if search_tool:
                    search_results = search_tool.get_organic_results(search_query, num_results=5)
                    formatted_results = search_tool.format_results(search_results)
                    source = "Web Search"

            final_prompt = f"""
            {self.pc_prompt}
            User request: {user_request_str}
            Source: {source}
            Data: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z
            Return ONLY JSON.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)
        except Exception as e:
            return {"error": str(e), "status": "failed"}


# ============================================================
# PC BUILDER AGENT
# ============================================================
class PCBuilderAgent(BaseAgent):
    """Handles custom PC build configurations."""

    def __init__(self, llm, prompt_template):
        super().__init__(llm)
        self.builder_prompt = prompt_template

    def handle_request(self, user_request):
        try:
            user_request_str = json.dumps(user_request, indent=2)
            extraction_prompt = f"""
            Extract location and budget from:
            {user_request_str}
            Return ONLY JSON: {{"location": "City, Country", "budget": number}}
            Return your answer as **STRICT JSON**. 
            Your response MUST:
            - Be enclosed in curly braces
            - Use double quotes for all keys and string values
            - Use a number (not string) for the budget field
            """
            params_raw = self.contact(extraction_prompt)
            print(f"[DEBUG] Raw extraction response: {params_raw}")
            params_cleaned = self._clean_json_text(self._extract_json_from_markdown(params_raw))
            try:
                params = self.safe_json_loads(params_cleaned)
                location = params.get("location", user_request.get("location", ""))
                budget = params.get("budget", user_request.get("budget"))
                if not budget or budget == "null":
                    budget = user_request.get("budget", 0)
            except Exception:
                location = user_request.get("location", "")
                budget = user_request.get("budget", 0)
            finally:
                print(f"[DEBUG] Final extracted location: {location}, budget: {budget}")



            formatted_results, source = None, None
            search_prompt = f"""
            Create search queries for all PC parts needed based on:
            {user_request_str}
            Return ONLY JSON: {{"search_queries": ["CPU query", "GPU query", "RAM query", ...]}}
            Ensure:
            - Each item in "search_queries" is a string.
            - The JSON is syntactically correct (no trailing commas or comments).
            - Do not include code blocks or Markdown fences.
            """
            decision_raw = self.contact(search_prompt)
            decision_cleaned = self._clean_json_text(self._extract_json_from_markdown(decision_raw))
            try:
                decision = self.safe_json_loads(decision_cleaned)
                queries = decision.get("search_queries", [])
            except Exception:
                queries = [f"gaming pc parts {location} under {budget}"]

            search_tool = self.tools.get("serper")
            if search_tool:
                part_results = []
                for q in queries:
                    if isinstance(q, dict):
                        q_str = list(q.values())[0] if q else ""
                    else:
                        q_str = str(q)

                    res = search_tool.get_organic_results(q_str, num_results=3)
                    part_results.append({"query": q_str, "results": res})
            final_prompt = f"""
            {self.builder_prompt}
            User request: {user_request_str}
            Source: {source}
            Data: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z
            VERY IMPORTANT!!!
            System message:
            - Output only valid JSON (no Markdown, no text before/after).
            - Use double quotes for all keys and string values.
            - Ensure every field, array, and object is closed properly.
            - Escape any double quotes within strings.
            """
            llm_output = self.contact(final_prompt)
            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))
            return self.safe_json_loads(cleaned)
        except Exception as e:
            return {"error": str(e), "status": "failed"}

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