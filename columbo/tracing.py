"""
MLflow tracing utilities for Columbo debugging agent.

Provides optional tracing capabilities to track:
- Debug loop iterations
- DSPy module calls (hypothesis generation, probe planning, etc.)
- Probe executions
- Overall session flow
"""

from typing import Any, Dict, Optional, Callable
from functools import wraps
import json

# Try to import mlflow for tracing
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def trace_enabled() -> bool:
    """Check if MLflow tracing is available and enabled."""
    if not MLFLOW_AVAILABLE:
        return False
    
    # Check if there's an active MLflow run
    try:
        active_run = mlflow.active_run()
        return active_run is not None
    except Exception:
        return False


def trace_step(step_name: str):
    """Decorator to trace a debug step with MLflow.
    
    Args:
        step_name: Name of the step (e.g., "hypothesis_generation", "probe_planning")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not trace_enabled():
                return func(*args, **kwargs)
            
            with mlflow.start_span(name=step_name) as span:
                # Log inputs
                span.set_inputs({"args": str(args)[:500], "kwargs": str(kwargs)[:500]})
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Log outputs
                if result is not None:
                    output_str = str(result)[:1000]  # Limit size
                    span.set_outputs({"result": output_str})
                
                return result
        
        return wrapper
    return decorator


def trace_probe_execution(probe_name: str, probe_args: Dict[str, Any], result: Any, error: Optional[str] = None):
    """Trace a probe execution with MLflow.
    
    Args:
        probe_name: Name of the probe executed
        probe_args: Arguments passed to the probe
        result: Result from the probe
        error: Error message if probe failed
    """
    if not trace_enabled():
        return
    
    try:
        with mlflow.start_span(name=f"probe:{probe_name}") as span:
            # Log probe details
            span.set_inputs({
                "probe_name": probe_name,
                "probe_args": json.dumps(probe_args, default=str)[:500]
            })
            
            # Log result or error
            if error:
                span.set_attribute("error", True)
                span.set_outputs({"error": error[:500]})
            else:
                result_str = json.dumps(result, default=str)[:1000]
                span.set_outputs({"result": result_str})
                span.set_attribute("success", True)
    except Exception as e:
        # Silently fail - don't break execution if tracing fails
        pass


def trace_reasoning_step(
    step_type: str,
    step_num: int,
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
):
    """Trace a reasoning step (hypothesis gen, probe planning, etc.).
    
    Args:
        step_type: Type of reasoning step (e.g., "hypothesis_generation")
        step_num: Current step number
        inputs: Input data for the reasoning step
        outputs: Output data from the reasoning step
        metadata: Optional metadata (e.g., confidence, selected probe)
    """
    if not trace_enabled():
        return
    
    try:
        span_name = f"step_{step_num}:{step_type}"
        with mlflow.start_span(name=span_name) as span:
            # Log inputs
            input_str = {k: str(v)[:500] for k, v in inputs.items()}
            span.set_inputs(input_str)
            
            # Log outputs
            output_str = {k: str(v)[:500] for k, v in outputs.items()}
            span.set_outputs(output_str)
            
            # Log metadata as attributes
            if metadata:
                for key, value in metadata.items():
                    span.set_attribute(key, str(value)[:100])
            
            span.set_attribute("step_number", step_num)
            span.set_attribute("step_type", step_type)
    except Exception as e:
        # Silently fail
        pass


def trace_session(session_id: str, initial_problem: str, max_steps: int):
    """Create a parent trace span for the entire debugging session.
    
    Args:
        session_id: Unique session identifier
        initial_problem: Initial problem description
        max_steps: Maximum steps allowed
    
    Returns:
        Context manager for the session span (or dummy context if tracing disabled)
    """
    if not trace_enabled():
        # Return a dummy context manager
        from contextlib import nullcontext
        return nullcontext()
    
    return mlflow.start_span(
        name="debug_session",
        span_type="CHAIN",
        attributes={
            "session_id": session_id,
            "initial_problem": initial_problem[:200],
            "max_steps": max_steps
        }
    )
