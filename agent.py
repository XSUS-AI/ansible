# PydanticAI Agent with MCP

from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.agent import AgentRunResult

from dotenv import load_dotenv
import os
import argparse

load_dotenv()

# Try to configure logfire if available
try:
    import logfire
    logfire.configure(token=os.getenv("LOGFIRE_API_KEY"))
    logfire.instrument_openai()
except (ImportError, AttributeError):
    pass

# Set up argument parser for model selection
parser = argparse.ArgumentParser(description='Run Ansible MCP Agent')
parser.add_argument('--model', type=str, default='anthropic/claude-3.7-sonnet',
                    help='Model to use (default: anthropic/claude-3.7-sonnet)')
args = parser.parse_args()
model_name = args.model

# Set up OpenRouter based model
API_KEY = os.getenv('OPENROUTER_API_KEY')
model = OpenAIModel(
    model_name,
    provider=OpenAIProvider(
        base_url='https://openrouter.ai/api/v1', 
        api_key=API_KEY
    ),
)

# MCP Environment variables - no specific ones needed for our Ansible MCP
env = {}

mcp_servers = [
    MCPServerStdio('python', ['src/mcp/mcp_server.py'], env=env),
]

from datetime import datetime, timezone

# Set up Agent with Server
agent_name = "AnsibleAgent"
def load_agent_prompt(agent:str):
    """Loads given agent replacing `time_now` var with current time"""
    print(f"Loading {agent}")
    time_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with open(f"agents/{agent}.md", "r") as f:
        agent_prompt = f.read()
    agent_prompt = agent_prompt.replace('{time_now}', time_now)
    return agent_prompt

# Load up the agent system prompt
agent_prompt = load_agent_prompt(agent_name)
print(f"Loaded agent prompt for {agent_name}")
agent = Agent(model, mcp_servers=mcp_servers, system_prompt=agent_prompt)

import traceback

async def main():
    """CLI testing in a conversation with the agent"""
    print(f"Starting Ansible Agent with model: {model_name}")
    print("Type 'exit' to quit")
    
    async with agent.run_mcp_servers(): 
        result:AgentRunResult = None

        while True:
            if result:
                print(f"\n{result.output}")
            user_input = input("\n> ")
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Exiting Ansible Agent...")
                break
                
            err = None
            for i in range(0, 3):
                try:
                    result = await agent.run(
                        user_input, 
                        message_history=None if result is None else result.all_messages()
                    )
                    break
                except Exception as e:
                    err = e
                    traceback.print_exc()
                    import asyncio
                    await asyncio.sleep(2)
            if result is None:
                print(f"\nError {err}. Try again...\n")
                continue

        
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
