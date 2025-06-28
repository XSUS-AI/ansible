"""A mock implementation of ansible_runner for development and testing"""
import os
import sys
import json
import uuid
from typing import Dict, List, Any, Tuple, Optional

# Mock events for playbook runs
class MockRunEvents:
    def __init__(self, successful=True):
        self.events = []
        self._generate_events(successful)
    
    def _generate_events(self, successful=True):
        # Generate a series of mock events for a playbook run
        host = "localhost"
        
        # Task 1: Gathering facts
        self.events.append({
            "event": "runner_on_ok",
            "event_data": {
                "task": "Gathering Facts",
                "host": host,
                "changed": False,
                "res": {"ansible_facts": {"hostname": "test-server"}}
            }
        })
        
        # Task 2: Test connection
        self.events.append({
            "event": "runner_on_ok",
            "event_data": {
                "task": "Test connection",
                "host": host,
                "changed": False,
                "res": {"msg": "Connection successful"}
            }
        })
        
        # Task 3: Create a test file
        self.events.append({
            "event": "runner_on_changed",
            "event_data": {
                "task": "Create a test file",
                "host": host,
                "changed": True,
                "res": {"dest": "/tmp/test.txt", "state": "file"}
            }
        })
        
        # Task 4: Check service status
        if successful:
            self.events.append({
                "event": "runner_on_ok",
                "event_data": {
                    "task": "Check service status",
                    "host": host,
                    "changed": False,
                    "res": {"name": "nginx", "state": "started"}
                }
            })
        else:
            self.events.append({
                "event": "runner_on_failed",
                "event_data": {
                    "task": "Check service status",
                    "host": host,
                    "changed": False,
                    "res": {"msg": "Service nginx is not running", "changed": False}
                }
            })
    
    def __iter__(self):
        return iter(self.events)


# Mock result for a playbook run
class MockRunner:
    def __init__(self, successful=True):
        self.successful = successful
        self.rc = 0 if successful else 1
        self.events = MockRunEvents(successful)
        self.stats = {
            "localhost": {
                "ok": 3 if successful else 2,
                "failures": 0 if successful else 1,
                "skipped": 0,
                "unreachable": 0
            }
        }
        
        # Generate some output
        self.stdout = f"PLAY [Execute Test Tasks] *********************************************\n\n"
        self.stdout += f"TASK [Gathering Facts] **************************************************\n"
        self.stdout += f"ok: [localhost]\n\n"
        self.stdout += f"TASK [Test connection] *************************************************\n"
        self.stdout += f"ok: [localhost]\n\n"
        self.stdout += f"TASK [Create a test file] **********************************************\n"
        self.stdout += f"changed: [localhost]\n\n"
        self.stdout += f"TASK [Check service status] ********************************************\n"
        
        if successful:
            self.stdout += f"ok: [localhost]\n\n"
            self.stdout += f"PLAY RECAP **************************************************************\n"
            self.stdout += f"localhost                  : ok=4    changed=1    unreachable=0    failed=0    skipped=0\n"
            self.stderr = ""
        else:
            self.stdout += f"failed: [localhost]\n\n"
            self.stdout += f"PLAY RECAP **************************************************************\n"
            self.stdout += f"localhost                  : ok=3    changed=1    unreachable=0    failed=1    skipped=0\n"
            self.stderr = "ERROR: Service nginx is not running\n"


# Main functions that match the ansible_runner API
def run(private_data_dir=None, playbook=None, inventory=None, 
        host_pattern=None, module=None, module_args=None, verbosity=0, 
        extravars=None, **kwargs):
    """Mock implementation of ansible_runner.run"""
    # Determine if this is a playbook run or ad-hoc command
    successful = True  # Default to success
    
    # Create private data dir if it doesn't exist
    if private_data_dir and not os.path.exists(private_data_dir):
        os.makedirs(private_data_dir, exist_ok=True)
    
    # Write some mock output files
    if private_data_dir:
        # Write stdout
        stdout_content = "Mock Ansible Runner Output\n"
        if playbook:
            stdout_content += f"Running playbook: {playbook}\n"
        elif module:
            stdout_content += f"Running module: {module} with args: {module_args}\n"
        
        with open(os.path.join(private_data_dir, "stdout"), "w") as f:
            f.write(stdout_content)
        
        # Write empty stderr
        with open(os.path.join(private_data_dir, "stderr"), "w") as f:
            f.write("")
    
    # Create and return a mock result
    return MockRunner(successful=successful)


def run_command(executable_cmd=None, cmdline_args=None, input_fd=None, 
                output_fd=None, error_fd=None, **kwargs) -> Tuple[int, str, str]:
    """Mock implementation of ansible_runner.run_command"""
    if executable_cmd == 'ansible-inventory' and '--list' in cmdline_args:
        # Return a mock inventory listing
        inventory = {
            "all": {
                "children": ["ungrouped", "webservers", "dbservers"]
            },
            "webservers": {
                "hosts": ["web1.example.com", "web2.example.com"],
                "vars": {"http_port": 80}
            },
            "dbservers": {
                "hosts": ["db1.example.com"],
                "vars": {"db_port": 5432}
            },
            "_meta": {
                "hostvars": {
                    "web1.example.com": {"ansible_host": "192.168.1.101"},
                    "web2.example.com": {"ansible_host": "192.168.1.102"},
                    "db1.example.com": {"ansible_host": "192.168.1.103"}
                }
            }
        }
        return 0, json.dumps(inventory), ""
    
    elif executable_cmd == 'ansible-playbook':
        # Return successful playbook execution
        return 0, "Playbook executed successfully", ""
    
    # Default fallback
    return 0, "Command executed", ""


# Print a message indicating this is a mock module
sys.stderr.write("NOTE: Using mock ansible_runner module for development/testing\n")

# If this file is executed directly, print help
if __name__ == "__main__":
    print("This is a mock implementation of the ansible_runner module for development and testing.")
    print("It's not meant to be run directly, but to be imported.")
