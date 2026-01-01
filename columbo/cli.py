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

from columbo.debug_loop import debug_loop
from columbo.ui import ColumboUI
from columbo.session_utils import (
    save_session_to_file,
    generate_session_report,
    analyze_probe_performance,
)


def setup_dspy_llm(api_key: str, model: str):
    """Configure DSPy with the specified LLM."""
    lm = dspy.LM(model, api_key=api_key, cache=False)
    dspy.configure(lm=lm)


def get_initial_evidence(args: argparse.Namespace) -> str:
    """Extract initial evidence from CLI arguments."""
    if args.from_file:
        evidence_file = Path(args.from_file)
        if not evidence_file.exists():
            print(f"ERROR: Evidence file not found: {evidence_file}")
            sys.exit(1)
        return evidence_file.read_text().strip()
    
    if args.evidence:
        return args.evidence
    
    # Interactive prompt if no evidence provided
    print("No initial evidence provided. Please describe the problem:")
    print("(Enter your evidence, then press Ctrl+D on a new line when done)\n")
    try:
        lines = []
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        return "\n".join(lines).strip()


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
        print("ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or export it as an environment variable")
        return 1
    
    # Configure LLM
    print("Configuring LLM...")
    try:
        setup_dspy_llm(api_key=openai_api_key, model=args.model)
    except Exception as e:
        print(f"ERROR: Failed to configure LLM: {e}")
        return 1
    
    # Get initial evidence
    if not args.from_file and not args.evidence:
        print("\nNo evidence provided. Starting interactive mode...\n")
    
    initial_evidence = get_initial_evidence(args)
    
    if not initial_evidence:
        print("ERROR: No evidence provided")
        return 1
    
    # Resolve workspace path
    workspace_root = Path(args.workspace).resolve()
    if not workspace_root.exists():
        print(f"ERROR: Workspace not found: {workspace_root}")
        return 1
    
    # Print session header
    print("\n" + "=" * 70)
    print("COLUMBO DEBUGGING SESSION")
    print("=" * 70)
    print(f"\nWorkspace: {workspace_root}")
    print(f"Max steps: {args.max_steps}")
    print(f"Model: {args.model}")
    print(f"\nInitial Evidence:")
    print("-" * 70)
    print(initial_evidence)
    print("-" * 70)
    
    # Initialize UI if interactive mode
    ui = None
    if args.interactive:
        print("\n🕵️  Starting interactive UI mode...")
        print("⚠️  UI will take over the screen. Press Ctrl+C to stop.\n")
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
        print("\n\n⚠️  Session interrupted by user")
        if ui:
            ui.stop()
        return 130
    except Exception as e:
        print(f"\nERROR: Debugging session failed: {e}")
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
    
    # Print results
    print("\n" + "=" * 70)
    print("DEBUGGING SESSION COMPLETE")
    print("=" * 70)
    
    print(f"\nTotal probing steps: {debug_session['total_steps']}")
    print(f"Session ID: {session_model.session_id}")
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    print(f"\nRoot Cause:\n{diagnosis['root_cause']}")
    print(f"\nConfidence: {diagnosis['confidence']}")
    print(f"\nRecommended Fixes:\n{diagnosis['recommended_fixes']}")
    
    if diagnosis['additional_notes']:
        print(f"\nAdditional Notes:\n{diagnosis['additional_notes']}")
    
    print("\n" + "-" * 70)
    print("EVIDENCE LOG:")
    print("-" * 70)
    for finding in debug_session["evidence_log"]:
        print(finding)
    
    print("\n" + "-" * 70)
    print("PROBES EXECUTED:")
    print("-" * 70)
    for probe in debug_session["probes_executed"]:
        print(f"\nStep {probe['step']}: {probe['probe_name']}")
        print(f"  Args: {probe['probe_args']}")
    
    # Performance analysis
    print("\n" + "=" * 70)
    print("PERFORMANCE METRICS")
    print("=" * 70)
    perf = analyze_probe_performance(session_model)
    print(f"\nTotal execution time: {perf.get('total_time', 0):.2f}s")
    print(f"Average per probe: {perf.get('avg_time_per_probe', 0):.2f}s")
    print(f"Success rate: {perf.get('success_rate', 0):.1%}")
    
    # Save session results
    if not args.no_save:
        output_dir = args.output_dir or (workspace_root / "columbo_sessions")
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        print("\n" + "-" * 70)
        
        # Save JSON session data
        session_file = save_session_to_file(session_model, str(output_dir))
        print(f"Session data saved to: {session_file}")
        
        # Generate and save markdown report
        report = generate_session_report(session_model)
        report_file = output_dir / f"report_{session_model.session_id}.md"
        report_file.write_text(report)
        print(f"Session report saved to: {report_file}")
    
    print("\n" + "=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
