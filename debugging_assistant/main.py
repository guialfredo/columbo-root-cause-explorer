"""Example usage of the debugging assistant agent."""

import dspy
from debugging_assistant.debug_loop import debug_loop
from pathlib import Path
from dotenv import load_dotenv
import os


def setup_dspy_llm(api_key: str):
    """Configure DSPy with your LLM of choice."""
    # For demo purposes, using OpenAI
    lm = dspy.LM("openai/gpt-5-mini", api_key=api_key, cache=False)
    dspy.configure(lm=lm)


if __name__ == "__main__":
    # Setup LLM
    print("Configuring LLM...")
    load_dotenv()  # Load .env file if present
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY not set in environment.")
    setup_dspy_llm(api_key=openai_api_key)

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
    
    print(f"\nTotal probing steps: {debug_session['total_steps']}")
    
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
