"""CLI entry point for Columbo debugging agent.

This allows users to run the debugging assistant on their own infrastructure
with custom initial evidence.
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv
import os
import dspy
import tempfile
import subprocess

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown

from columbo.debug_loop import debug_loop
from columbo.ui import ColumboUI
from columbo.session_utils import (
    save_session_to_file,
    generate_session_report,
    analyze_probe_performance,
)

console = Console()


def setup_dspy_llm(api_key: str, model: str):
    """Configure DSPy with the specified LLM."""
    lm = dspy.LM(model, api_key=api_key, cache=False)
    dspy.configure(lm=lm)


def get_initial_evidence(args: argparse.Namespace) -> str:
    """Extract initial evidence from CLI arguments."""
    if args.from_file:
        evidence_file = Path(args.from_file)
        if not evidence_file.exists():
            console.print(f"[red]ERROR: Evidence file not found: {evidence_file}[/red]")
            sys.exit(1)
        return evidence_file.read_text().strip()
    
    if args.evidence:
        return args.evidence
    
    # Interactive prompt with Rich
    return prompt_for_evidence_interactive()


def prompt_for_evidence_interactive() -> str:
    """Prompt user for initial evidence using Rich interactive UI."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]🕵️  Columbo Evidence Collection[/bold cyan]\n\n"
        "Let's gather some initial information about the problem you're investigating.\n"
        "The more context you provide, the better Columbo can help!",
        border_style="cyan"
    ))
    console.print()
    
    # Show input options
    console.print("[bold]How would you like to provide the evidence?[/bold]\n")
    console.print("  1. [cyan]Type directly[/cyan] - Quick structured prompts")
    console.print("  2. [cyan]Use editor[/cyan] - Write freely in your text editor")
    console.print("  3. [cyan]Free-form[/cyan] - Paste or type multiple lines\n")
    
    choice = Prompt.ask(
        "Choose an option",
        choices=["1", "2", "3"],
        default="1"
    )
    
    if choice == "1":
        return collect_evidence_inline()
    elif choice == "2":
        return collect_evidence_in_editor()
    else:
        return collect_evidence_freeform()


def collect_evidence_in_editor() -> str:
    """Open user's preferred editor for evidence collection."""
    # Create a temporary file with helpful template
    template = """# Describe your problem below
# Lines starting with # will be ignored
#
# Helpful information to include:
# - What error or unexpected behavior are you seeing?
# - Which service/container is affected?
# - What were you trying to do when this happened?
# - Any relevant context (recent changes, environment, etc.)
#
# Example:
# My nginx container won't start after updating docker-compose.yml
# 
# Error message: "bind: address already in use"
# 
# Context:
# - Running on macOS with Docker Desktop
# - Changed the port from 8080 to 80 in docker-compose.yml
# - Other containers seem to be running fine

"""
    
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tf:
        tf.write(template)
        temp_path = tf.name
    
    try:
        # Get editor from environment or use default
        editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'nano'))
        
        console.print(f"[dim]Opening {editor}... (save and close when done)[/dim]")
        
        # Open editor
        subprocess.run([editor, temp_path], check=True)
        
        # Read the content
        with open(temp_path, 'r') as f:
            content = f.read()
        
        # Remove comment lines and strip
        lines = [line for line in content.split('\n') if not line.strip().startswith('#')]
        evidence = '\n'.join(lines).strip()
        
        if not evidence:
            console.print("[yellow]⚠️  No evidence provided in editor[/yellow]")
            retry = Confirm.ask("Would you like to try again?", default=True)
            if retry:
                return collect_evidence_in_editor()
            else:
                sys.exit(0)
        
        return evidence
        
    finally:
        # Cleanup temp file
        try:
            os.unlink(temp_path)
        except:
            pass


def collect_evidence_inline() -> str:
    """Collect evidence via inline prompts."""
    console.print("[bold]Please provide the following information:[/bold]\n")
    
    # Structured questions
    problem = Prompt.ask("1️⃣  [cyan]What problem are you investigating?[/cyan]")
    
    console.print("\n2️⃣  [cyan]Any error messages or unexpected behavior?[/cyan]")
    console.print("   [dim](Press Enter for none)[/dim]")
    errors = Prompt.ask("   ", default="No specific error messages")
    
    console.print("\n3️⃣  [cyan]Which service/container is affected?[/cyan]")
    console.print("   [dim](Press Enter if unsure)[/dim]")
    service = Prompt.ask("   ", default="Not sure")
    
    console.print("\n4️⃣  [cyan]Any additional context?[/cyan]")
    console.print("   [dim](Recent changes, environment info, etc. Press Enter to skip)[/dim]")
    context = Prompt.ask("   ", default="")
    
    # Build evidence string
    evidence_parts = [f"Problem: {problem}"]
    
    if errors and errors != "No specific error messages":
        evidence_parts.append(f"\nError details: {errors}")
    
    if service and service != "Not sure":
        evidence_parts.append(f"\nAffected service: {service}")
    
    if context:
        evidence_parts.append(f"\nContext: {context}")
    
    evidence = "\n".join(evidence_parts)
    
    # Show preview
    console.print("\n" + "─" * 70)
    console.print(Panel(
        evidence,
        title="[bold]Evidence Summary[/bold]",
        border_style="green"
    ))
    console.print("─" * 70)
    
    # Confirm
    if not Confirm.ask("\nDoes this look correct?", default=True):
        console.print("\n[yellow]Let's try again...[/yellow]\n")
        return collect_evidence_inline()
    
    return evidence


