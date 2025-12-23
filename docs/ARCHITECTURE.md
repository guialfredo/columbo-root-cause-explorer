# Schema Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User Entry Point                           │
│                            main.py                                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Debug Loop Core                              │
│                         debug_loop.py                                │
│                                                                      │
│  1. Creates DebugSession (Pydantic model)                           │
│  2. For each step:                                                   │
│     - Generate hypotheses (DSPy)                                     │
│     - Plan probe (DSPy) → converts to ProbePlanOutput               │
│     - Execute probe → creates ProbeCall                              │
│     - Check signature for duplicates                                 │
│     - Digest evidence → creates Finding                              │
│     - Stop decision (DSPy) → converts to StopDecision               │
│  3. Final diagnosis (DSPy)                                          │
│  4. Return dict + session_model                                     │
└───────────┬────────────────────┬────────────────────┬───────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
    ┌───────────────┐   ┌──────────────┐   ┌─────────────────┐
    │   schemas.py  │   │converters.py │   │ session_utils.py│
    │               │   │              │   │                 │
    │ Core Models:  │   │ Converters:  │   │ Utilities:      │
    │ DebugSession  │◄──┤ DSPy→Pydantic│   │ Save/Load       │
    │ ProbeCall     │   │              │   │ Report Gen      │
    │ Finding       │   │ - parse_stop │   │ Analytics       │
    │ Hypothesis    │   │ - parse_plan │   │ Export          │
    │ RootCause     │   │ - extract    │   └─────────────────┘
    │ StopDecision  │   └──────────────┘
    │ ...           │
    └───────────────┘
            │
            │ Uses
            ▼
    ┌───────────────────────────────────────┐
    │         Pydantic Features             │
    │                                       │
    │ • Validation                          │
    │ • Computed Properties                 │
    │ • Serialization (model_dump)          │
    │ • Type Safety                         │
    │ • Field Constraints                   │
    └───────────────────────────────────────┘
```

## Data Flow Example

```
Initial Problem (str)
    │
    ▼
┌─────────────────────┐
│  DebugSession       │
│  - session_id       │
│  - initial_problem  │
│  - max_steps        │
│  - probe_history: []│
│  - findings_log: [] │
└──────────┬──────────┘
           │
           │ For each step...
           ▼
    ┌──────────────┐
    │ DSPy Modules │
    │ (LLM calls)  │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐         ┌────────────────┐
    │ Raw Output   │────────>│  Converters    │
    │ (unstructured│         │  parse_*()     │
    └──────────────┘         └────────┬───────┘
                                      │
                                      ▼
                             ┌─────────────────┐
                             │ Pydantic Models │
                             │ - ProbeCall     │
                             │ - Finding       │
                             │ - StopDecision  │
                             └────────┬────────┘
                                      │
                                      ▼
                             ┌─────────────────┐
                             │  Add to Session │
                             │  probe_history  │
                             │  findings_log   │
                             └─────────────────┘
```

## Integration Points

### 1. Session Initialization
```python
# debug_loop.py line ~310
session = DebugSession(
    session_id=str(uuid.uuid4())[:8],
    initial_problem=initial_evidence,
    workspace_root=workspace_root,
    max_steps=max_steps,
    current_step=0
)
```

### 2. Probe Execution
```python
# debug_loop.py line ~380
probe_call = ProbeCall(
    step=step + 1,
    probe_name=probe_name,
    probe_args=parse_probe_args(probe_args),
    started_at=datetime.utcnow(),
    finished_at=datetime.utcnow(),
    result=raw_probe_result,
    error=raw_probe_result.get("error")
)
probe_call.signature = probe_call.compute_signature()
session.probe_history.append(probe_call)
```

### 3. Deduplication Check
```python
# debug_loop.py line ~360
if probe_signature in session.get_executed_probe_signatures():
    # Skip duplicate
    continue
```

### 4. Stop Decision
```python
# debug_loop.py line ~450
stop_decision = parse_stop_decision(stop_decision_raw)
session.should_stop = stop_decision.should_stop
session.stop_reason = stop_decision.reasoning
```

### 5. Return Enhanced Results
```python
# debug_loop.py line ~500
return {
    "diagnosis": {...},
    "debug_session": {...},
    "session_model": session  # NEW: Full Pydantic model
}
```

## Usage Patterns

### Pattern 1: Access Structured Data
```python
result = debug_loop(...)
session = result["session_model"]

# Type-safe access
for probe in session.probe_history:
    if probe.duration_seconds > 1.0:
        print(f"Slow probe: {probe.probe_name}")
```

### Pattern 2: Persist Sessions
```python
from session_utils import save_session_to_file

save_session_to_file(session, "./sessions")
# Creates: ./sessions/debug_session_{id}.json
```

### Pattern 3: Generate Reports
```python
from session_utils import generate_session_report

report = generate_session_report(session)
Path(f"report_{session.session_id}.md").write_text(report)
```

### Pattern 4: Analytics
```python
from session_utils import analyze_probe_performance

perf = analyze_probe_performance(session)
print(f"Total time: {perf['total_time']:.2f}s")
print(f"Success rate: {perf['success_rate']:.1%}")
```

## Benefits by Component

### schemas.py
- ✅ Single source of truth for data structures
- ✅ Automatic validation on construction
- ✅ Computed properties (duration, success, etc.)
- ✅ Type hints for IDE support

### converters.py
- ✅ Clean separation: DSPy outputs → Pydantic models
- ✅ Handles parsing and validation
- ✅ Error handling for malformed LLM outputs
- ✅ Reusable conversion logic

### session_utils.py
- ✅ High-level operations on sessions
- ✅ Serialization (JSON) and deserialization
- ✅ Report generation (Markdown)
- ✅ Performance analytics
- ✅ Export to FinalArtifact

### debug_loop.py
- ✅ Uses structured models internally
- ✅ Maintains backward compatibility
- ✅ Cleaner code with type safety
- ✅ Built-in deduplication

## Migration Impact

### Before (Dict-based)
```python
probe = {
    "step": 1,
    "probe_name": "logs",
    "probe_args": {"tail": 50},
    "result": {...}
}

# No validation
# No computed properties
# Manual serialization
# No type hints
```

### After (Schema-based)
```python
probe = ProbeCall(
    step=1,
    probe_name="logs",
    probe_args={"tail": 50},
    started_at=datetime.utcnow(),
    finished_at=datetime.utcnow(),
    result={...}
)

# Automatic validation ✅
# Computed properties ✅
# Built-in serialization ✅
# Full type hints ✅
```

## Future Possibilities

With schemas in place:

1. **Database Integration**
   ```python
   from sqlmodel import SQLModel
   # ProbeCall already Pydantic → easy DB storage
   ```

2. **API Endpoints**
   ```python
   from fastapi import FastAPI
   # Schemas automatically become API contracts
   ```

3. **ML Training Data**
   ```python
   # Export structured sessions for training
   artifacts = [create_final_artifact(s) for s in sessions]
   ```

4. **Observability**
   ```python
   # Export metrics to Prometheus/Datadog
   metrics = analyze_probe_performance(session)
   ```

5. **Collaborative Debugging**
   ```python
   # Share sessions between team members
   session_json = session.model_dump_json()
   ```
