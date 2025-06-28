#!/usr/bin/env python3

"""
Helper script to start the agent with mock modules instead of real ones.
This allows testing without having all dependencies installed.
"""

import sys
import os

# Add the mock_modules directory to the Python path
MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_modules")
sys.path.insert(0, MOCK_DIR)

# Now run the agent
print("Starting agent with mock modules...")
print(f"Using mock directory: {MOCK_DIR}")

# Execute the agent module
from agent import main
import asyncio
asyncio.run(main())