def collect_evidence_freeform() -> str:
    """Collect evidence in free-form multi-line format."""
    console.print()
    console.print(Panel.fit(
        "[bold]Free-form Evidence Entry[/bold]\n\n"
        "Type or paste your problem description below.\n"
        "When finished, type [cyan]END[/cyan] on a new line and press Enter.\n\n"
        "[dim]Tip: You can paste multi-line text directly[/dim]",
        border_style="cyan"
    ))
    console.print()
    
    lines = []
    console.print("[dim]> Start typing (type END without quotes on a new line when done):[/dim]\n")
    
    try:
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        # Handle Ctrl+D or Ctrl+C gracefully
        pass
    
    evidence = "\n".join(lines).strip()
    
    if not evidence:
        console.print("\n[yellow]⚠️  No evidence provided[/yellow]")
        retry = Confirm.ask("Would you like to try again?", default=True)
        if retry:
            return collect_evidence_freeform()
        else:
            sys.exit(0)
    
    # Show preview
    console.print("\n" + "─" * 70)
    console.print(Panel(
        evidence,
        title="[bold]Evidence Summary[/bold]",
        border_style="green"
    ))
    console.print("─" * 70)
    
    # Confirm
    if not Confirm.ask("\nDoes this look correct?", default=True):
        console.print("\n[yellow]Let's try again...[/yellow]\n")
        return collect_evidence_freeform()
    
    return evidence


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="columbo",
        description="Columbo: Hypothesis-driven debugging agent for containerized systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start debugging with inline evidence
  columbo debug "My app container fails to connect to postgres"
  
  # Load evidence from a file
  columbo debug --from-file problem.txt
  
  # Use interactive UI mode
  columbo debug --interactive "Service keeps crashing"
  
  # Specify workspace and custom settings
  columbo debug "Port conflict error" --workspace /path/to/project --max-steps 10
  
  # Use a different LLM model
  columbo debug "Network timeout" --model openai/gpt-5-mini
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Debug command
    debug_parser = subparsers.add_parser(
        "debug",
        help="Start a debugging session",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    debug_parser.add_argument(
        "evidence",
        nargs="?",
        help="Initial evidence or problem description (optional if using --from-file)"
    )
    
    debug_parser.add_argument(
        "--from-file",
        type=str,
        metavar="PATH",
        help="Read initial evidence from a text file"
    )
    
    debug_parser.add_argument(
        "--workspace",
        type=str,
        default=".",
        metavar="PATH",
        help="Path to workspace/project root (default: current directory)"
    )
    
    debug_parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        metavar="N",
        help="Maximum number of debugging steps (default: 8)"
    )
    
    debug_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive Rich UI for live investigation updates"
    )
    
    debug_parser.add_argument(
        "--model",
        type=str,
        default="openai/gpt-5-mini",
        metavar="MODEL",
        help="LLM model to use (default: openai/gpt-5-mini)"
    )
    
    debug_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Directory to save session results (default: ./columbo_sessions)"
    )
    
    debug_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save session results to disk"
    )
    
    args = parser.parse_args()
    
    # Show help if no command provided
    if not args.command:
        parser.print_help()
        return 0
    
    # Handle debug command
    if args.command == "debug":
        return run_debug(args)
    
    return 0


