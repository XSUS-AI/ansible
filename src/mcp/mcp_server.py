import os
import logging
import tempfile
import json
import yaml
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union, Literal
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

import ansible_runner
from mcp.server.fastmcp import FastMCP, Context

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            'ansible_mcp.log', maxBytes=10_000_000, backupCount=5
        )
    ]
)

logger = logging.getLogger("ansible_mcp")

# Set up environment variables
ANSIBLE_DATA_DIR = os.getenv("ANSIBLE_DATA_DIR", str(Path.home() / ".ansible_mcp"))

# Base Models for Ansible operations
class SSHKeyConfig(BaseModel):
    """Configuration for SSH keys"""
    use_system_keys: bool = Field(
        default=True,
        description="Whether to use system SSH keys from ~/.ssh"
    )
    private_key_path: Optional[str] = Field(
        default=None, 
        description="Path to a specific private key file"
    )
    private_key_content: Optional[str] = Field(
        default=None, 
        description="Content of a private key to use (not recommended for production)"
    )
    key_passphrase: Optional[str] = Field(
        default=None, 
        description="Passphrase for the private key if required"
    )


class InventoryHost(BaseModel):
    """Representation of a host in inventory"""
    name: str = Field(description="Host name or IP address")
    variables: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Host variables"
    )
    groups: List[str] = Field(
        default_factory=list, 
        description="Groups this host belongs to"
    )


class InventoryGroup(BaseModel):
    """Representation of a group in inventory"""
    name: str = Field(description="Group name")
    variables: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Group variables"
    )
    children: List[str] = Field(
        default_factory=list, 
        description="Child groups"
    )


class Inventory(BaseModel):
    """Ansible inventory representation"""
    hosts: List[InventoryHost] = Field(
        default_factory=list, 
        description="List of hosts in the inventory"
    )
    groups: List[InventoryGroup] = Field(
        default_factory=list, 
        description="List of groups in the inventory"
    )
    

class PlaybookTask(BaseModel):
    """Representation of a task in a playbook"""
    name: str = Field(description="Task name")
    module: str = Field(description="Ansible module name")
    args: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Module arguments"
    )
    become: Optional[bool] = Field(
        default=None, 
        description="Whether to use privilege escalation"
    )
    become_user: Optional[str] = Field(
        default=None, 
        description="User to become when using privilege escalation"
    )
    ignore_errors: Optional[bool] = Field(
        default=None, 
        description="Whether to ignore errors for this task"
    )
    when: Optional[Union[str, List[str]]] = Field(
        default=None, 
        description="Conditional expression for when to run the task"
    )
    register: Optional[str] = Field(
        default=None, 
        description="Variable name to store the result"
    )
    loop: Optional[Union[str, List[Any]]] = Field(
        default=None, 
        description="Items to loop over"
    )


class PlaybookPlay(BaseModel):
    """Representation of a play in a playbook"""
    name: str = Field(description="Play name")
    hosts: Union[str, List[str]] = Field(description="Target hosts or groups")
    tasks: List[PlaybookTask] = Field(
        default_factory=list, 
        description="List of tasks in the play"
    )
    become: Optional[bool] = Field(
        default=None, 
        description="Whether to use privilege escalation"
    )
    become_user: Optional[str] = Field(
        default=None, 
        description="User to become when using privilege escalation"
    )
    vars: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Variables for the play"
    )
    roles: List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list, 
        description="Roles to include in the play"
    )
    gather_facts: Optional[bool] = Field(
        default=None, 
        description="Whether to gather facts"
    )


class Playbook(BaseModel):
    """Representation of an Ansible playbook"""
    plays: List[PlaybookPlay] = Field(
        default_factory=list, 
        description="List of plays in the playbook"
    )


class AnsibleConfig(BaseModel):
    """Ansible configuration settings"""
    inventory_path: Optional[str] = Field(
        default=None, 
        description="Path to inventory file or directory"
    )
    inventory: Optional[Inventory] = Field(
        default=None, 
        description="Inventory data if not using a file"
    )
    playbook_path: Optional[str] = Field(
        default=None, 
        description="Path to playbook file"
    )
    playbook: Optional[Playbook] = Field(
        default=None, 
        description="Playbook data if not using a file"
    )
    private_data_dir: Optional[str] = Field(
        default=None, 
        description="Directory for Ansible Runner to use for execution data"
    )
    ssh_config: SSHKeyConfig = Field(
        default_factory=SSHKeyConfig, 
        description="SSH key configuration"
    )
    extra_vars: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Extra variables to pass to Ansible"
    )
    verbosity: int = Field(
        default=0, 
        description="Verbosity level (0-4)"
    )
    timeout: Optional[int] = Field(
        default=None, 
        description="Timeout in seconds"
    )


# Tool Request/Response Models
class PlaybookRunRequest(BaseModel):
    """Request to run a playbook"""
    config: AnsibleConfig = Field(description="Ansible configuration")


