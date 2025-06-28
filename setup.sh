#!/bin/bash

# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
mkdir -p logs

echo -e "${YELLOW}Ansible MCP Agent Setup${NC}"
echo "============================="
echo ""

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [[ $PYTHON_MAJOR -lt 3 || ($PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 9) ]]; then
    echo -e "${RED}Error: Python 3.9+ is required. Found: $PYTHON_VERSION${NC}"
    echo "Please upgrade your Python installation."
    exit 1
else
    echo -e "${GREEN}Python version $PYTHON_VERSION is OK${NC}"
fi

# Install pip packages
echo -e "\n${YELLOW}Installing Python dependencies...${NC}"
pip install -r requirements.txt

# Sometimes ansible-runner needs to be installed separately
echo -e "\n${YELLOW}Checking ansible-runner installation...${NC}"
if ! python -c "import ansible_runner" 2>/dev/null; then
    echo -e "${YELLOW}ansible-runner not found. Installing directly...${NC}"
    pip install ansible-runner
    
    if ! python -c "import ansible_runner" 2>/dev/null; then
        echo -e "${RED}ERROR: Failed to install ansible-runner.${NC}"
        echo "You might need to install it with your system package manager."
        echo -e "For Ubuntu/Debian: ${YELLOW}sudo apt install python3-ansible-runner${NC}"
        echo -e "For RHEL/CentOS: ${YELLOW}sudo yum install python3-ansible-runner${NC}"
        echo -e "For macOS: ${YELLOW}pip3 install ansible-runner${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}ansible-runner is properly installed.${NC}"

# Install FastMCP dependency if needed
echo -e "\n${YELLOW}Checking FastMCP installation...${NC}"
if ! python -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
    echo -e "${YELLOW}FastMCP not found. Installing...${NC}"
    
    # First create the directory structure
    mkdir -p src/mcp/server
    
    # Create the FastMCP module
    cat > src/mcp/server/__init__.py << 'EOF'
# MCP Server package
EOF
    
    cat > src/mcp/server/fastmcp.py << 'EOF'
"""FastMCP - Simplified MCP server implementation"""
import sys
import json
import asyncio
from typing import List, Dict, Any, Callable, Optional, Union, TypeVar, Awaitable
from pydantic import BaseModel

T = TypeVar('T')
U = TypeVar('U')

class Context:
    """Context for MCP tools"""
    def __init__(self, request_id: str, request_context: Any):
        self.request_id = request_id
        self.request_context = request_context

    async def info(self, message: str) -> None:
        """Send informational message"""
        response = {
            "type": "info", 
            "requestId": self.request_id, 
            "message": message
        }
        print(json.dumps(response), flush=True)


