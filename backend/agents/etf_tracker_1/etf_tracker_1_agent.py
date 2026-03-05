#!/usr/bin/env python3
"""
ETF Tracker — A2A-compliant agent.

I want an ETF creation agent. Given a description of an ETF it should be able to find a group of stocks that match the description. For example: "Create an ETF that is made of healthcare stocks with high dividends and a stable values" 
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.etf_tracker_1.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class EtfTracker1Agent(BaseA2AAgent):
    """I want an ETF creation agent. Given a description of an ETF it should be able to find a group of stocks that match the description. For example: "Create an ETF that is made of healthcare stocks with high dividends and a stable values" """

    agent_id = "etf-tracker-1-1"
    service_name = "ETF Tracker"
    description = """I want an ETF creation agent. Given a description of an ETF it should be able to find a group of stocks that match the description. For example: "Create an ETF that is made of healthcare stocks with high dividends and a stable values" """
    skill_tags = []

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="ETF_TRACKER_1_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ETF Tracker')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on')
    args = parser.parse_args()

    agent = EtfTracker1Agent(port=args.port)
    asyncio.run(agent.run())