class TaskResult(BaseModel):
    """Result of a single task execution"""
    task_name: str = Field(description="Task name")
    host: str = Field(description="Target host")
    status: Literal["ok", "failed", "skipped", "unreachable", "changed"] = Field(
        description="Task execution status"
    )
    changed: bool = Field(description="Whether the task made changes")
    result: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Task execution result data"
    )


class PlaybookRunResult(BaseModel):
    """Result of a playbook run"""
    success: bool = Field(description="Whether the playbook run was successful")
    stats: Dict[str, Dict[str, int]] = Field(
        description="Playbook run statistics by host")
    task_results: List[TaskResult] = Field(
        default_factory=list, 
        description="Results of individual tasks"
    )
    stdout: str = Field(description="Standard output from the playbook run")
    stderr: str = Field(description="Standard error output from the playbook run")


class CreateInventoryRequest(BaseModel):
    """Request to create an inventory"""
    inventory: Inventory = Field(description="Inventory data")
    path: Optional[str] = Field(
        default=None, 
        description="Path to save the inventory file"
    )


class CreateInventoryResponse(BaseModel):
    """Response after creating an inventory"""
    success: bool = Field(description="Whether the operation was successful")
    path: Optional[str] = Field(
        default=None, 
        description="Path where the inventory was saved"
    )
    message: Optional[str] = Field(
        default=None, 
        description="Informational or error message"
    )


class LoadInventoryRequest(BaseModel):
    """Request to load an inventory"""
    path: str = Field(description="Path to the inventory file or directory")


class LoadInventoryResponse(BaseModel):
    """Response after loading an inventory"""
    success: bool = Field(description="Whether the operation was successful")
    inventory: Optional[Inventory] = Field(
        default=None, 
        description="Loaded inventory data"
    )
    message: Optional[str] = Field(
        default=None, 
        description="Informational or error message"
    )


class CreatePlaybookRequest(BaseModel):
    """Request to create a playbook"""
    playbook: Playbook = Field(description="Playbook data")
    path: Optional[str] = Field(
        default=None, 
        description="Path to save the playbook file"
    )


class CreatePlaybookResponse(BaseModel):
    """Response after creating a playbook"""
    success: bool = Field(description="Whether the operation was successful")
    path: Optional[str] = Field(
        default=None, 
        description="Path where the playbook was saved"
    )
    message: Optional[str] = Field(
        default=None, 
        description="Informational or error message"
    )


class LoadPlaybookRequest(BaseModel):
    """Request to load a playbook"""
    path: str = Field(description="Path to the playbook file")


class LoadPlaybookResponse(BaseModel):
    """Response after loading a playbook"""
    success: bool = Field(description="Whether the operation was successful")
    playbook: Optional[Playbook] = Field(
        default=None, 
        description="Loaded playbook data"
    )
    message: Optional[str] = Field(
        default=None, 
        description="Informational or error message"
    )


class AdHocCommandRequest(BaseModel):
    """Request to run an ad-hoc command"""
    hosts: Union[str, List[str]] = Field(description="Target hosts or groups")
    module: str = Field(description="Ansible module to use")
    args: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Module arguments"
    )
    config: AnsibleConfig = Field(description="Ansible configuration")


class AdHocCommandResult(BaseModel):
    """Result of an ad-hoc command"""
    success: bool = Field(description="Whether the command was successful")
    results: Dict[str, Dict[str, Any]] = Field(
        description="Results by host"
    )
    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error output from the command")


class GetSSHKeysRequest(BaseModel):
    """Request to get available SSH keys"""
    pass


class SSHKeyInfo(BaseModel):
    """Information about an SSH key"""
    path: str = Field(description="Path to the SSH key")
    name: str = Field(description="Name/filename of the key")
    type: str = Field(description="Type of the key (e.g., rsa, ed25519)")
    comment: Optional[str] = Field(description="Comment or identifier for the key")


class GetSSHKeysResponse(BaseModel):
    """Response with available SSH keys"""
    success: bool = Field(description="Whether the operation was successful")
    keys: List[SSHKeyInfo] = Field(
        default_factory=list,
        description="List of available SSH keys"
    )
    message: Optional[str] = Field(
        default=None,
        description="Informational or error message"
    )


class ListPlaybooksRequest(BaseModel):
    """Request to list available playbooks"""
    directory: Optional[str] = Field(
        default=None,
        description="Directory to search for playbooks (defaults to standard playbooks directory)"
    )


class PlaybookInfo(BaseModel):
    """Information about a playbook"""
    path: str = Field(description="Path to the playbook file")
    name: str = Field(description="Name of the playbook file")
    size: int = Field(description="Size of the playbook file in bytes")
    modified: str = Field(description="Last modified timestamp")


class ListPlaybooksResponse(BaseModel):
    """Response with list of available playbooks"""
    success: bool = Field(description="Whether the operation was successful")
    playbooks: List[PlaybookInfo] = Field(
        default_factory=list,
        description="List of available playbooks"
    )
    message: Optional[str] = Field(
        default=None,
        description="Informational or error message"
    )


