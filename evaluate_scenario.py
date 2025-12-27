"""
Evaluate the debugging assistant on a specific scenario.

This script:
1. Spins up a scenario using Docker Compose
2. Runs the debugging assistant with the scenario's initial evidence
3. Compares the diagnosis with the expected root cause
4. Tears down the scenario
5. Generates an evaluation report
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv
import os
import dspy
import time
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scenarios.common.runner import (
    load_scenario,
    spin_up_scenario,
    tear_down_scenario,
    check_and_resolve_conflicts,
)
from debugging_assistant.debug_loop import debug_loop
from debugging_assistant.session_utils import (
    save_session_to_file,
    generate_session_report,
)


def setup_dspy_llm(api_key: str):
    """Configure DSPy with your LLM of choice."""
    lm = dspy.LM("openai/gpt-5-mini", api_key=api_key, cache=False)
    dspy.configure(lm=lm)


def evaluate_diagnosis(
    diagnosis: dict,
    optimal_steps: int,
    session_model,
) -> dict:
    """Evaluate the debugging session performance.
    
    Returns:
        dict with evaluation metrics
    """
    steps_used = session_model.current_step
    
    # Simple efficiency score: optimal steps / actual steps
    # Capped at 1.0 for overperformance
    efficiency_score = min(1.0, optimal_steps / steps_used) if steps_used > 0 else 0
    
    return {
        "steps_used": steps_used,
        "optimal_steps": optimal_steps,
        "efficiency_score": efficiency_score,
        "confidence": diagnosis["confidence"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate debugging assistant on a scenario"
    )
    parser.add_argument(
        "scenario_id",
        help="Scenario ID to evaluate (e.g., s001_env_override)"
    )
    parser.add_argument(
        "--no-spin-up",
        action="store_true",
        help="Skip spinning up the scenario (assume it's already running)"
    )
    parser.add_argument(
        "--no-teardown",
        action="store_true",
        help="Skip tearing down the scenario after evaluation"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Automatically cleanup conflicting containers before starting"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation_results"),
        help="Directory to save evaluation results"
    )
    
    args = parser.parse_args()
    
    # Setup
    print("=" * 70)
    print("COLUMBO SCENARIO EVALUATOR")
    print("=" * 70)
    
    # Load environment and configure LLM
    load_dotenv()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY not set in environment")
        return 1
    
    setup_dspy_llm(api_key=openai_api_key)
    
    # Load scenario
    scenarios_root = project_root / "scenarios"
    print(f"\nLoading scenario: {args.scenario_id}")
    
    try:
        scenario_ref = load_scenario(scenarios_root, args.scenario_id)
        manifest = scenario_ref.load_manifest()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    
    print(f"✓ Loaded: {manifest.title}")
    print(f"  Difficulty: {manifest.difficulty}")
    print(f"  Max steps: {manifest.budgets['max_steps']}")
    print(f"  Optimal steps: {manifest.budgets['optimal_steps']}")
    
    # Check for conflicts before spinning up
    if not args.no_spin_up:
        print(f"\n{'=' * 70}")
        print("PRE-FLIGHT CHECKS")
        print("=" * 70)
        
        conflicts_resolved = check_and_resolve_conflicts(
            args.scenario_id,
            auto_cleanup=args.cleanup,
            force=False
        )
        
        if not conflicts_resolved:
            print("\n💡 Tip: Run with --cleanup to automatically resolve conflicts")
            return 1
    
    # Spin up scenario
    compose_spec = None
    if not args.no_spin_up:
        print(f"\n{'=' * 70}")
        print("SPINNING UP SCENARIO")
        print("=" * 70)
        
        try:
            compose_spec = spin_up_scenario(scenario_ref)
            print(f"✓ Scenario spun up (project: {compose_spec.project_name})")
            
            # Wait for containers to stabilize
            print("\nWaiting for containers to stabilize...")
            time.sleep(5)
            
        except Exception as e:
            print(f"ERROR spinning up scenario: {e}")
            return 1
    
    # Run debugging assistant
    print(f"\n{'=' * 70}")
    print("RUNNING DEBUGGING ASSISTANT")
    print("=" * 70)
    
    initial_evidence = manifest.initial_evidence
    if not initial_evidence:
        print("WARNING: No initial_evidence in manifest, using default")
        initial_evidence = f"Problem: Service failure in {manifest.title}"
    
    print(f"\nInitial Evidence:\n{initial_evidence}\n")
    
    try:
        result = debug_loop(
            initial_evidence=initial_evidence,
            max_steps=manifest.budgets['max_steps'],
            workspace_root=str(scenario_ref.scenario_dir),
        )
        
        diagnosis = result["diagnosis"]
        session_model = result["session_model"]
        
    except Exception as e:
        print(f"ERROR during debugging: {e}")
        if compose_spec and not args.no_teardown:
            print("\nTearing down scenario...")
            tear_down_scenario(compose_spec)
        return 1
    
    # Evaluate results
    print(f"\n{'=' * 70}")
    print("EVALUATION RESULTS")
    print("=" * 70)
    
    evaluation = evaluate_diagnosis(
        diagnosis=diagnosis,
        optimal_steps=manifest.budgets['optimal_steps'],
        session_model=session_model,
    )
    
    print(f"\n📊 Efficiency Score: {evaluation['efficiency_score']:.2%}")
    print(f"   Steps Used: {evaluation['steps_used']} (optimal: {evaluation['optimal_steps']})")
    print(f"   Confidence: {evaluation['confidence']}")
    
    print(f"\n{'=' * 70}")
    print("DIAGNOSIS")
    print("=" * 70)
    print(f"\nRoot Cause:\n{diagnosis['root_cause']}")
    print(f"\nRecommended Fixes:\n{diagnosis['recommended_fixes']}")
    
    print(f"\n{'=' * 70}")
    print("EXPECTED ROOT CAUSE")
    print("=" * 70)
    print(f"\nID: {manifest.grading['expected_root_cause_id']}")
    
    # Save results
    args.output_dir.mkdir(exist_ok=True)
    
    # Save session
    session_file = save_session_to_file(
        session_model,
        str(args.output_dir)
    )
    print(f"\n💾 Session saved to: {session_file}")
    
    # Save report
    report = generate_session_report(session_model)
    report_file = args.output_dir / f"report_{session_model.session_id}.md"
    report_file.write_text(report)
    print(f"💾 Report saved to: {report_file}")
    
    # Save evaluation
    eval_file = args.output_dir / f"evaluation_{session_model.session_id}.json"
    eval_data = {
        "scenario_id": manifest.scenario_id,
        "scenario_title": manifest.title,
        "session_id": session_model.session_id,
        "evaluation": evaluation,
        "diagnosis": diagnosis,
        "expected_root_cause_id": manifest.grading['expected_root_cause_id'],
        "timestamp": session_model.started_at.isoformat(),
    }
    eval_file.write_text(json.dumps(eval_data, indent=2, default=str))
    print(f"💾 Evaluation saved to: {eval_file}")
    
    # Tear down scenario
    if compose_spec and not args.no_teardown:
        print(f"\n{'=' * 70}")
        print("TEARING DOWN SCENARIO")
        print("=" * 70)
        
        try:
            tear_down_scenario(compose_spec)
            print("✓ Scenario torn down")
        except Exception as e:
            print(f"ERROR tearing down scenario: {e}")
    
    # Final summary
    print(f"\n{'=' * 70}")
    print("EVALUATION COMPLETE")
    print("=" * 70)
    
    if evaluation['efficiency_score'] >= 0.8:
        print("\n✅ EXCELLENT: Debugging completed efficiently!")
    elif evaluation['efficiency_score'] >= 0.5:
        print("\n⚠️  ACCEPTABLE: Debugging completed but used more steps than optimal")
    else:
        print("\n❌ NEEDS IMPROVEMENT: Debugging took significantly more steps than expected")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
