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
    analyze_probe_performance,
)


def setup_dspy_llm(api_key: str):
    """Configure DSPy with your LLM of choice."""
    lm = dspy.LM("openai/gpt-5-mini", api_key=api_key, cache=False)
    dspy.configure(lm=lm)


def evaluate_diagnosis(
    diagnosis: dict,
    expected_root_cause: dict,
    session_model,
) -> dict:
    """Evaluate how well the diagnosis matches the expected root cause.
    
    Returns:
        dict with evaluation metrics
    """
    root_cause_text = diagnosis["root_cause"].lower()
    expected_keywords = expected_root_cause.get("keywords", [])
    expected_summary = expected_root_cause.get("summary", "").lower()
    
    # Check keyword matches
    keywords_found = [kw for kw in expected_keywords if kw.lower() in root_cause_text]
    keyword_score = len(keywords_found) / len(expected_keywords) if expected_keywords else 0
    
    # Check if summary concepts are mentioned
    summary_words = expected_summary.split()
    summary_matches = sum(1 for word in summary_words if len(word) > 3 and word in root_cause_text)
    summary_score = summary_matches / len(summary_words) if summary_words else 0
    
    # Check if location is mentioned
    expected_location = expected_root_cause.get("location", "")
    location_mentioned = expected_location.lower() in root_cause_text if expected_location else False
    
    # Overall score
    overall_score = (keyword_score * 0.5 + summary_score * 0.3 + (1.0 if location_mentioned else 0.0) * 0.2)
    
    return {
        "overall_score": overall_score,
        "keyword_score": keyword_score,
        "keywords_found": keywords_found,
        "summary_score": summary_score,
        "location_mentioned": location_mentioned,
        "steps_used": session_model.current_step,
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
    print(f"  Max steps: {manifest.max_debug_steps}")
    
    # Check for conflicts before spinning up
    if not args.no_spin_up:
        print(f"\n{'=' * 70}")
        print("PRE-FLIGHT CHECKS")
        print("=" * 70)
        
        conflicts_resolved = check_and_resolve_conflicts(
            manifest,
            auto_cleanup=args.cleanup,
            force=False
        )
        
        if not conflicts_resolved:
            print("\n💡 Tip: Run with --cleanup to automatically resolve conflicts")
      
    print(f"✓ Loaded: {manifest.title}")
    print(f"  Difficulty: {manifest.difficulty}")
    print(f"  Max steps: {manifest.max_debug_steps}")
    
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
        initial_evidence = f"Problem: {manifest.description}"
    
    print(f"\nInitial Evidence:\n{initial_evidence}\n")
    
    try:
        result = debug_loop(
            initial_evidence=initial_evidence,
            max_steps=manifest.max_debug_steps,
            workspace_root=str(scenario_ref.scenario_dir),
        )
        
        diagnosis = result["diagnosis"]
        debug_session = result["debug_session"]
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
        expected_root_cause=manifest.expected_root_cause,
        session_model=session_model,
    )
    
    print(f"\n📊 Overall Score: {evaluation['overall_score']:.2%}")
    print(f"   Keyword Score: {evaluation['keyword_score']:.2%}")
    print(f"   Summary Score: {evaluation['summary_score']:.2%}")
    print(f"   Location Mentioned: {'✓' if evaluation['location_mentioned'] else '✗'}")
    print(f"   Steps Used: {evaluation['steps_used']}/{manifest.max_debug_steps}")
    print(f"   Confidence: {evaluation['confidence']}")
    
    print(f"\n🔍 Keywords Found: {', '.join(evaluation['keywords_found'])}")
    
    print(f"\n{'=' * 70}")
    print("DIAGNOSIS")
    print("=" * 70)
    print(f"\nRoot Cause:\n{diagnosis['root_cause']}")
    print(f"\nRecommended Fixes:\n{diagnosis['recommended_fixes']}")
    
    print(f"\n{'=' * 70}")
    print("EXPECTED ROOT CAUSE")
    print("=" * 70)
    print(f"\nID: {manifest.expected_root_cause.get('id')}")
    print(f"Summary: {manifest.expected_root_cause.get('summary')}")
    print(f"Location: {manifest.expected_root_cause.get('location')}")
    
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
        "scenario_name": manifest.name,
        "session_id": session_model.session_id,
        "evaluation": evaluation,
        "diagnosis": diagnosis,
        "expected_root_cause": manifest.expected_root_cause,
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
    
    if evaluation['overall_score'] >= 0.7:
        print("\n✅ PASS: Debugging assistant successfully identified the root cause!")
    elif evaluation['overall_score'] >= 0.4:
        print("\n⚠️  PARTIAL: Debugging assistant partially identified the issue")
    else:
        print("\n❌ FAIL: Debugging assistant did not identify the root cause")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