class ListInventoriesRequest(BaseModel):
    """Request to list available inventories"""
    directory: Optional[str] = Field(
        default=None,
        description="Directory to search for inventories (defaults to standard inventory directory)"
    )


class InventoryInfo(BaseModel):
    """Information about an inventory file"""
    path: str = Field(description="Path to the inventory file")
    name: str = Field(description="Name of the inventory file")
    size: int = Field(description="Size of the inventory file in bytes")
    modified: str = Field(description="Last modified timestamp")


class ListInventoriesResponse(BaseModel):
    """Response with list of available inventories"""
    success: bool = Field(description="Whether the operation was successful")
    inventories: List[InventoryInfo] = Field(
        default_factory=list,
        description="List of available inventories"
    )
    message: Optional[str] = Field(
        default=None,
        description="Informational or error message"
    )


class AnsibleServerState(BaseModel):
    """State maintained by the Ansible server"""
    base_dir: Path = Field(description="Base directory for Ansible data")
    playbooks_dir: Path = Field(description="Directory for playbooks")
    inventory_dir: Path = Field(description="Directory for inventory files")
    private_data_dir: Path = Field(description="Directory for private data")


# Set up asynccontext manager for server lifespan
@asynccontextmanager
async def ansible_mcp_lifespan(server: FastMCP):
    """Lifespan for the Ansible MCP server"""
    logger.info("Initializing Ansible MCP Server...")
    
    # Create base directories
    base_dir = Path(ANSIBLE_DATA_DIR)
    base_dir.mkdir(exist_ok=True, parents=True)
    
    playbooks_dir = base_dir / "playbooks"
    inventory_dir = base_dir / "inventory"
    private_data_dir = base_dir / "private"
    
    playbooks_dir.mkdir(exist_ok=True)
    inventory_dir.mkdir(exist_ok=True)
    private_data_dir.mkdir(exist_ok=True)
    
    logger.info(f"Using data directory: {base_dir}")
    
    # Create server state
    state = AnsibleServerState(
        base_dir=base_dir,
        playbooks_dir=playbooks_dir,
        inventory_dir=inventory_dir,
        private_data_dir=private_data_dir
    )
    
    try:
        yield {"state": state}
    finally:
        logger.info("Shutting down Ansible MCP Server...")


# Initialize FastMCP
mcp = FastMCP(
    "AnsibleMCP", 
    dependencies=["ansible-runner", "pyyaml"],
    lifespan=ansible_mcp_lifespan
)


