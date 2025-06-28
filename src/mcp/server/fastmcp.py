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
