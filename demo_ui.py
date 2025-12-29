"""Demo script showing both regular and interactive UI modes."""

import dspy
from columbo.debug_loop import debug_loop
from columbo.ui import ColumboUI, SimpleProgressUI
from pathlib import Path
from dotenv import load_dotenv
import os
import sys


def setup_llm():
    """Configure the LLM."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    lm = dspy.LM("openai/gpt-4o-mini", api_key=api_key, cache=False)
    dspy.configure(lm=lm)


def run_with_full_ui(problem: str, workspace: str, max_steps: int = 6):
    """Run with the full interactive UI."""
    print("🕵️  Starting Columbo with interactive UI...\n")
    
    ui = ColumboUI(max_steps=max_steps)
    ui.start()
    
    try:
        result = debug_loop(
            initial_evidence=problem,
            max_steps=max_steps,
            workspace_root=workspace,
            ui_callback=ui
        )
        
        ui.show_final_diagnosis(result["diagnosis"])
        return result
        
    except KeyboardInterrupt:
        ui.stop()
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    finally:
        ui.stop()


def run_with_simple_progress(problem: str, workspace: str, max_steps: int = 6):
    """Run with simple progress bar only."""
    print("🕵️  Starting Columbo with progress tracking...\n")
    
    ui = SimpleProgressUI(max_steps=max_steps)
    ui.start()
    
    try:
        result = debug_loop(
            initial_evidence=problem,
            max_steps=max_steps,
            workspace_root=workspace,
            ui_callback=ui
        )
        
        ui.show_final_diagnosis(result["diagnosis"])
        return result
        
    finally:
        ui.stop()


def run_silent(problem: str, workspace: str, max_steps: int = 6):
    """Run without any UI (verbose logs only)."""
    print("🕵️  Starting Columbo (verbose mode)...\n")
    
    result = debug_loop(
        initial_evidence=problem,
        max_steps=max_steps,
        workspace_root=workspace,
        ui_callback=None  # No UI callbacks
    )
    
    return result


if __name__ == "__main__":
    setup_llm()
    
    # Example problem
    problem = """
My web application is not responding on localhost:8080.

Context:
- App runs in a Docker container
- Should expose port 8080
- docker-compose.yml exists in project root
"""
    
    workspace = str(Path.cwd())
    
    # Choose mode based on command line argument
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    
    if mode == "full":
        print("Mode: Full Interactive UI\n")
        result = run_with_full_ui(problem, workspace, max_steps=6)
    elif mode == "simple":
        print("Mode: Simple Progress Bar\n")
        result = run_with_simple_progress(problem, workspace, max_steps=6)
    elif mode == "silent":
        print("Mode: Silent (verbose logs)\n")
        result = run_silent(problem, workspace, max_steps=6)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python demo_ui.py [full|simple|silent]")
        sys.exit(1)
    
    print(f"\n✅ Investigation complete (Session ID: {result['session_model'].session_id})")