# Tool functions
@mcp.tool()
async def run_playbook(request: PlaybookRunRequest, ctx: Context) -> PlaybookRunResult:
    """Run an Ansible playbook with specified configuration"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        await ctx.info("Preparing to run playbook...")
        
        # Create a private data directory for this run
        run_id = uuid.uuid4().hex
        private_data_dir = state.private_data_dir / f"run_{run_id}"
        private_data_dir.mkdir(exist_ok=True)
        
        # Prepare inventory
        inventory_path = request.config.inventory_path
        if request.config.inventory and not inventory_path:
            await ctx.info("Creating temporary inventory from provided data...")
            inventory_data = {}
            
            # Process hosts
            for host in request.config.inventory.hosts:
                if host.groups:
                    # Add host to its groups
                    for group in host.groups:
                        if group not in inventory_data:
                            inventory_data[group] = {'hosts': {}}
                        elif 'hosts' not in inventory_data[group]:
                            inventory_data[group]['hosts'] = {}
                        
                        inventory_data[group]['hosts'][host.name] = host.variables
                else:
                    # Host not in any group, add to 'ungrouped'
                    if 'ungrouped' not in inventory_data:
                        inventory_data['ungrouped'] = {'hosts': {}}
                    elif 'hosts' not in inventory_data['ungrouped']:
                        inventory_data['ungrouped']['hosts'] = {}
                    
                    inventory_data['ungrouped']['hosts'][host.name] = host.variables
            
            # Process groups
            for group in request.config.inventory.groups:
                if group.name not in inventory_data:
                    inventory_data[group.name] = {}
                
                # Add variables
                if group.variables:
                    inventory_data[group.name]['vars'] = group.variables
                
                # Add children
                if group.children:
                    if 'children' not in inventory_data[group.name]:
                        inventory_data[group.name]['children'] = {}
                    
                    for child in group.children:
                        inventory_data[group.name]['children'][child] = {}
            
            # Create inventory directory and file
            inventory_dir = private_data_dir / "inventory"
            inventory_dir.mkdir(exist_ok=True)
            inventory_file = inventory_dir / "inventory.yml"
            
            with open(inventory_file, 'w') as f:
                yaml.safe_dump(inventory_data, f)
            
            inventory_path = str(inventory_file)
        
        # Prepare playbook
        playbook_path = request.config.playbook_path
        if request.config.playbook and not playbook_path:
            await ctx.info("Creating temporary playbook from provided data...")
            # Convert Playbook to dictionary format
            playbook_data = []
            for play in request.config.playbook.plays:
                play_dict = play.model_dump(exclude_none=True)
                
                # Process tasks
                if 'tasks' in play_dict:
                    play_dict['tasks'] = [task.model_dump(exclude_none=True) for task in play.tasks]
                
                playbook_data.append(play_dict)
            
            # Create playbook file
            temp_dir = private_data_dir / "project"
            temp_dir.mkdir(exist_ok=True)
            playbook_file = temp_dir / "playbook.yml"
            
            with open(playbook_file, 'w') as f:
                yaml.safe_dump(playbook_data, f)
            
            playbook_path = str(playbook_file)
        
        # Set up SSH keys if needed
        ssh_config = request.config.ssh_config
        if ssh_config and (ssh_config.private_key_path or ssh_config.private_key_content):
            await ctx.info("Setting up SSH keys...")
            ssh_dir = private_data_dir / "env"
            ssh_dir.mkdir(exist_ok=True)
            
            # If a specific private key is provided, use it
            if ssh_config.private_key_path:
                # Copy the key to the private data directory
                shutil.copy(ssh_config.private_key_path, ssh_dir / "ssh_key")
            
            # If private key content is provided, write it to a file
            elif ssh_config.private_key_content:
                with open(ssh_dir / "ssh_key", 'w') as f:
                    f.write(ssh_config.private_key_content)
                os.chmod(ssh_dir / "ssh_key", 0o600)  # Set proper permissions
        
        # Prepare runner config
        runner_config = {
            'private_data_dir': str(private_data_dir),
            'verbosity': request.config.verbosity
        }
        
        if inventory_path:
            runner_config['inventory'] = inventory_path
        
        if playbook_path:
            runner_config['playbook'] = playbook_path
        
        if request.config.extra_vars:
            runner_config['extravars'] = request.config.extra_vars
        
        if request.config.timeout:
            runner_config['timeout'] = request.config.timeout
        
        # Run the playbook
        await ctx.info(f"Running playbook {playbook_path}...")
        logger.info(f"Running playbook with config: {runner_config}")
        
        runner = ansible_runner.run(**runner_config)
        
        # Process results
        task_results = []
        for event in runner.events:
            if event['event'] == 'runner_on_ok':
                task_result = TaskResult(
                    task_name=event['event_data'].get('task', 'unnamed task'),
                    host=event['event_data'].get('host', ''),
                    status='ok',
                    changed=event['event_data'].get('changed', False),
                    result=event['event_data'].get('res', {})
                )
                task_results.append(task_result)
            
            elif event['event'] == 'runner_on_failed':
                task_result = TaskResult(
                    task_name=event['event_data'].get('task', 'unnamed task'),
                    host=event['event_data'].get('host', ''),
                    status='failed',
                    changed=event['event_data'].get('changed', False),
                    result=event['event_data'].get('res', {})
                )
                task_results.append(task_result)
            
            elif event['event'] == 'runner_on_skipped':
                task_result = TaskResult(
                    task_name=event['event_data'].get('task', 'unnamed task'),
                    host=event['event_data'].get('host', ''),
                    status='skipped',
                    changed=False,
                    result={}
                )
                task_results.append(task_result)
            
            elif event['event'] == 'runner_on_unreachable':
                task_result = TaskResult(
                    task_name=event['event_data'].get('task', 'unnamed task'),
                    host=event['event_data'].get('host', ''),
                    status='unreachable',
                    changed=False,
                    result=event['event_data'].get('res', {})
                )
                task_results.append(task_result)
            
            elif event['event'] == 'runner_on_changed':
                task_result = TaskResult(
                    task_name=event['event_data'].get('task', 'unnamed task'),
                    host=event['event_data'].get('host', ''),
                    status='changed',
                    changed=True,
                    result=event['event_data'].get('res', {})
                )
                task_results.append(task_result)
        
        # Get stdout and stderr
        stdout = ""
        stdout_path = private_data_dir / "stdout"
        if stdout_path.exists():
            with open(stdout_path) as f:
                stdout = f.read()
        
        stderr = ""
        stderr_path = private_data_dir / "stderr"
        if stderr_path.exists():
            with open(stderr_path) as f:
                stderr = f.read()
        
        success = runner.rc == 0
        result_msg = "Successfully completed" if success else "Failed"
        await ctx.info(f"{result_msg} playbook execution.")
        
        # Clean up temporary directory after a successful run
        shutil.rmtree(private_data_dir, ignore_errors=True)
        
        return PlaybookRunResult(
            success=success,
            stats=runner.stats,
            task_results=task_results,
            stdout=stdout,
            stderr=stderr
        )
    
    except Exception as e:
        logger.exception("Error running playbook")
        # Clean up temporary directory in case of error
        if 'private_data_dir' in locals():
            shutil.rmtree(private_data_dir, ignore_errors=True)
        
        return PlaybookRunResult(
            success=False,
            stats={},
            task_results=[],
            stdout="",
            stderr=str(e)
        )


@mcp.tool()
async def run_ad_hoc_command(request: AdHocCommandRequest, ctx: Context) -> AdHocCommandResult:
    """Run an ad-hoc Ansible command on specified hosts"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        await ctx.info(f"Preparing to run ad-hoc command with module {request.module}...")
        
        # Create a private data directory for this run
        run_id = uuid.uuid4().hex
        private_data_dir = state.private_data_dir / f"run_{run_id}"
        private_data_dir.mkdir(exist_ok=True)
        
        # Prepare inventory (same as in run_playbook)
        inventory_path = request.config.inventory_path
        if request.config.inventory and not inventory_path:
            await ctx.info("Creating temporary inventory from provided data...")
            inventory_data = {}
            
            # Process hosts
            for host in request.config.inventory.hosts:
                if host.groups:
                    # Add host to its groups
                    for group in host.groups:
                        if group not in inventory_data:
                            inventory_data[group] = {'hosts': {}}
                        elif 'hosts' not in inventory_data[group]:
                            inventory_data[group]['hosts'] = {}
                        
                        inventory_data[group]['hosts'][host.name] = host.variables
                else:
                    # Host not in any group, add to 'ungrouped'
                    if 'ungrouped' not in inventory_data:
                        inventory_data['ungrouped'] = {'hosts': {}}
                    elif 'hosts' not in inventory_data['ungrouped']:
                        inventory_data['ungrouped']['hosts'] = {}
                    
                    inventory_data['ungrouped']['hosts'][host.name] = host.variables
            
            # Process groups
            for group in request.config.inventory.groups:
                if group.name not in inventory_data:
                    inventory_data[group.name] = {}
                
                # Add variables
                if group.variables:
                    inventory_data[group.name]['vars'] = group.variables
                
                # Add children
                if group.children:
                    if 'children' not in inventory_data[group.name]:
                        inventory_data[group.name]['children'] = {}
                    
                    for child in group.children:
                        inventory_data[group.name]['children'][child] = {}
            
            # Create inventory directory and file
            inventory_dir = private_data_dir / "inventory"
            inventory_dir.mkdir(exist_ok=True)
            inventory_file = inventory_dir / "inventory.yml"
            
            with open(inventory_file, 'w') as f:
                yaml.safe_dump(inventory_data, f)
            
            inventory_path = str(inventory_file)
        
        # Set up SSH keys if needed
        ssh_config = request.config.ssh_config
        if ssh_config and (ssh_config.private_key_path or ssh_config.private_key_content):
            await ctx.info("Setting up SSH keys...")
            ssh_dir = private_data_dir / "env"
            ssh_dir.mkdir(exist_ok=True)
            
            # If a specific private key is provided, use it
            if ssh_config.private_key_path:
                # Copy the key to the private data directory
                shutil.copy(ssh_config.private_key_path, ssh_dir / "ssh_key")
            
            # If private key content is provided, write it to a file
            elif ssh_config.private_key_content:
                with open(ssh_dir / "ssh_key", 'w') as f:
                    f.write(ssh_config.private_key_content)
                os.chmod(ssh_dir / "ssh_key", 0o600)  # Set proper permissions
        
        # Prepare runner config
        runner_config = {
            'private_data_dir': str(private_data_dir),
            'verbosity': request.config.verbosity
        }
        
        if inventory_path:
            runner_config['inventory'] = inventory_path
        
        if request.config.extra_vars:
            runner_config['extravars'] = request.config.extra_vars
        
        if request.config.timeout:
            runner_config['timeout'] = request.config.timeout
        
        # Prepare hosts
        hosts = request.hosts
        if isinstance(hosts, list):
            hosts = ','.join(hosts)
        
        # Create module arguments string
        module_args = ''
        for key, value in request.args.items():
            if isinstance(value, bool):
                if value:
                    module_args += f" {key}=yes"
                else:
                    module_args += f" {key}=no"
            elif isinstance(value, (int, float)):
                module_args += f" {key}={value}"
            else:
                module_args += f" {key}='{value}'"  # For string values
        
        # Set up the ad-hoc command
        runner_config.update({
            'host_pattern': hosts,
            'module': request.module,
            'module_args': module_args.strip()
        })
        
        # Run the command
        await ctx.info(f"Running ad-hoc command with module {request.module} on {hosts}...")
        logger.info(f"Running ad-hoc command with config: {runner_config}")
        
        runner = ansible_runner.run(**runner_config)
        
        # Get results by host
        results = {}
        for event in runner.events:
            if event['event'] in ['runner_on_ok', 'runner_on_failed', 'runner_on_unreachable']:
                host = event['event_data'].get('host')
                if host:
                    results[host] = event['event_data'].get('res', {})
        
        # Get stdout and stderr
        stdout = ""
        stdout_path = private_data_dir / "stdout"
        if stdout_path.exists():
            with open(stdout_path) as f:
                stdout = f.read()
        
        stderr = ""
        stderr_path = private_data_dir / "stderr"
        if stderr_path.exists():
            with open(stderr_path) as f:
                stderr = f.read()
        
        success = runner.rc == 0
        result_msg = "Successfully completed" if success else "Failed"
        await ctx.info(f"{result_msg} ad-hoc command execution.")
        
        # Clean up temporary directory after a successful run
        shutil.rmtree(private_data_dir, ignore_errors=True)
        
        return AdHocCommandResult(
            success=success,
            results=results,
            stdout=stdout,
            stderr=stderr
        )
    
    except Exception as e:
        logger.exception("Error running ad-hoc command")
        # Clean up temporary directory in case of error
        if 'private_data_dir' in locals():
            shutil.rmtree(private_data_dir, ignore_errors=True)
        
        return AdHocCommandResult(
            success=False,
            results={},
            stdout="",
            stderr=str(e)
        )


