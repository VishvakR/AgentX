"""Agent Sara — CLI entry point.

Usage:
    python -m AgentX.main                         # default session
    python -m AgentX.main --session my:chat        # custom session key
    python -m AgentX.main --model qwen3.5:4b-mlx   # override model
"""

"""
commands:

agentx agent -- Intractive Agent
agentx version -- version
"""
from AgentX.cli.command import run_cli

def main():
    run_cli()

if __name__ == "__main__":
    main()
