"""Interactive Terminal UI for Columbo debug sessions using Rich."""

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.text import Text
from rich.console import Console, Group
from rich.syntax import Syntax
from typing import Optional, List, Dict, Any
from datetime import datetime
from columbo.schemas import DebugSession, ProbeCall, Finding, ConfidenceLevel
import json


class ColumboUI:
    """Interactive Terminal UI for watching Columbo investigate."""
    
    def __init__(self, max_steps: int = 10):
        self.console = Console()
        self.max_steps = max_steps
        self.current_step = 0
        self.current_activity = "Initializing..."
        self.hypotheses: List[Dict[str, Any]] = []  # Store all hypotheses
        self.latest_finding = None
        self.probe_history: List[Dict[str, Any]] = []
        self.confidence = "unknown"
        
        # Progress tracking
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        self.progress_task = None
        
        # Layout
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )
        self.layout["left"].split_column(
            Layout(name="investigation", ratio=1),
            Layout(name="evidence", ratio=1),
        )
        
        self.live = None
    
    def start(self):
        """Start the live UI display."""
        self.progress_task = self.progress.add_task(
            "Investigation Progress", total=self.max_steps
        )
        self.live = Live(
            self.render(), 
            console=self.console, 
            refresh_per_second=4,
            screen=False,
        )
        self.live.start()
    
    def stop(self):
        """Stop the live UI display."""
        if self.live:
            self.live.stop()
    
    def render(self) -> Layout:
        """Render the current UI state."""
        # Header
        self.layout["header"].update(
            Panel(
                Text("🕵️  Columbo Root Cause Explorer", style="bold cyan", justify="center"),
                style="bold white on blue"
            )
        )
        
        # Investigation panel
        inv_content = []
        inv_content.append(f"[bold]Step {self.current_step}/{self.max_steps}[/bold]")
        inv_content.append(f"[yellow]⚙ {self.current_activity}[/yellow]")
        
        if self.hypotheses:
            inv_content.append("")
            inv_content.append(f"[bold cyan]Active Hypotheses ({len(self.hypotheses)}):[/bold cyan]")
            # Show all hypotheses with their confidence
            for i, hyp in enumerate(self.hypotheses[:5], 1):  # Show top 5
                conf_style = {
                    "high": "red",
                    "medium": "yellow", 
                    "low": "blue"
                }.get(hyp.get("confidence", "").lower(), "white")
                
                # Clean up description - remove "H1:", "H2:" prefixes if present
                desc = hyp.get('description', 'Unknown')
                desc = desc.strip()
                # Remove leading H1:, H2:, etc if present
                if desc and len(desc) > 3 and desc[0] == 'H' and desc[2] == ':':
                    desc = desc[3:].strip()
                
                # Truncate to 70 chars for cleaner display
                if len(desc) > 70:
                    desc = desc[:67] + "..."
                
                conf_badge = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🔵"
                }.get(hyp.get("confidence", "").lower(), "⚪")
                
                hyp_text = f"  [{conf_style}]{conf_badge} {desc}[/{conf_style}]"
                inv_content.append(hyp_text)
            
            if len(self.hypotheses) > 5:
                inv_content.append(f"  [dim]...and {len(self.hypotheses) - 5} more[/dim]")
        
        self.layout["investigation"].update(
            Panel(
                "\n".join(inv_content),
                title="🔍 Active Investigation",
                border_style="cyan"
            )
        )
        
        # Evidence panel
        if self.latest_finding:
            evidence_text = []
            evidence_text.append(f"[bold green]Latest Finding:[/bold green]")
            evidence_text.append(f"  {self.latest_finding['summary']}")
            evidence_text.append("")
            evidence_text.append(f"[dim]Significance:[/dim] {self.latest_finding.get('significance', 'N/A')}")
            
            self.layout["evidence"].update(
                Panel(
                    "\n".join(evidence_text),
                    title="📊 Evidence Collected",
                    border_style="green"
                )
            )
        else:
            self.layout["evidence"].update(
                Panel(
                    "[dim]No evidence collected yet...[/dim]",
                    title="📊 Evidence Collected",
                    border_style="green"
                )
            )
        
        # Probe history table
        history_table = Table(show_header=True, header_style="bold magenta", box=None)
        history_table.add_column("Step", style="dim", width=5)
        history_table.add_column("Probe", style="cyan")
        history_table.add_column("Status", width=8)
        
        for probe in self.probe_history[-10:]:  # Show last 10
            status_emoji = "✓" if probe.get("success", True) else "✗"
            status_style = "green" if probe.get("success", True) else "red"
            history_table.add_row(
                str(probe["step"]),
                probe["name"][:30],
                f"[{status_style}]{status_emoji}[/{status_style}]"
            )
        
        self.layout["right"].update(
            Panel(
                history_table,
                title="📝 Probe History",
                border_style="magenta"
            )
        )
        
        # Footer with progress
        footer_group = Group(
            self.progress,
            Text(f"Confidence: {self.confidence}", style="bold yellow")
        )
        self.layout["footer"].update(Panel(footer_group, style="bold white on dark_blue"))
        
        return self.layout
    
    def update_step(self, step: int):
        """Update current step number."""
        self.current_step = step
        if self.progress_task is not None:
            self.progress.update(self.progress_task, completed=step)
        if self.live:
            self.live.update(self.render())
    
    def update_activity(self, activity: str):
        """Update current activity description."""
        self.current_activity = activity
        if self.live:
            self.live.update(self.render())
    
    def update_hypotheses(self, hypotheses: List[Dict[str, Any]]):
        """Update all active hypotheses."""
        self.hypotheses = hypotheses
        if self.live:
            self.live.update(self.render())
    
    def add_probe_execution(self, step: int, probe_name: str, success: bool = True):
        """Add a probe to the execution history."""
        self.probe_history.append({
            "step": step,
            "name": probe_name,
            "success": success,
        })
        if self.live:
            self.live.update(self.render())
    
    def update_finding(self, finding: Dict[str, Any]):
        """Update the latest finding."""
        self.latest_finding = finding
        if self.live:
            self.live.update(self.render())
    
    def update_confidence(self, confidence: str):
        """Update confidence level."""
        self.confidence = confidence
        if self.live:
            self.live.update(self.render())
    
    def show_final_diagnosis(self, diagnosis: Dict[str, Any]):
        """Display final diagnosis in a formatted panel."""
        self.stop()
        
        # Create diagnosis panel
        diag_content = []
        diag_content.append(f"[bold red]Root Cause:[/bold red]")
        diag_content.append(f"  {diagnosis.get('root_cause', 'Unknown')}")
        diag_content.append("")
        diag_content.append(f"[bold green]Recommended Fixes:[/bold green]")
        diag_content.append(f"  {diagnosis.get('recommended_fixes', 'None provided')}")
        diag_content.append("")
        diag_content.append(f"[bold yellow]Confidence:[/bold yellow] {diagnosis.get('confidence', 'unknown')}")
        
        if diagnosis.get('additional_notes'):
            diag_content.append("")
            diag_content.append(f"[bold cyan]Additional Notes:[/bold cyan]")
            diag_content.append(f"  {diagnosis['additional_notes']}")
        
        self.console.print()
        self.console.print(
            Panel(
                "\n".join(diag_content),
                title="🎯 Final Diagnosis",
                border_style="bold green",
                expand=False,
            )
        )
        self.console.print()


class SimpleProgressUI:
    """Simpler progress-only UI for minimal output."""
    
    def __init__(self, max_steps: int = 10):
        self.console = Console()
        self.max_steps = max_steps
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        )
        self.task = None
    
    def start(self):
        """Start progress tracking."""
        self.progress.start()
        self.task = self.progress.add_task("Investigating...", total=self.max_steps)
    
    def stop(self):
        """Stop progress tracking."""
        self.progress.stop()
    
    def update_step(self, step: int):
        """Update progress."""
        if self.task is not None:
            self.progress.update(self.task, completed=step)
    
    def update_activity(self, activity: str):
        """Update activity description."""
        if self.task is not None:
            self.progress.update(self.task, description=f"[bold blue]{activity}")
    
    def show_final_diagnosis(self, diagnosis: Dict[str, Any]):
        """Show final diagnosis."""
        self.console.print()
        self.console.print(f"[bold green]✓[/bold green] Investigation complete!")
        self.console.print(f"[bold]Root Cause:[/bold] {diagnosis.get('root_cause', 'Unknown')}")