@mcp.tool()
async def create_inventory(request: CreateInventoryRequest, ctx: Context) -> CreateInventoryResponse:
    """Create an Ansible inventory file from structured data"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        await ctx.info("Creating inventory file...")
        
        # Generate inventory data
        inventory_data = {}
        
        # Process hosts
        for host in request.inventory.hosts:
            if host.groups:
                # Add host to its groups
                for group in host.groups:
                    if group not in inventory_data:
                        inventory_data[group] = {'hosts': {}}
                    elif 'hosts' not in inventory_data[group]:
                        inventory_data[group]['hosts'] = {}
                    
                    inventory_data[group]['hosts'][host.name] = host.variables
            else:
                # Host not in any group, add to 'ungrouped'
                if 'ungrouped' not in inventory_data:
                    inventory_data['ungrouped'] = {'hosts': {}}
                elif 'hosts' not in inventory_data['ungrouped']:
                    inventory_data['ungrouped']['hosts'] = {}
                
                inventory_data['ungrouped']['hosts'][host.name] = host.variables
        
        # Process groups
        for group in request.inventory.groups:
            if group.name not in inventory_data:
                inventory_data[group.name] = {}
            
            # Add variables
            if group.variables:
                inventory_data[group.name]['vars'] = group.variables
            
            # Add children
            if group.children:
                if 'children' not in inventory_data[group.name]:
                    inventory_data[group.name]['children'] = {}
                
                for child in group.children:
                    inventory_data[group.name]['children'][child] = {}
        
        # Determine output path
        if request.path:
            output_path = request.path
        else:
            output_path = state.inventory_dir / f"inventory_{uuid.uuid4().hex}.yml"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Write inventory to file
        with open(output_path, 'w') as f:
            yaml.safe_dump(inventory_data, f)
        
        await ctx.info(f"Inventory created at {output_path}")
        
        return CreateInventoryResponse(
            success=True,
            path=str(output_path),
            message=f"Inventory created successfully at {output_path}"
        )
    
    except Exception as e:
        logger.exception("Error creating inventory")
        return CreateInventoryResponse(
            success=False,
            message=f"Failed to create inventory: {str(e)}"
        )


@mcp.tool()
async def load_inventory(request: LoadInventoryRequest, ctx: Context) -> LoadInventoryResponse:
    """Load an Ansible inventory file and parse its contents"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        await ctx.info(f"Loading inventory from {request.path}...")
        
        # Check if the path exists
        if not os.path.exists(request.path):
            return LoadInventoryResponse(
                success=False,
                message=f"Inventory file not found: {request.path}"
            )
        
        # Parse inventory using ansible-inventory command
        runner_config = {
            'private_data_dir': str(state.private_data_dir),
            'inventory': request.path,
        }
        
        # Get JSON representation of the inventory
        result = ansible_runner.run_command(
            executable_cmd='ansible-inventory',
            cmdline_args=['--list', '--export'],
            **runner_config
        )
        
        if result[0] != 0:  # Command failed
            return LoadInventoryResponse(
                success=False,
                message=f"Failed to load inventory: {result[1]}"
            )
        
        # Parse the JSON output
        inventory_json = json.loads(result[1])
        
        # Convert to our Inventory model
        inventory = Inventory(hosts=[], groups=[])
        
        # Process host entries
        all_hosts = set()
        host_groups = {}
        
        for group_name, group_data in inventory_json.items():
            if group_name in ['_meta', 'all']:
                continue
            
            # Get hosts in this group
            if 'hosts' in group_data:
                for host_name in group_data['hosts']:
                    all_hosts.add(host_name)
                    if host_name not in host_groups:
                        host_groups[host_name] = []
                    host_groups[host_name].append(group_name)
            
            # Add group
            group = InventoryGroup(
                name=group_name,
                variables=group_data.get('vars', {}),
                children=list(group_data.get('children', []))
            )
            inventory.groups.append(group)
        
        # Process host variables
        if '_meta' in inventory_json and 'hostvars' in inventory_json['_meta']:
            for host_name, host_vars in inventory_json['_meta']['hostvars'].items():
                host = InventoryHost(
                    name=host_name,
                    variables=host_vars,
                    groups=host_groups.get(host_name, [])
                )
                inventory.hosts.append(host)
        else:
            # No host variables, just create hosts with empty variables
            for host_name in all_hosts:
                host = InventoryHost(
                    name=host_name,
                    groups=host_groups.get(host_name, [])
                )
                inventory.hosts.append(host)
        
        await ctx.info(f"Successfully loaded inventory with {len(inventory.hosts)} hosts and {len(inventory.groups)} groups")
        
        return LoadInventoryResponse(
            success=True,
            inventory=inventory,
            message=f"Inventory loaded successfully from {request.path}"
        )
    
    except Exception as e:
        logger.exception("Error loading inventory")
        return LoadInventoryResponse(
            success=False,
            message=f"Failed to load inventory: {str(e)}"
        )


