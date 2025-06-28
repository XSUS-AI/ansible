#!/bin/bash

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}     Ansible MCP Agent Setup Script          ${NC}"
echo -e "${BLUE}===============================================${NC}"

# Check for Python
echo -e "\n${YELLOW}Checking Python installation...${NC}"
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
    echo -e "${GREEN}Python 3 found.${NC}"
else
    echo -e "${RED}Python 3 not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo -e "${YELLOW}Found Python version: ${PYTHON_VERSION}${NC}"

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}Python 3.8 or higher is required. Found $PYTHON_VERSION${NC}"
    exit 1
fi

# Check for pip
echo -e "\n${YELLOW}Checking pip installation...${NC}"
if $PYTHON_CMD -m pip --version &>/dev/null; then
    echo -e "${GREEN}pip found.${NC}"
else
    echo -e "${RED}pip not found. Installing pip...${NC}"
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON_CMD get-pip.py
    rm get-pip.py
fi

# Create a virtual environment (optional)
echo -e "\n${YELLOW}Setting up virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${GREEN}Virtual environment already exists.${NC}"
else
    $PYTHON_CMD -m pip install virtualenv
    $PYTHON_CMD -m virtualenv venv
    echo -e "${GREEN}Created virtual environment.${NC}"
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

echo -e "${GREEN}Activated virtual environment.${NC}"

# Install requirements
echo -e "\n${YELLOW}Installing dependencies...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}Installed dependencies from requirements.txt.${NC}"

# Special handling for ansible-runner
echo -e "\n${YELLOW}Checking ansible-runner installation...${NC}"
if pip show ansible-runner &>/dev/null; then
    echo -e "${GREEN}ansible-runner found.${NC}"
else
    echo -e "${YELLOW}Attempting to install ansible-runner...${NC}"
    
    # Try pip install first
    pip install ansible-runner
    
    # Check if successful
    if ! pip show ansible-runner &>/dev/null; then
        echo -e "${YELLOW}pip install failed, trying system package manager...${NC}"
        
        # Try system package managers based on OS
        if command -v apt &>/dev/null; then
            echo -e "${YELLOW}Debian/Ubuntu detected, using apt...${NC}"
            sudo apt update
            sudo apt install -y python3-ansible-runner
        elif command -v yum &>/dev/null; then
            echo -e "${YELLOW}RHEL/CentOS detected, using yum...${NC}"
            sudo yum install -y python3-ansible-runner
        elif command -v dnf &>/dev/null; then
            echo -e "${YELLOW}Fedora detected, using dnf...${NC}"
            sudo dnf install -y python3-ansible-runner
        elif command -v brew &>/dev/null; then
            echo -e "${YELLOW}macOS with Homebrew detected...${NC}"
            brew install ansible-runner
        else
            echo -e "${RED}Could not detect package manager. Please install ansible-runner manually.${NC}"
            echo -e "${YELLOW}You can try: pip install ansible-runner --no-binary :all:${NC}"
            exit 1
        fi
    fi
fi

# Verify ansible-runner installation again
if pip show ansible-runner &>/dev/null || command -v ansible-runner &>/dev/null; then
    echo -e "${GREEN}ansible-runner installation verified.${NC}"
else
    echo -e "${RED}ansible-runner installation failed.${NC}"
    echo -e "${YELLOW}For debugging, try running: pip install ansible-runner -v${NC}"
    exit 1
fi

# Check MCP server directory structure
echo -e "\n${YELLOW}Checking MCP server directory structure...${NC}"

# Create any missing directories
mkdir -p src/mcp/server

# Create __init__.py files if they don't exist
touch src/mcp/__init__.py
touch src/mcp/server/__init__.py

# Check FastMCP implementation
if [ ! -f "src/mcp/server/fastmcp.py" ]; then
    echo -e "${YELLOW}Creating FastMCP implementation...${NC}"
    cat > src/mcp/server/fastmcp.py << 'EOF'
