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
        text = text.replace(""", '"').replace(""", '"').replace("'", "'")

        # Fix stray commas before closing braces/brackets
        text = re.sub(r",\s*([\]}])", r"\1", text)

        # Fix unescaped inch marks like 27" Monitor → 27\" Monitor
        text = re.sub(r'(\d)"(?=[^:,\}\]])', r'\1\\"', text)

        # FIX 1: Handle URLs with missing closing quotes
        text = re.sub(
            r'("url"\s*:\s*")(https?://[^"\n]+?)(/)\s*\n',
            r'\1\2\3"\n',
            text
        )

        # FIX 2: More robust URL quote fixing
        text = re.sub(
            r'("url"\s*:\s*"https?://[^"\n]+)(\s*[\r\n]+\s*[},\]])',
            r'\1"\2',
            text
        )

        # FIX 3: Remove incorrectly escaped closing quotes (e.g., 200000\")
        # This fixes: "text under 200000\"  →  "text under 200000"
        text = re.sub(r'([\w\d\s]+)\\"(\s*[,\n\r])', r'\1"\2', text)

        # FIX 4: Fix cases where backslash appears before closing quote at end of line
        # Handles: "query text\"  →  "query text"
        text = re.sub(r'\\"(\s*$)', r'"\1', text, flags=re.MULTILINE)

        # FIX 5: Remove literal \n or \t inside string values
        text = re.sub(r'(?<=": ")([^"]*?)\\n([^"]*?)(?=")', lambda m: m.group(0).replace('\\n', ' '), text)
        text = re.sub(r'(?<=": ")([^"]*?)\\t([^"]*?)(?=")', lambda m: m.group(0).replace('\\t', ' '), text)

        return text.strip()

    @staticmethod
    def safe_json_loads(text):
        """Attempts to load JSON safely with comprehensive error handling."""
        import re
        import json
        
        if not text or not text.strip():
            print("[ERROR] Empty text provided to safe_json_loads")
            return None
        
        try:
            # Step 1: Extract JSON portion if embedded in other text
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                text = match.group(1)
            
            # Step 2: Attempt normal JSON parse
            return json.loads(text)
            
        except json.JSONDecodeError as e:
            print(f"[WARN] Initial JSON parsing failed: {e}")
            print(f"[WARN] Error location: line {e.lineno}, column {e.colno}")
            
            try:
                # Step 3: Apply aggressive fixes
                fixed = text
                
                # Fix 1: Remove trailing commas
                fixed = re.sub(r',\s*([\]}])', r'\1', fixed)
                
                # Fix 2: Escape unescaped quotes in numbers (like 27")
                fixed = re.sub(r'(\d)"(?=[^:,\}\]])', r'\1\\"', fixed)
                
                # Fix 3: Fix URLs missing closing quotes before newlines
                fixed = re.sub(
                    r'("url"\s*:\s*"https?://[^"\n]+)(\s*[\r\n])',
                    r'\1"\2',
                    fixed
                )
                
                # Fix 4: Remove control characters (tabs, newlines) inside strings
                # Split by lines and rejoin, ensuring no literal control chars in strings
                lines = fixed.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Remove literal \n and \t inside string values
                    line = re.sub(r'\\[nt]', ' ', line)
                    cleaned_lines.append(line)
                fixed = '\n'.join(cleaned_lines)
                
                # Fix 5: Ensure all quotes are balanced
                # Count quotes per line to detect unclosed strings
                lines = fixed.split('\n')
                for i, line in enumerate(lines):
                    # Skip empty lines
                    if not line.strip():
                        continue
                    # Count non-escaped quotes
                    quote_count = len(re.findall(r'(?<!\\)"', line))
                    # If odd number, likely missing closing quote
                    if quote_count % 2 == 1 and not line.rstrip().endswith(','):
                        # Try adding closing quote before newline
                        if '"url"' in line and 'https://' in line:
                            lines[i] = line.rstrip() + '"'
                
                fixed = '\n'.join(lines)
                
                print("[INFO] Attempting parse with auto-fixes...")
                return json.loads(fixed)
                
            except json.JSONDecodeError as e2:
                print(f"[ERROR] Auto-fix parse failed: {e2}")
                print(f"[ERROR] Error location: line {e2.lineno}, column {e2.colno}")
                
                # Show context around the error
                lines = text.split('\n')
                if e2.lineno <= len(lines):
                    error_line = lines[e2.lineno - 1]
                    print(f"[ERROR] Problem line {e2.lineno}: {error_line}")
                    if e2.colno and e2.colno < len(error_line):
                        print(f"[ERROR] Problem character: '{error_line[e2.colno]}'")
                
                print(f"[ERROR] Full text:\n{text}\n")
                return None
                
        except Exception as e:
            print(f"[ERROR] Unexpected error in safe_json_loads: {e}")
            print(f"[ERROR] Text: {text[:500]}...")  # Show first 500 chars
            return None