class FastMCP:
    """Fast Model Context Protocol (MCP) server implementation"""
    def __init__(
        self, 
        name: str, 
        version: str = "0.1.0", 
        dependencies: List[str] = None,
        lifespan = None
    ):
        self.name = name
        self.version = version
        self.dependencies = dependencies or []
        self.tools = {}
        self.lifespan = lifespan
        self.lifespan_context = {}
        self._lock = asyncio.Lock()

    def tool(self):
        """Decorator to register a tool"""
        def decorator(func: Callable[[Any, Context], Awaitable[Any]]):
            self.tools[func.__name__] = func
            return func
        return decorator

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an MCP request"""
        request_id = request.get("requestId", "")
        request_type = request.get("type", "")
        
        if request_type == "listTools":
            tool_specs = []
            for tool_name, tool_func in self.tools.items():
                # Determine parameter schema from function annotations
                param_model = None
                for param_name, param_type in tool_func.__annotations__.items():
                    if param_name != "return" and param_name != "ctx":
                        param_model = param_type
                        break
                
                # Get return type
                return_model = tool_func.__annotations__.get("return")
                
                # Create tool spec
                tool_spec = {
                    "name": tool_name,
                    "description": tool_func.__doc__ or "",
                }
                
                # Add parameter schema if available
                if param_model and hasattr(param_model, "model_json_schema"):
                    param_schema = param_model.model_json_schema()
                    tool_spec["parameters"] = param_schema
                
                # Add return schema if available
                if return_model and hasattr(return_model, "model_json_schema"):
                    return_schema = return_model.model_json_schema()
                    tool_spec["returnSchema"] = return_schema
                
                tool_specs.append(tool_spec)
            
            return {
                "type": "listToolsResponse",
                "requestId": request_id,
                "tools": tool_specs
            }
        
        elif request_type == "callTool":
            tool_name = request.get("name", "")
            parameters = request.get("parameters", {})
            
            if tool_name not in self.tools:
                return {
                    "type": "callToolError",
                    "requestId": request_id,
                    "error": f"Tool '{tool_name}' not found"
                }
            
            tool_func = self.tools[tool_name]
            
            # Find request parameter type
            param_model = None
            for param_name, param_type in tool_func.__annotations__.items():
                if param_name != "return" and param_name != "ctx":
                    param_model = param_type
                    break
            
            try:
                # Create the request object from parameters
                if param_model:
                    request_obj = param_model.model_validate(parameters)
                else:
                    request_obj = parameters
                
                # Create context
                ctx = Context(request_id, self.lifespan_context)
                
                # Call the tool
                result = await tool_func(request_obj, ctx)
                
                # Convert to JSON serializable format
                if hasattr(result, "model_dump"):
                    result = result.model_dump()
                
                return {
                    "type": "callToolResponse",
                    "requestId": request_id,
                    "result": result
                }
            
            except Exception as e:
                return {
                    "type": "callToolError",
                    "requestId": request_id,
                    "error": str(e)
                }
        
        else:
            return {
                "type": "error",
                "requestId": request_id,
                "error": f"Unknown request type: {request_type}"
            }

    async def process_requests(self):
        """Process MCP requests from stdin"""
        if self.lifespan:
            async with self.lifespan(self) as context:
                self.lifespan_context = context
                while True:
                    try:
                        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                        if not line:
                            break
                        
                        try:
                            request = json.loads(line)
                            response = await self.handle_request(request)
                            print(json.dumps(response), flush=True)
                        except json.JSONDecodeError:
                            sys.stderr.write(f"Invalid JSON: {line}\n")
                    except Exception as e:
                        sys.stderr.write(f"Error processing request: {str(e)}\n")
        else:
            while True:
                try:
                    line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                    if not line:
                        break
                    
                    try:
                        request = json.loads(line)
                        response = await self.handle_request(request)
                        print(json.dumps(response), flush=True)
                    except json.JSONDecodeError:
                        sys.stderr.write(f"Invalid JSON: {line}\n")
                except Exception as e:
                    sys.stderr.write(f"Error processing request: {str(e)}\n")

    def run(self):
        """Run the MCP server"""
        asyncio.run(self.process_requests())

    async def start(self):
        """Start the MCP server"""
        # Send server information
        server_info = {
            "type": "serverInfo",
            "name": self.name,
            "version": self.version,
            "dependencies": self.dependencies
        }
        print(json.dumps(server_info), flush=True)
        
        await self.process_requests()

    def run_async(self):
        """Run the MCP server in an event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start())
EOF
    
    # Make sure the modules are importable
    touch src/__init__.py
    touch src/mcp/__init__.py
    
    echo -e "${GREEN}FastMCP has been installed.${NC}"
else
    echo -e "${GREEN}FastMCP is already installed.${NC}"
fi

# Check for Ansible
echo -e "\n${YELLOW}Checking Ansible installation...${NC}"
if ! command -v ansible >/dev/null 2>&1; then
    echo -e "${YELLOW}Ansible command not found. Trying to install...${NC}"
    pip install ansible
    
    if ! command -v ansible >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Failed to install Ansible via pip.${NC}"
        echo "You might need to install it with your system package manager:"
        echo -e "For Ubuntu/Debian: ${YELLOW}sudo apt install ansible${NC}"
        echo -e "For RHEL/CentOS: ${YELLOW}sudo yum install ansible${NC}"
        echo -e "For macOS: ${YELLOW}brew install ansible${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}Ansible is properly installed:${NC}"
ansible --version | head -n 2

# Check for OpenRouter API key
echo -e "\n${YELLOW}Checking OpenRouter API key...${NC}"
if [ -f ".env" ] && grep -q "OPENROUTER_API_KEY" .env; then
    echo -e "${GREEN}OpenRouter API key found in .env file.${NC}"
else
    echo -e "${YELLOW}Creating .env file for API keys...${NC}"
    if [ ! -f ".env" ]; then
        echo 'OPENROUTER_API_KEY=your_openrouter_key_here' > .env
        echo -e "${YELLOW}Created .env file. Please edit it to add your OpenRouter API key.${NC}"
    else
        echo 'OPENROUTER_API_KEY=your_openrouter_key_here' >> .env
        echo -e "${YELLOW}Added OPENROUTER_API_KEY to .env file. Please edit it to add your key.${NC}"
    fi
fi

# Setup complete!
echo -e "\n${GREEN}Setup completed successfully! ${NC}"
echo -e "You can now run the agent with: ${YELLOW}python agent.py${NC}"
echo -e "Or with a specific model: ${YELLOW}python agent.py --model anthropic/claude-3-opus${NC}"