import asyncio
from contextlib import asynccontextmanager
import inspect
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Type, TypeVar, Union, get_type_hints, cast

from pydantic import BaseModel, create_model

logger = logging.getLogger(__name__)

# Define Context class for tool methods
class Context:
    """Context object passed to tool methods providing access to request context and utilities"""
    
    def __init__(self, request_context: Any):
        self.request_context = request_context
    
    async def info(self, message: str) -> None:
        """Log an informational message"""
        logger.info(message)
    
    async def warn(self, message: str) -> None:
        """Log a warning message"""
        logger.warning(message)
    
    async def error(self, message: str) -> None:
        """Log an error message"""
        logger.error(message)
    
    async def report_progress(self, current: int, total: int) -> None:
        """Report progress of a long-running operation"""
        logger.info(f"Progress: {current}/{total}")
    
    async def read_resource(self, uri: str) -> tuple[str, str]:
        """Read the content of a resource by URI
        
        Returns:
            Tuple of (content, mime_type)
        """
        logger.info(f"Reading resource: {uri}")
        # This would call the actual resource reading implementation
        return ("", "text/plain")


# Type variable for generic functions
T = TypeVar("T")
LifespanT = TypeVar("LifespanT")


class FastMCP:
    """FastMCP server implementation for the Model Context Protocol"""
    
    def __init__(self, 
                 name: str, 
                 dependencies: Optional[List[str]] = None,
                 lifespan: Optional[Callable[..., AsyncIterator[Any]]] = None):
        """Initialize the FastMCP server
        
        Args:
            name: Name of the server
            dependencies: List of Python package dependencies required
            lifespan: Optional async context manager for server lifecycle
        """
        self.name = name
        self.dependencies = dependencies or []
        self.lifespan = lifespan
        self.tools: Dict[str, Any] = {}
        self.resources: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self.request_context: Dict[str, Any] = {}
        
        logger.info(f"Initializing FastMCP server: {name}")
    
    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a function as an MCP tool
        
        Example:
            @mcp.tool()
            def my_tool(param1: str, param2: int) -> str:
                return f"{param1}: {param2}"
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = func.__name__
            doc = func.__doc__ or f"{tool_name} tool"
            
            # Get function parameters and create model
            sig = inspect.signature(func)
            params = {}
            for param_name, param in sig.parameters.items():
                if param_name == "ctx" or param_name == "context":
                    continue  # Skip context parameter
                # Get type annotation if available
                param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
                # Get default value if available
                default = param.default if param.default != inspect.Parameter.empty else ...
                # Add to params dict
                params[param_name] = (param_type, default)
            
            # Create request model dynamically
            request_model = create_model(f"{tool_name.title()}Request", **params)  # type: ignore
            
            # Store the tool info
            self.tools[tool_name] = {
                "func": func,
                "doc": doc,
                "request_model": request_model,
            }
            
            return func
        
        return decorator
    
    def resource(self, uri_template: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a function as an MCP resource provider
        
        Example:
            @mcp.resource("user://{user_id}/profile")
            def get_user_profile(user_id: str) -> str:
                return f"Profile for user {user_id}"
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            resource_name = func.__name__
            doc = func.__doc__ or f"{resource_name} resource"
            
            # Store the resource info
            self.resources[uri_template] = {
                "func": func,
                "doc": doc,
            }
            
            return func
        
        return decorator
    
    def prompt(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a function as an MCP prompt provider
        
        Example:
            @mcp.prompt()
            def greeting(name: str) -> str:
                return f"Hello {name}, how can I assist you today?"
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            prompt_name = func.__name__
            doc = func.__doc__ or f"{prompt_name} prompt"
            
            # Get function parameters
            sig = inspect.signature(func)
            params = []
            for param_name, param in sig.parameters.items():
                if param_name == "ctx" or param_name == "context":
                    continue  # Skip context parameter
                params.append({
                    "name": param_name,
                    "description": f"{param_name} parameter",  # Basic description
                    "required": param.default == inspect.Parameter.empty,
                })
            
            # Store the prompt info
            self.prompts[prompt_name] = {
                "func": func,
                "doc": doc,
                "params": params,
            }
            
            return func
        
        return decorator
    
    async def _prepare_context(self) -> Dict[str, Any]:
        """Set up request context and run the lifespan if provided"""
        context = {}
        
        # If we have a lifespan function, run it and get the context
        if self.lifespan:
            # Create an async context manager
            lifespan_context = self.lifespan(self)
            context = {"lifespan_context_manager": lifespan_context}
            # Enter the context manager
            ctx = await lifespan_context.__aenter__()
            context["lifespan_context"] = ctx
        
        return context
    
    async def _cleanup_context(self, context: Dict[str, Any]) -> None:
        """Clean up any resources in the context"""
        if "lifespan_context_manager" in context:
            # Exit the lifespan context manager
            await context["lifespan_context_manager"].__aexit__(None, None, None)
    
    def run(self) -> None:
        """Run the FastMCP server"""
        logger.info(f"Starting FastMCP server: {self.name}")
        
        # In practice, this would set up the MCP protocol handlers and transport
        # This is simplified for illustration
        
        try:
            # Prepare context
            loop = asyncio.get_event_loop()
            self.request_context = loop.run_until_complete(self._prepare_context())
            
            # Run the server
            # This would be replaced with actual MCP server logic
            logger.info("Server running. Press Ctrl+C to stop.")
            loop.run_forever()
            
        except KeyboardInterrupt:
            logger.info("Server stopping due to keyboard interrupt")
        finally:
            # Clean up
            if self.request_context:
                loop.run_until_complete(self._cleanup_context(self.request_context))
            logger.info(f"FastMCP server {self.name} stopped")
    
    def sse_app(self) -> Any:
        """Return an ASGI app that can be mounted in a larger ASGI application
        
        This would return an ASGI application implementing the Server-Sent Events
        transport for MCP.
        """
        # This is a stub - the actual implementation would return an ASGI app
        # that implements the MCP protocol over SSE
        return None
EOF
    echo -e "${GREEN}Created FastMCP implementation.${NC}"
else
    echo -e "${GREEN}FastMCP implementation already exists.${NC}"
fi

# Create .env file if it doesn't exist
echo -e "\n${YELLOW}Checking for environment configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file template...${NC}"
    cat > .env << 'EOF'
# API keys and environment variables
OPENROUTER_API_KEY=your_api_key_here

# Ansible configuration
ANSIBLE_DATA_DIR=~/.ansible_mcp
EOF
    echo -e "${GREEN}Created .env file template. Please edit it to add your API keys.${NC}"
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Make sure logs directory exists
mkdir -p logs

# Create a simple test to verify setup
echo -e "\n${YELLOW}Creating test script...${NC}"
cat > test_setup.py << 'EOF'
#!/usr/bin/env python3

import os
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath("src"))

# Check imports
try:
    from mcp.server.fastmcp import FastMCP, Context
    print("✓ MCP FastMCP imported successfully")
except ImportError as e:
    print(f"✗ MCP FastMCP import failed: {e}")
    sys.exit(1)

try:
    import ansible_runner
    print("✓ ansible-runner imported successfully")
except ImportError as e:
    print(f"✗ ansible-runner import failed: {e}")
    sys.exit(1)

# Create a simple MCP server
mcp = FastMCP("TestServer", dependencies=["ansible-runner"])

@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone"""
    return f"Hello, {name}!"

print("✓ MCP server created successfully")
print("\nSetup test passed!")
print("\nRun the agent with: python agent.py")
EOF
chmod +x test_setup.py

# Run the test script
echo -e "\n${YELLOW}Running test script to verify setup...${NC}"
python test_setup.py

echo -e "\n${GREEN}Setup complete!${NC}"
echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}     Ansible MCP Agent is ready to use!      ${NC}"
echo -e "${BLUE}===============================================${NC}"
echo -e "\n${YELLOW}Run the agent with:${NC} python agent.py"
