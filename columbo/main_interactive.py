"""Interactive UI version of the debugging assistant agent."""

import dspy
from columbo.debug_loop import debug_loop
from columbo.ui import ColumboUI
from columbo.session_utils import (
    save_session_to_file, 
    generate_session_report,
)
from pathlib import Path
from dotenv import load_dotenv
import os


def setup_dspy_llm(api_key: str):
    """Configure DSPy with your LLM of choice."""
    lm = dspy.LM("openai/gpt-5-mini", api_key=api_key, cache=False)
    dspy.configure(lm=lm)


if __name__ == "__main__":
    # Setup LLM
    load_dotenv()
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

    # Create interactive UI
    ui = ColumboUI(max_steps=6)
    ui.start()

    try:
        # Run the debug loop with UI callbacks
        result = debug_loop(
            initial_evidence=initial_evidence, 
            max_steps=6, 
            workspace_root=workspace_root,
            ui_callback=ui
        )

        # Show final diagnosis
        diagnosis = result["diagnosis"]
        ui.show_final_diagnosis(diagnosis)
        
        # Save session artifacts
        session_model = result["session_model"]
        output_path = save_session_to_file(session_model)
        
        # Generate report
        report_path = generate_session_report(session_model)
        
        print(f"\n📄 Session saved to: {output_path}")
        print(f"📋 Report saved to: {report_path}")
        
    except KeyboardInterrupt:
        ui.stop()
        print("\n\n⚠️  Investigation interrupted by user")
    except Exception as e:
        ui.stop()
        print(f"\n\n❌ Error during investigation: {e}")
        raise
