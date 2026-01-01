# Columbo Evaluation Framework

## Core Trade-off

Columbo must balance two competing objectives:
- **Efficiency**: Solve problems in as few steps as possible
- **Groundedness**: Gather sufficient evidence before concluding, ensuring trustworthy diagnoses

## Evaluation Metrics

All scenarios include labeled ground truth data in `manifest.json` for scoring.

### 1. Task Completion
- **Method**: LLM-as-judge grading
- **Question**: Did Columbo correctly identify and explain the root cause?
- **Output**: Score (e.g., 0-10 or pass/fail)

### 2. Stopping Criterion Quality
- **Method**: LLM-as-judge grading
- **Question**: Was the decision to stop debugging justified by the evidence gathered?
- **Purpose**: Measures groundedness - did it conclude prematurely or gather sufficient proof?
- **Output**: Score (e.g., 0-10)

### 3. Tool Recall
- **Method**: Automated comparison against manifest.json
- **Question**: Did Columbo call all mandatory probes defined in the scenario?
- **Output**: Recall percentage (mandatory tools called / total mandatory tools)

### 4. Step Efficiency
- **Method**: Simple count comparison
- **Metrics**:
  - Total steps taken
  - Comparison to optimal path (defined in manifest.json)
  - Ratio: actual steps / optimal steps

### 5. Problem Category Identification
- **Method**: Binary match against manifest.json
- **Question**: Did Columbo correctly classify the problem category?
- **Output**: Binary (correct/incorrect)

## Future Enhancements

Potential additions for later iterations:
- **Early detection**: How many steps before identifying the correct category?
- **Tool precision**: Percentage of probes that were relevant vs unnecessary
- **Evidence quality**: Richness of gathered evidence per step
- **Reasoning coherence**: Quality of hypothesis evolution

## Summary Table

| Metric | Type | Data Source | Complexity |
|--------|------|-------------|------------|
| Task Completion | LLM Judge | Debug report | Medium |
| Stopping Quality | LLM Judge | Session + evidence | Medium |
| Tool Recall | Automated | manifest.json | Low |
| Step Efficiency | Automated | Session log | Low |
| Category Match | Automated | manifest.json | Low |