@mcp.tool()
async def create_playbook(request: CreatePlaybookRequest, ctx: Context) -> CreatePlaybookResponse:
    """Create an Ansible playbook file from structured data"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        await ctx.info("Creating playbook file...")
        
        # Convert Playbook to dictionary format
        playbook_data = []
        for play in request.playbook.plays:
            play_dict = play.model_dump(exclude_none=True)
            
            # Process tasks
            if 'tasks' in play_dict:
                play_dict['tasks'] = [task.model_dump(exclude_none=True) for task in play.tasks]
            
            playbook_data.append(play_dict)
        
        # Determine output path
        if request.path:
            output_path = request.path
        else:
            output_path = state.playbooks_dir / f"playbook_{uuid.uuid4().hex}.yml"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Write playbook to file
        with open(output_path, 'w') as f:
            yaml.safe_dump(playbook_data, f)
        
        await ctx.info(f"Playbook created at {output_path}")
        
        return CreatePlaybookResponse(
            success=True,
            path=str(output_path),
            message=f"Playbook created successfully at {output_path}"
        )
    
    except Exception as e:
        logger.exception("Error creating playbook")
        return CreatePlaybookResponse(
            success=False,
            message=f"Failed to create playbook: {str(e)}"
        )


@mcp.tool()
async def load_playbook(request: LoadPlaybookRequest, ctx: Context) -> LoadPlaybookResponse:
    """Load an Ansible playbook file and parse its contents"""
    try:
        await ctx.info(f"Loading playbook from {request.path}...")
        
        # Check if the path exists
        if not os.path.exists(request.path):
            return LoadPlaybookResponse(
                success=False,
                message=f"Playbook file not found: {request.path}"
            )
        
        # Read the playbook file
        with open(request.path, 'r') as f:
            playbook_data = yaml.safe_load(f)
        
        # Convert to our Playbook model
        plays = []
        
        for play_data in playbook_data:
            # Extract tasks
            tasks = []
            if 'tasks' in play_data:
                for task_data in play_data['tasks']:
                    module_name = None
                    args = {}
                    
                    # Find the module being used
                    for key, value in task_data.items():
                        if key not in [
                            'name', 'become', 'become_user', 'ignore_errors', 
                            'when', 'register', 'loop', 'loop_control'
                        ]:
                            module_name = key
                            if isinstance(value, dict):
                                args = value
                            else:
                                args = {"_raw_params": value}
                            break
                    
                    if not module_name:
                        continue  # Skip if no module found
                    
                    task = PlaybookTask(
                        name=task_data.get('name', 'Unnamed task'),
                        module=module_name,
                        args=args,
                        become=task_data.get('become'),
                        become_user=task_data.get('become_user'),
                        ignore_errors=task_data.get('ignore_errors'),
                        when=task_data.get('when'),
                        register=task_data.get('register'),
                        loop=task_data.get('loop')
                    )
                    tasks.append(task)
            
            # Create the play
            play = PlaybookPlay(
                name=play_data.get('name', 'Unnamed play'),
                hosts=play_data.get('hosts'),
                tasks=tasks,
                become=play_data.get('become'),
                become_user=play_data.get('become_user'),
                vars=play_data.get('vars', {}),
                roles=play_data.get('roles', []),
                gather_facts=play_data.get('gather_facts')
            )
            plays.append(play)
        
        playbook = Playbook(plays=plays)
        
        await ctx.info(f"Successfully loaded playbook with {len(plays)} plays")
        
        return LoadPlaybookResponse(
            success=True,
            playbook=playbook,
            message=f"Playbook loaded successfully from {request.path}"
        )
    
    except Exception as e:
        logger.exception("Error loading playbook")
        return LoadPlaybookResponse(
            success=False,
            message=f"Failed to load playbook: {str(e)}"
        )


@mcp.tool()
async def get_ssh_keys(request: GetSSHKeysRequest, ctx: Context) -> GetSSHKeysResponse:
    """Get list of available SSH keys in the system"""
    try:
        await ctx.info("Retrieving available SSH keys...")
        
        # First, check the standard ~/.ssh directory
        ssh_dir = Path.home() / ".ssh"
        
        if not ssh_dir.exists():
            return GetSSHKeysResponse(
                success=True,
                keys=[],
                message="SSH directory not found"
            )
        
        keys = []
        
        # Find private keys (files without .pub extension and with typical key patterns)
        for file_path in ssh_dir.glob("*"):
            if file_path.is_file() and not file_path.name.endswith(".pub") and not file_path.name in ["known_hosts", "authorized_keys", "config"]:
                # Try to determine the key type
                try:
                    # Use ssh-keygen to get key information
                    result = subprocess.run(
                        ["ssh-keygen", "-l", "-f", str(file_path)],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        # Parse output like: 2048 SHA256:abcdef user@host (RSA)
                        output = result.stdout.strip()
                        parts = output.split()
                        
                        # Extract key type from last part which is like (RSA)
                        key_type = ""
                        if len(parts) >= 4:
                            key_type = parts[-1].strip("()").lower()
                        
                        # Extract comment/identifier (usually user@host)
                        comment = ""
                        if len(parts) >= 3:
                            comment = parts[-2]
                        
                        keys.append(SSHKeyInfo(
                            path=str(file_path),
                            name=file_path.name,
                            type=key_type,
                            comment=comment
                        ))
                except Exception as e:
                    logger.warning(f"Could not process key {file_path}: {str(e)}")
                    # Add without detailed info
                    keys.append(SSHKeyInfo(
                        path=str(file_path),
                        name=file_path.name,
                        type="unknown"
                    ))
        
        await ctx.info(f"Found {len(keys)} SSH keys")
        
        return GetSSHKeysResponse(
            success=True,
            keys=keys,
            message=f"Found {len(keys)} SSH keys"
        )
    
    except Exception as e:
        logger.exception("Error getting SSH keys")
        return GetSSHKeysResponse(
            success=False,
            keys=[],
            message=f"Failed to get SSH keys: {str(e)}"
        )


@mcp.tool()
async def list_playbooks(request: ListPlaybooksRequest, ctx: Context) -> ListPlaybooksResponse:
    """List available Ansible playbooks in the specified directory"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        directory = request.directory if request.directory else state.playbooks_dir
        
        await ctx.info(f"Listing playbooks in {directory}...")
        
        if not os.path.exists(directory):
            return ListPlaybooksResponse(
                success=False,
                message=f"Directory not found: {directory}"
            )
        
        playbooks = []
        
        # Look for YAML files that could be playbooks
        for file_path in Path(directory).glob("**/*.y*ml"):
            if file_path.is_file():
                # Try to validate it's an Ansible playbook by looking at content
                try:
                    with open(file_path, 'r') as f:
                        content = yaml.safe_load(f)
                        
                        # Basic validation: should be a list of plays with hosts
                        if isinstance(content, list) and all(isinstance(item, dict) and 'hosts' in item for item in content):
                            stat = file_path.stat()
                            playbooks.append(PlaybookInfo(
                                path=str(file_path),
                                name=file_path.name,
                                size=stat.st_size,
                                modified=str(stat.st_mtime)
                            ))
                except Exception as e:
                    logger.debug(f"Could not validate {file_path} as playbook: {str(e)}")
                    # Skip non-valid files
                    pass
        
        await ctx.info(f"Found {len(playbooks)} playbooks")
        
        return ListPlaybooksResponse(
            success=True,
            playbooks=playbooks,
            message=f"Found {len(playbooks)} playbooks"
        )
    
    except Exception as e:
        logger.exception("Error listing playbooks")
        return ListPlaybooksResponse(
            success=False,
            playbooks=[],
            message=f"Failed to list playbooks: {str(e)}"
        )