# Add this method to your BaseAgent class:

    def _validate_response(self, response: dict) -> dict:
        """Validate and sanitize agent response before returning."""
        if response is None:
            return {
                "error": "Agent produced null response",
                "status": "failed",
                "recommendations": [],
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "status": "failed"
                }
            }
        
        # Ensure required keys exist
        if "recommendations" not in response:
            response["recommendations"] = []
        
        if "metadata" not in response:
            response["metadata"] = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "status": "partial"
            }
        
        # Check if recommendations is empty or invalid
        if not response["recommendations"]:
            print("[WARN] Empty recommendations array in response")
            response["error"] = "No recommendations were generated"
            response["status"] = "failed"
            response["metadata"]["status"] = "failed"
        
        # Validate recommendations array contains valid data
        if isinstance(response["recommendations"], list):
            valid_recs = []
            for i, rec in enumerate(response["recommendations"]):
                if rec and isinstance(rec, dict):
                    # Check for valid identifier fields
                    # Standard devices: 'name' or 'title'
                    # PC Builder: 'build_name' or 'components'
                    has_identifier = (
                        rec.get("name") or 
                        rec.get("title") or 
                        rec.get("build_name") or
                        rec.get("components")  # PC Builder has components array
                    )
                    
                    if has_identifier:
                        valid_recs.append(rec)
                    else:
                        print(f"[WARN] Invalid recommendation at index {i}: missing identifier (name/title/build_name/components)")
                        print(f"[WARN] Keys present: {list(rec.keys())[:10]}")  # Show first 10 keys
                else:
                    print(f"[WARN] Invalid recommendation at index {i}: not a dict or is None")
            
            response["recommendations"] = valid_recs
            
            if not valid_recs:
                response["error"] = "No valid recommendations found in response"
                response["status"] = "failed"
        
        # Clean up any remaining control characters in strings
        import json
        try:
            # Serialize and deserialize to ensure it's valid JSON
            json_str = json.dumps(response, ensure_ascii=False)
            response = json.loads(json_str)
        except Exception as e:
            print(f"[ERROR] Response validation failed: {e}")
            return {
                "error": f"Response validation failed: {str(e)}",
                "status": "failed",
                "partial_data": str(response)[:500],  # Only include first 500 chars
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "status": "failed"
                }
            }
        
        # Add debugging info in development
        print(f"[DEBUG] Validated response has {len(response.get('recommendations', []))} recommendations")
        
        return response

# Then update the end of each agent's handle_request method:
# OLD:
# return self.safe_json_loads(cleaned)

# NEW:

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
            result = self.safe_json_loads(cleaned)
            return self._validate_response(result)

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
            result = self.safe_json_loads(cleaned)
            return self._validate_response(result)

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
            result = self.safe_json_loads(cleaned)
            return self._validate_response(result)
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
            result = self.safe_json_loads(cleaned)
            return self._validate_response(result)
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
            result = self.safe_json_loads(cleaned)
            return self._validate_response(result)
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
# In the PCBuilderAgent's handle_request method, update the final_prompt:

            final_prompt = f"""
            {self.builder_prompt}
            User request: {user_request_str}
            Source: {source}
            Data: {formatted_results}
            Timestamp: {datetime.utcnow().isoformat()}Z

            CRITICAL JSON FORMATTING REQUIREMENTS:
            1. Output ONLY valid JSON - no Markdown, no text before/after
            2. Use double quotes for ALL keys and string values
            3. Every URL MUST be on a single line with proper closing quotes
            4. Ensure every field, array, and object is properly closed
            5. Escape any double quotes within strings using backslash
            6. Do NOT include newlines inside string values
            7. All URLs must follow this exact format: "url": "https://example.com/path"
            8. Verify closing quotes exist for ALL string fields before newlines

            Example of correct URL formatting:
            "vendor_online": {{
            "store": "Example Store",
            "url": "https://example.com/product"
            }},

            Return your response as a single, valid JSON object.
            """
# In PCBuilderAgent.handle_request, after llm_output = self.contact(final_prompt)
            llm_output = self.contact(final_prompt)

            # ADD THIS DEBUGGING BLOCK
            print("[DEBUG] ===== PC Builder LLM Raw Output =====")
            print(llm_output[:1000])  # Print first 1000 chars
            print("[DEBUG] =====================================")

            cleaned = self._clean_json_text(self._extract_json_from_markdown(llm_output))

            print("[DEBUG] ===== PC Builder Cleaned JSON =====")
            print(cleaned[:1000])  # Print first 1000 chars
            print("[DEBUG] ====================================")

            result = self.safe_json_loads(cleaned)

            print("[DEBUG] ===== PC Builder Parsed Result =====")
            if result:
                print(f"Keys in result: {result.keys()}")
                if "recommendations" in result:
                    print(f"Number of recommendations: {len(result.get('recommendations', []))}")
                if "components" in result:
                    print(f"Components: {list(result.get('components', {}).keys())}")
            else:
                print("Result is None!")
            print("[DEBUG] ======================================")

            return self._validate_response(result)
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