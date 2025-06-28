import os
import tempfile
import shutil
import json
import yaml
import uuid
from typing import Dict, List, Optional, Any, Tuple, Generator, Union
from pathlib import Path
import ansible_runner
from .models import (
    SSHKeyConfig, AnsibleConfig, Inventory, InventoryHost, InventoryGroup,
    Playbook, PlaybookPlay, PlaybookTask, PlaybookRunRequest, PlaybookRunResult, 
    TaskResult, CreateInventoryRequest, CreateInventoryResponse, LoadInventoryRequest,
    LoadInventoryResponse, CreatePlaybookRequest, CreatePlaybookResponse,
    LoadPlaybookRequest, LoadPlaybookResponse, AdHocCommandRequest, AdHocCommandResult
)


class AnsibleClient:
    """Client for interacting with Ansible via ansible-runner"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """Initialize the Ansible client
        
        Args:
            base_dir: Base directory for storing Ansible data (playbooks, inventory, etc.)
                      If None, a default directory will be used
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            # Use current working directory if no base_dir provided
            self.base_dir = Path.cwd() / "ansible_data"
        
        # Create base directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Create subdirectories
        self.playbooks_dir = self.base_dir / "playbooks"
        self.inventory_dir = self.base_dir / "inventory"
        self.private_data_dir = self.base_dir / "private"
        
        os.makedirs(self.playbooks_dir, exist_ok=True)
        os.makedirs(self.inventory_dir, exist_ok=True)
        os.makedirs(self.private_data_dir, exist_ok=True)
    
    def _setup_ssh_keys(self, ssh_config: SSHKeyConfig, private_data_dir: str) -> None:
        """Set up SSH keys for Ansible Runner
        
        Args:
            ssh_config: SSH key configuration
            private_data_dir: Directory where to store SSH key files
        """
        ssh_dir = os.path.join(private_data_dir, 'env')
        os.makedirs(ssh_dir, exist_ok=True)
        
        # If a specific private key is provided, use it
        if ssh_config.private_key_path:
            # Copy the key to the private data directory
            shutil.copy(ssh_config.private_key_path, os.path.join(ssh_dir, 'ssh_key'))
        
        # If private key content is provided, write it to a file
        elif ssh_config.private_key_content:
            with open(os.path.join(ssh_dir, 'ssh_key'), 'w') as f:
                f.write(ssh_config.private_key_content)
            os.chmod(os.path.join(ssh_dir, 'ssh_key'), 0o600)  # Set proper permissions
    
    def _create_temp_inventory(self, inventory: Inventory) -> str:
        """Create a temporary inventory file from an Inventory object
        
        Args:
            inventory: Inventory object
            
        Returns:
            Path to the temporary inventory file
        """
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="ansible_inventory_")
        
        inventory_data = {}
        
        # Process hosts
        for host in inventory.hosts:
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
        for group in inventory.groups:
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
        
        # Write inventory to file
        inventory_file = os.path.join(temp_dir, 'inventory.yml')
        with open(inventory_file, 'w') as f:
            yaml.safe_dump(inventory_data, f)
        
        return inventory_file
    
    def _create_temp_playbook(self, playbook: Playbook) -> str:
        """Create a temporary playbook file from a Playbook object
        
        Args:
            playbook: Playbook object
            
        Returns:
            Path to the temporary playbook file
        """
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="ansible_playbook_")
        
        # Convert Playbook to dictionary format
        playbook_data = []
        for play in playbook.plays:
            play_dict = play.model_dump(exclude_none=True)
            
            # Process tasks
            if 'tasks' in play_dict:
                play_dict['tasks'] = [task.model_dump(exclude_none=True) for task in play.tasks]
            
            playbook_data.append(play_dict)
        
        # Write playbook to file
        playbook_file = os.path.join(temp_dir, 'playbook.yml')
        with open(playbook_file, 'w') as f:
            yaml.safe_dump(playbook_data, f)
        
        return playbook_file
    
    def _prepare_runner_config(self, config: AnsibleConfig) -> Tuple[str, Dict[str, Any]]:
        """Prepare configuration for Ansible Runner
        
        Args:
            config: Ansible configuration
            
        Returns:
            Tuple of (private_data_dir, runner_config)
        """
        # Create a private data directory for this run
        private_data_dir = os.path.join(self.private_data_dir, f"run_{uuid.uuid4().hex}")
        os.makedirs(private_data_dir, exist_ok=True)
        
        # Prepare inventory
        inventory_path = config.inventory_path
        if config.inventory and not inventory_path:
            inventory_path = self._create_temp_inventory(config.inventory)
        
        # Prepare playbook
        playbook_path = config.playbook_path
        if config.playbook and not playbook_path:
            playbook_path = self._create_temp_playbook(config.playbook)
        
        # Set up SSH keys if needed
        if config.ssh_config and (config.ssh_config.private_key_path or config.ssh_config.private_key_content):
            self._setup_ssh_keys(config.ssh_config, private_data_dir)
        
        # Prepare runner config
        runner_config = {
            'private_data_dir': private_data_dir,
            'verbosity': config.verbosity,
        }
        
        if inventory_path:
            runner_config['inventory'] = inventory_path
        
        if playbook_path:
            runner_config['playbook'] = playbook_path
        
        if config.extra_vars:
            runner_config['extravars'] = config.extra_vars
        
        if config.timeout:
            runner_config['timeout'] = config.timeout
        
        return private_data_dir, runner_config
    
    def _process_events(self, runner: Any) -> List[TaskResult]:
        """Process events from Ansible Runner
        
        Args:
            runner: Ansible Runner instance
            
        Returns:
            List of TaskResult objects
        """
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
        
        return task_results
    
    async def run_playbook(self, request: PlaybookRunRequest) -> PlaybookRunResult:
        """Run an Ansible playbook
        
        Args:
            request: Request with playbook and configuration
            
        Returns:
            Result of the playbook run
        """
        try:
            # Prepare configuration
            private_data_dir, runner_config = self._prepare_runner_config(request.config)
            
            # Run the playbook
            runner = ansible_runner.run(**runner_config)
            
            # Process results
            task_results = self._process_events(runner)
            
            # Get stdout and stderr
            stdout = ""
            with open(os.path.join(private_data_dir, 'stdout')) as f:
                stdout = f.read()
            
            stderr = ""
            stderr_path = os.path.join(private_data_dir, 'stderr')
            if os.path.exists(stderr_path):
                with open(stderr_path) as f:
                    stderr = f.read()
            
            # Clean up temporary directory after a successful run
            shutil.rmtree(private_data_dir, ignore_errors=True)
            
            return PlaybookRunResult(
                success=(runner.rc == 0),
                stats=runner.stats,
                task_results=task_results,
                stdout=stdout,
                stderr=stderr
            )
        
        except Exception as e:
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
    
    async def run_ad_hoc_command(self, request: AdHocCommandRequest) -> AdHocCommandResult:
        """Run an ad-hoc Ansible command
        
        Args:
            request: Request with command details
            
        Returns:
            Result of the command
        """
        try:
            # Prepare configuration
            private_data_dir, runner_config = self._prepare_runner_config(request.config)
            
            # Override playbook with module and module_args
            if 'playbook' in runner_config:
                del runner_config['playbook']
            
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
                    module_args += f" {key}=\'{value}\'"  # For string values
            
            # Set up the ad-hoc command
            runner_config.update({
                'host_pattern': hosts,
                'module': request.module,
                'module_args': module_args.strip()
            })
            
            # Run the command
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
            with open(os.path.join(private_data_dir, 'stdout')) as f:
                stdout = f.read()
            
            stderr = ""
            stderr_path = os.path.join(private_data_dir, 'stderr')
            if os.path.exists(stderr_path):
                with open(stderr_path) as f:
                    stderr = f.read()
            
            # Clean up temporary directory after a successful run
            shutil.rmtree(private_data_dir, ignore_errors=True)
            
            return AdHocCommandResult(
                success=(runner.rc == 0),
                results=results,
                stdout=stdout,
                stderr=stderr
            )
        
        except Exception as e:
            # Clean up temporary directory in case of error
            if 'private_data_dir' in locals():
                shutil.rmtree(private_data_dir, ignore_errors=True)
            
            return AdHocCommandResult(
                success=False,
                results={},
                stdout="",
                stderr=str(e)
            )
    
    async def create_inventory(self, request: CreateInventoryRequest) -> CreateInventoryResponse:
        """Create an inventory file
        
        Args:
            request: Request with inventory details
            
        Returns:
            Result of the inventory creation
        """
        try:
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
                output_path = os.path.join(self.inventory_dir, f"inventory_{uuid.uuid4().hex}.yml")
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Write inventory to file
            with open(output_path, 'w') as f:
                yaml.safe_dump(inventory_data, f)
            
            return CreateInventoryResponse(
                success=True,
                path=output_path,
                message=f"Inventory created successfully at {output_path}"
            )
        
        except Exception as e:
            return CreateInventoryResponse(
                success=False,
                message=f"Failed to create inventory: {str(e)}"
            )
    
    async def load_inventory(self, request: LoadInventoryRequest) -> LoadInventoryResponse:
        """Load an inventory file
        
        Args:
            request: Request with inventory file path
            
        Returns:
            Loaded inventory data
        """
        try:
            # Check if the path exists
            if not os.path.exists(request.path):
                return LoadInventoryResponse(
                    success=False,
                    message=f"Inventory file not found: {request.path}"
                )
            
            # Parse inventory using ansible-inventory command
            runner_config = {
                'private_data_dir': self.private_data_dir,
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
            
            return LoadInventoryResponse(
                success=True,
                inventory=inventory,
                message=f"Inventory loaded successfully from {request.path}"
            )
        
        except Exception as e:
            return LoadInventoryResponse(
                success=False,
                message=f"Failed to load inventory: {str(e)}"
            )
    
    async def create_playbook(self, request: CreatePlaybookRequest) -> CreatePlaybookResponse:
        """Create a playbook file
        
        Args:
            request: Request with playbook details
            
        Returns:
            Result of the playbook creation
        """
        try:
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
                output_path = os.path.join(self.playbooks_dir, f"playbook_{uuid.uuid4().hex}.yml")
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Write playbook to file
            with open(output_path, 'w') as f:
                yaml.safe_dump(playbook_data, f)
            
            return CreatePlaybookResponse(
                success=True,
                path=output_path,
                message=f"Playbook created successfully at {output_path}"
            )
        
        except Exception as e:
            return CreatePlaybookResponse(
                success=False,
                message=f"Failed to create playbook: {str(e)}"
            )
    
    async def load_playbook(self, request: LoadPlaybookRequest) -> LoadPlaybookResponse:
        """Load a playbook file
        
        Args:
            request: Request with playbook file path
            
        Returns:
            Loaded playbook data
        """
        try:
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
            
            return LoadPlaybookResponse(
                success=True,
                playbook=playbook,
                message=f"Playbook loaded successfully from {request.path}"
            )
        
        except Exception as e:
            return LoadPlaybookResponse(
                success=False,
                message=f"Failed to load playbook: {str(e)}"
            )
