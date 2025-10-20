from llm_provider import LLMProvider
from vector_db_tool import VectorDBTool
from serper_tool import SerperSearchTool
from device_agents import create_phone_agent, create_laptop_agent

# Initialize once
llm = LLMProvider()
vector_db = VectorDBTool()
serper = SerperSearchTool()

# Create agents
phone_agent = create_phone_agent(llm, vector_db, serper)
laptop_agent = create_laptop_agent(llm, vector_db, serper)

# Use them
result = phone_agent.handle_request({
    "location": "Nairobi, Kenya",
    "budget": 45000,
    "ram": "8GB"
})