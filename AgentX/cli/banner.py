from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.columns import Columns

console = Console()

def banner():
    AGENTX_ASCII = """
 █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗  ██╗
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝╚██╗██╔╝
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║    ╚███╔╝
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║    ██╔██╗
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██╔╝ ██╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝
"""

    content = Text(justify="center")
    content.append(AGENTX_ASCII, style="bold color(223)")
    content.append("\n\n")
    content.append("The Agent that Works FOR You", style="dim white")
    content.append("\n")
    content.append("Personal AI Agent & Task Orchestrator", style="color(240)")

    panel = Panel(
        Align.center(content),
        border_style="color(238)",
        padding=(1, 4),
        # style="on color(235)",
    )

    console.print()
    console.print(panel)
    console.print()