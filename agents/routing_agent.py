import os
import json
from google.adk.agents import Agent
from google.adk.tools.bigquery import BigQueryToolset, BigQueryCredentialsConfig
import google.auth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def parse_routing_result(response_text: str):
    """
    Parse JSON output from the routing agent.
    """
    clean_response = (
        response_text
        .strip()
        .replace("```json", "")
        .replace("```", "")
    )

    return json.loads(clean_response)


# Load routing prompt
agent_dir = os.path.dirname(os.path.abspath(__file__))
prompt_path = os.path.join(
    agent_dir,
    "..",
    "prompts",
    "routing_prompt.txt"
)

with open(prompt_path, "r") as f:
    routing_instruction = f.read()


# Define ADK agent
root_agent = Agent(
    name="routing_agent",
    model="gemini-1.5-flash",
    description="Routes user conversations to the correct downstream agent.",
    instruction=routing_instruction,
)