"""Example usage of the debugging assistant agent."""

import dspy
from columbo.debug_loop import debug_loop
from columbo.session_utils import (
    save_session_to_file, 
    generate_session_report,
    analyze_probe_performance
)
from pathlib import Path
from dotenv import load_dotenv
import os


def setup_dspy_llm(api_key: str, seed: int = None):
    """Configure DSPy with your LLM of choice.
    
    Args:
        api_key: OpenAI API key
        seed: Optional random seed for reproducible outputs
    """
    # For demo purposes, using OpenAI
    kwargs = {"api_key": api_key, "cache": False}
    if seed is not None:
        kwargs["seed"] = seed
    lm = dspy.LM("openai/gpt-5-mini", **kwargs)
    dspy.configure(lm=lm)


if __name__ == "__main__":
    # Setup LLM
    print("Configuring LLM...")
    load_dotenv()  # Load .env file if present
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY not set in environment.")
    
    # Optional: Set seed for reproducible runs
    seed = os.getenv("COLUMBO_SEED")
    seed = int(seed) if seed else None
    if seed:
        print(f"Using seed: {seed} for reproducible outputs")
    
    setup_dspy_llm(api_key=openai_api_key, seed=seed)

    # Define the initial problem/evidence
    initial_evidence = """
Hi I have a Problem: My rag-agent is failing to connect to my vectordb container.

I have no error details.

Context:
- Vectordb should be running in a Docker container
- Expected to be accessible from the rag-agent container
- docker-compose.yml exists in the project root
"""

    # Get workspace root
    workspace_root = str(Path(__file__).parent.parent)

    # Run the debug loop
    print("\n" + "=" * 70)
    print("STARTING DEBUGGING SESSION")
    print("=" * 70 + "\n")

    result = debug_loop(
        initial_evidence=initial_evidence, max_steps=6, workspace_root=workspace_root
    )

    # Print final results
    print("\n" + "=" * 70)
    print("DEBUGGING SESSION COMPLETE")
    print("=" * 70)
    
    # Access the new structured result format
    diagnosis = result["diagnosis"]
    debug_session = result["debug_session"]
    session_model = result["session_model"]  # The full Pydantic model
    
    print(f"\nTotal probing steps: {debug_session['total_steps']}")
    print(f"Session ID: {session_model.session_id}")
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)
    print(f"\nRoot Cause:\n{diagnosis['root_cause']}")
    print(f"\nConfidence: {diagnosis['confidence']}")
    print(f"\nRecommended Fixes:\n{diagnosis['recommended_fixes']}")
    if diagnosis['additional_notes']:
        print(f"\nAdditional Notes:\n{diagnosis['additional_notes']}")
    
    print("\n" + "-" * 70)
    print("EVIDENCE LOG (All Findings):")
    print("-" * 70)
    for finding in debug_session["evidence_log"]:
        print(finding)

    print("\n" + "-" * 70)
    print("PROBES EXECUTED:")
    print("-" * 70)
    for probe in debug_session["probes_executed"]:
        print(f"\nStep {probe['step']}: {probe['probe_name']}")
        print(f"  Args: {probe['probe_args']}")
    
    # NEW: Use the structured session model for advanced features
    print("\n" + "=" * 70)
    print("SESSION ANALYTICS (Using Pydantic Models)")
    print("=" * 70)
    
    # Performance analysis
    perf = analyze_probe_performance(session_model)
    print(f"\nProbe Performance:")
    print(f"  Total execution time: {perf.get('total_time', 0):.2f}s")
    print(f"  Average per probe: {perf.get('avg_time_per_probe', 0):.2f}s")
    print(f"  Success rate: {perf.get('success_rate', 0):.1%}")
    
    # Save session to file
    print("\n" + "-" * 70)
    output_dir = Path(workspace_root) / "debug_sessions"
    output_dir.mkdir(exist_ok=True)
    
    session_file = save_session_to_file(session_model, str(output_dir))
    print(f"Session data saved to: {session_file}")
    
    # Generate and save markdown report
    report = generate_session_report(session_model)
    report_file = output_dir / f"report_{session_model.session_id}.md"
    report_file.write_text(report)
    print(f"Session report saved to: {report_file}")