def run_debug(args: argparse.Namespace) -> int:
    """Execute a debugging session."""
    
    # Load environment variables
    load_dotenv()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        console.print("[red]ERROR: OPENAI_API_KEY not set in environment[/red]")
        console.print("[yellow]Please set it in your .env file or export it as an environment variable[/yellow]")
        return 1
    
    # Configure LLM
    console.print("[dim]Configuring LLM...[/dim]")
    try:
        setup_dspy_llm(api_key=openai_api_key, model=args.model)
    except Exception as e:
        console.print(f"[red]ERROR: Failed to configure LLM: {e}[/red]")
        return 1
    
    # Get initial evidence
    initial_evidence = get_initial_evidence(args)
    
    if not initial_evidence:
        console.print("[red]ERROR: No evidence provided[/red]")
        return 1
    
    # Resolve workspace path
    workspace_root = Path(args.workspace).resolve()
    if not workspace_root.exists():
        console.print(f"[red]ERROR: Workspace not found: {workspace_root}[/red]")
        return 1
    
    # Print session header (only in non-interactive mode)
    if not args.interactive:
        console.print("\n" + "=" * 70)
        console.print("[bold cyan]COLUMBO DEBUGGING SESSION[/bold cyan]")
        console.print("=" * 70)
        console.print(f"\n[dim]Workspace:[/dim] {workspace_root}")
        console.print(f"[dim]Max steps:[/dim] {args.max_steps}")
        console.print(f"[dim]Model:[/dim] {args.model}")
        console.print(f"\n[bold]Initial Evidence:[/bold]")
        console.print("─" * 70)
        console.print(Panel(initial_evidence, border_style="blue"))
        console.print("─" * 70)
    
    # Initialize UI if interactive mode
    ui = None
    if args.interactive:
        console.print("\n[bold cyan]🕵️  Starting interactive UI mode...[/bold cyan]")
        console.print("[dim]⚠️  UI will take over the screen. Press Ctrl+C to stop.[/dim]\n")
        ui = ColumboUI(max_steps=args.max_steps, verbose=False)
        ui.start()
    
    # Run debugging loop
    try:
        result = debug_loop(
            initial_evidence=initial_evidence,
            max_steps=args.max_steps,
            workspace_root=str(workspace_root),
            ui_callback=ui,
            verbose=not args.interactive,
        )
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠️  Session interrupted by user[/yellow]")
        if ui:
            ui.stop()
        return 130
    except Exception as e:
        console.print(f"\n[red]ERROR: Debugging session failed: {e}[/red]")
        if ui:
            ui.stop()
        return 1
    finally:
        if ui:
            ui.stop()
    
    # Extract results
    diagnosis = result["diagnosis"]
    debug_session = result["debug_session"]
    session_model = result["session_model"]
    
    # Print results with Rich formatting
    console.print("\n" + "=" * 70)
    console.print("[bold green]DEBUGGING SESSION COMPLETE[/bold green]")
    console.print("=" * 70)
    
    console.print(f"\n[dim]Total probing steps:[/dim] {debug_session['total_steps']}")
    console.print(f"[dim]Session ID:[/dim] {session_model.session_id}")
    
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]DIAGNOSIS[/bold cyan]")
    console.print("=" * 70)
    
    console.print(Panel(
        f"[bold]Root Cause:[/bold]\n{diagnosis['root_cause']}\n\n"
        f"[bold]Confidence:[/bold] {diagnosis['confidence']}\n\n"
        f"[bold]Recommended Fixes:[/bold]\n{diagnosis['recommended_fixes']}"
        + (f"\n\n[bold]Additional Notes:[/bold]\n{diagnosis['additional_notes']}" if diagnosis['additional_notes'] else ""),
        border_style="green",
        title="[bold]Final Diagnosis[/bold]"
    ))
    
    console.print("\n" + "─" * 70)
    console.print("[bold]EVIDENCE LOG:[/bold]")
    console.print("─" * 70)
    for finding in debug_session["evidence_log"]:
        console.print(f"• {finding}")
    
    console.print("\n" + "─" * 70)
    console.print("[bold]PROBES EXECUTED:[/bold]")
    console.print("─" * 70)
    for probe in debug_session["probes_executed"]:
        console.print(f"\n[cyan]Step {probe['step']}:[/cyan] {probe['probe_name']}")
        console.print(f"  [dim]Args: {probe['probe_args']}[/dim]")
    
    # Performance analysis
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]PERFORMANCE METRICS[/bold cyan]")
    console.print("=" * 70)
    perf = analyze_probe_performance(session_model)
    console.print(f"\n[dim]Total execution time:[/dim] {perf.get('total_time', 0):.2f}s")
    console.print(f"[dim]Average per probe:[/dim] {perf.get('avg_time_per_probe', 0):.2f}s")
    console.print(f"[dim]Success rate:[/dim] {perf.get('success_rate', 0):.1%}")
    
    # Save session results
    if not args.no_save:
        output_dir = args.output_dir or (workspace_root / "columbo_sessions")
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        console.print("\n" + "─" * 70)
        
        # Save JSON session data
        session_file = save_session_to_file(session_model, str(output_dir))
        console.print(f"[green]✓[/green] Session data saved to: [blue]{session_file}[/blue]")
        
        # Generate and save markdown report
        report = generate_session_report(session_model)
        report_file = output_dir / f"report_{session_model.session_id}.md"
        report_file.write_text(report)
        console.print(f"[green]✓[/green] Session report saved to: [blue]{report_file}[/blue]")
    
    console.print("\n" + "=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
