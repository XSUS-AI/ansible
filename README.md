# Ansible MCP Agent

## Overview
Ansible MCP Agent is a powerful assistant that helps manage servers and infrastructure using Ansible. It provides a natural language interface to common Ansible operations through the Model Context Protocol (MCP).

## Features
- Run Ansible playbooks on remote servers
- Execute ad-hoc commands for quick tasks
- Create and manage inventory files
- Create and manage playbook files
- Use system SSH keys for secure authentication
- DevOps and SysOps automation capabilities

## Requirements
- Python 3.9+
- Ansible (with ansible-runner)
- OpenAI API key or OpenRouter API key
- SSH keys configured on the system (for remote connections)

## Repository

The project is available on GitHub:

```bash
# Clone the repository
git clone git@github.com:XSUS-AI/ansible.git
cd ansible
```

You can also use HTTPS if you don't have SSH keys configured for GitHub:

```bash
git clone https://github.com/XSUS-AI/ansible.git
cd ansible
```

## Installation

### Automated Setup

Use the provided setup script to automatically install dependencies:

```bash
chmod +x setup.sh
./setup.sh
```

This script will install all required dependencies and verify that both Ansible and ansible-runner are properly installed.

### Manual Installation

If you prefer to install dependencies manually:

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. If ansible-runner is not properly installed after this, install it directly:
   ```bash
   pip install ansible-runner
   ```

3. Verify Ansible is installed and available in your PATH:
   ```bash
   ansible --version
   ```

### Configuration

Create a `.env` file with your API keys:
```
OPENROUTER_API_KEY=your_openrouter_key
```

## Usage

### Start the Agent
```bash
python agent.py
```

You can specify a different model:
```bash
python agent.py --model anthropic/claude-3-opus
```

### Troubleshooting

If you encounter errors when starting the agent, check the debug logs at `logs/debug.log` for detailed error messages.

Common issues:
- Missing dependencies: Run the `setup.sh` script to install them
- API key not found: Ensure your `.env` file contains the necessary API keys
- SSH keys not configured: The agent uses system SSH keys for authentication

### Example Operations

- List SSH keys on your system
- Create inventory files with servers
- Create playbooks for common tasks
- Run playbooks against your infrastructure
- Execute quick ad-hoc commands
- View and edit existing playbooks and inventories

## Directory Structure

```
├── agents/                # Agent system prompts
│   └── AnsibleAgent.md    # AnsibleAgent system prompt
├── src/                   # Source code
│   └── mcp/               # MCP server code
│       └── mcp_server.py  # Main MCP server implementation
├── .well-known/           # Agent card metadata
│   └── agent.json         # A2A Agent card
├── agent.py               # Agent runner script
├── logs/                  # Log files
│   └── debug.log          # Debug logs
├── prompts.json           # Sample prompts for testing
├── requirements.txt       # Python dependencies
├── setup.sh               # Setup script for dependencies
└── README.md              # This file
```

## How It Works

1. The agent starts an MCP server that connects to Ansible
2. Your requests are processed by an LLM (Claude 3.7 Sonnet by default)
3. The LLM uses the MCP server tools to perform Ansible operations
4. Results are returned in a conversational format

## Security Notes

- The agent only uses system SSH keys and cannot modify them
- Access is restricted to hosts defined in inventory files
- No credentials are stored in the agent itself

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request