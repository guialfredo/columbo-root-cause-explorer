"""Interactive Terminal UI for Columbo debug sessions using Rich."""

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.text import Text
from rich.console import Console, Group
from typing import Optional, List, Dict, Any
from datetime import datetime
from columbo.schemas import DebugSession, ProbeCall, Finding, ConfidenceLevel
import sys
import io
import re


class SuppressOutput:
    """Context manager to suppress print statements during UI mode."""
    
    def __init__(self, suppress: bool = True):
        self.suppress = suppress
        self.original_stdout = None
        self.original_stderr = None
        
    def __enter__(self):
        if self.suppress:
            self.original_stdout = sys.stdout
            self.original_stderr = sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.suppress:
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr


class ColumboUI:
    """Interactive Terminal UI for watching Columbo investigate."""
    
    def __init__(self, max_steps: int = 10, verbose: bool = False):
        self.console = Console()
        self.max_steps = max_steps
        self.verbose = verbose  # Control whether to show verbose logs
        self.current_step = 0
        self.current_activity = "Initializing..."
        self.hypotheses: List[Dict[str, Any]] = []  # Store all hypotheses
        self.latest_finding = None
        self.probe_history: List[Dict[str, Any]] = []
        self.confidence = "unknown"
        self.current_probe_plan = None  # Store current probe plan details
        self.stop_decision = None  # Store stop decision info
        
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
            Layout(name="investigation", ratio=3),
            Layout(name="evidence", ratio=2),
        )
        
        self.live = None
    
    def start(self):
        """Start the live UI display."""
        self.progress_task = self.progress.add_task(
            "Investigation Budget Consumed", total=self.max_steps
        )
        self.live = Live(
            self.render(), 
            console=self.console, 
            refresh_per_second=4,
            screen=True,  # Use alternate screen buffer for isolated UI
            redirect_stderr=False,  # Allow errors to still show
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
        
        # Only show activity if we're not done (don't duplicate stop decision)
        if not self.stop_decision:
            inv_content.append(f"[yellow]⚙ {self.current_activity}[/yellow]")
        
        # Show hypotheses first (more important than probe plan)
        if self.hypotheses:
            inv_content.append("")
            inv_content.append(f"[bold cyan]Active Hypotheses ({len(self.hypotheses)}):[/bold cyan]")
            # Show top 3 most likely hypotheses only
            for i, hyp in enumerate(self.hypotheses[:3], 1):
                conf_style = {
                    "high": "red",
                    "medium": "yellow", 
                    "low": "blue"
                }.get(hyp.get("confidence", "").lower(), "white")
                
                # Clean up description - remove "H1:", "H2:", "H10:" etc prefixes if present
                desc = hyp.get('description', 'Unknown')
                desc = desc.strip()
                desc = re.sub(r'^H\d+:\s*', '', desc)
                
                # Truncate for display - aim for ~110 chars max to show more context
                # First, try to find a natural break point (dash, comma, em-dash)
                truncate_at = 110
                for delimiter in [' — ', ' - ', ', ', '; ']:
                    pos = desc.find(delimiter)
                    if 30 < pos < truncate_at:
                        desc = desc[:pos]
                        break
                else:
                    # No good delimiter, just hard truncate at word boundary
                    if len(desc) > truncate_at:
                        desc = desc[:truncate_at].rsplit(' ', 1)[0] + "..."
                
                conf_badge = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🔵"
                }.get(hyp.get("confidence", "").lower(), "⚪")
                
                # Single line display to avoid awkward wrapping
                hyp_text = f"  [{conf_style}]{conf_badge} {desc}[/{conf_style}]"
                inv_content.append(hyp_text)
            
            if len(self.hypotheses) > 3:
                inv_content.append(f"  [dim]...and {len(self.hypotheses) - 3} more[/dim]")
        
        # Show current probe plan after hypotheses (but not if we've decided to stop)
        if self.current_probe_plan and not self.stop_decision:
            inv_content.append("")
            inv_content.append(f"[bold magenta]📋 Next Probe:[/bold magenta]")
            
            # Show probe name and args on same line
            probe_name = self.current_probe_plan['name']
            args_str = str(self.current_probe_plan.get('args', '{}'))
            # Compact args display - remove extra whitespace
            args_str = args_str.replace('\n', ' ').replace('  ', ' ')
            if len(args_str) > 50:
                args_str = args_str[:47] + "..."
            inv_content.append(f"  [cyan]{probe_name}[/cyan] [dim]{args_str}[/dim]")
            
            # Show expected signal as rationale
            if self.current_probe_plan.get('expected'):
                exp = self.current_probe_plan['expected']
                # Allow more space - keep first 2 sentences or up to 180 chars
                sentences = exp.split('. ')
                if len(sentences) >= 2:
                    # Take first 2 sentences
                    exp = sentences[0] + '. ' + sentences[1]
                    if not exp.endswith('.'):
                        exp += '.'
                    if len(exp) > 180:
                        exp = exp[:177] + "..."
                elif len(exp) > 180:
                    exp = exp[:177] + "..."
                inv_content.append(f"  [dim]Why: {exp}[/dim]")
        
        # Show stop decision if available (at the end for better flow)
        if self.stop_decision:
            inv_content.append("")
            inv_content.append("[bold]Decision:[/bold]")
            reasoning = self.stop_decision['reasoning']
            
            # Allow up to 200 chars for stop decision (it's important context)
            # Try to break at sentence boundary if needed
            if len(reasoning) > 200:
                # Look for last complete sentence within 200 chars
                truncate_pos = 200
                last_period = reasoning.rfind('. ', 0, truncate_pos)
                if last_period > 100:  # Use sentence break if it's not too early
                    reasoning = reasoning[:last_period + 1]
                else:
                    # No good sentence break, just truncate with ellipsis
                    reasoning = reasoning[:197] + "..."
            
            if self.stop_decision["should_stop"]:
                inv_content.append(f"  [bold red]🛑 Stop:[/bold red] {reasoning}")
            else:
                inv_content.append(f"  [bold green]▶ Continue:[/bold green] {reasoning}")
        
        self.layout["investigation"].update(
            Panel(
                "\n".join(inv_content),
                title="🔍 Active Investigation",
                border_style="cyan"
            )
        )
        
        # Evidence panel
        if self.latest_finding:
            summary = self.latest_finding['summary']
            severity = self.latest_finding.get('severity', 'info')
            
            # Severity styling
            severity_emoji = {
                'critical': '🔴',
                'warning': '🟡',
                'info': 'ℹ️'
            }.get(severity, 'ℹ️')
            
            severity_style = {
                'critical': 'bold red',
                'warning': 'bold yellow',
                'info': 'bold green'
            }.get(severity, 'bold green')
            
            # With concise summaries (~120 chars), less truncation needed
            # Only truncate if unusually long (> 300 chars)
            if len(summary) > 300:
                truncate_pos = 280
                for delimiter in ['. ', '\n', '; ', ', ']:
                    pos = summary.rfind(delimiter, 200, truncate_pos)
                    if pos > 0:
                        summary = summary[:pos + len(delimiter)] + "..."
                        break
                else:
                    summary = summary[:280] + "..."
            
            evidence_parts = [
                Text(f"{severity_emoji} Latest Finding:", style=severity_style),
                Text(""),
                Text(summary)
            ]
            
            self.layout["evidence"].update(
                Panel(
                    Group(*evidence_parts),
                    title="📊 Evidence",
                    border_style="green"
                )
            )
        else:
            self.layout["evidence"].update(
                Panel(
                    "[dim]No evidence yet...[/dim]",
                    title="📊 Evidence",
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
        # Clear only probe plan from previous step
        # Keep stop decision visible as context for why we're continuing
        self.current_probe_plan = None
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
        # Clear previous stop decision now that we have new hypotheses (new round of thinking)
        self.stop_decision = None
        if self.live:
            self.live.update(self.render())
    
    def update_probe_plan(self, probe_name: str, probe_args: str, expected_signal: str):
        """Update the current probe plan being executed."""
        self.current_probe_plan = {
            "name": probe_name,
            "args": probe_args,
            "expected": expected_signal
        }
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
    
    def update_stop_decision(self, should_stop: bool, reasoning: str, confidence: str):
        """Update stop decision information."""
        self.stop_decision = {
            "should_stop": should_stop,
            "reasoning": reasoning,
            "confidence": confidence
        }
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
