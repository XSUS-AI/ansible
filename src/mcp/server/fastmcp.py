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