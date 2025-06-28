#!/bin/bash

# Install all required dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Verify ansible-runner is installed
if python -c "import ansible_runner" 2>/dev/null; then
    echo "ansible_runner is successfully installed."
else
    echo "WARNING: ansible_runner installation failed. Trying to install it directly..."
    pip install ansible-runner
    
    if python -c "import ansible_runner" 2>/dev/null; then
        echo "ansible_runner is now successfully installed."
    else
        echo "ERROR: Failed to install ansible_runner. Please try to install it manually:"
        echo "pip install ansible-runner"
        exit 1
    fi
fi

# Verify Ansible is installed
if command -v ansible >/dev/null 2>&1; then
    echo "Ansible is successfully installed."
    ansible --version | head -n 1
else
    echo "WARNING: Ansible is not in PATH. Checking if it's installed as a Python module..."
    if python -c "import ansible" 2>/dev/null; then
        echo "Ansible is installed as a Python module."
    else
        echo "ERROR: Ansible is not installed. Please install it manually:"
        echo "pip install ansible"
        exit 1
    fi
fi

echo ""
echo "Setup completed. You should now be able to run the agent with:"
echo "python agent.py"