@mcp.tool()
async def list_inventories(request: ListInventoriesRequest, ctx: Context) -> ListInventoriesResponse:
    """List available Ansible inventory files in the specified directory"""
    state = ctx.request_context.lifespan_context["state"]
    
    try:
        directory = request.directory if request.directory else state.inventory_dir
        
        await ctx.info(f"Listing inventories in {directory}...")
        
        if not os.path.exists(directory):
            return ListInventoriesResponse(
                success=False,
                message=f"Directory not found: {directory}"
            )
        
        inventories = []
        
        # Look for YAML/JSON/INI files that could be inventories
        for file_pattern in ["*.y*ml", "*.json", "*.ini"]:
            for file_path in Path(directory).glob(f"**/{file_pattern}"):
                if file_path.is_file():
                    # We don't do content validation for inventories since they can be in various formats
                    stat = file_path.stat()
                    inventories.append(InventoryInfo(
                        path=str(file_path),
                        name=file_path.name,
                        size=stat.st_size,
                        modified=str(stat.st_mtime)
                    ))
        
        await ctx.info(f"Found {len(inventories)} inventories")
        
        return ListInventoriesResponse(
            success=True,
            inventories=inventories,
            message=f"Found {len(inventories)} inventories"
        )
    
    except Exception as e:
        logger.exception("Error listing inventories")
        return ListInventoriesResponse(
            success=False,
            inventories=[],
            message=f"Failed to list inventories: {str(e)}"
        )


def main():
    mcp.run()
    
if __name__ == "__main__":
    main()
