from typing import Dict, List, Optional, Literal, Union, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


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
    # Other task attributes
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
    # Other play attributes
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
