# Columbo Evaluation Framework

## Core Trade-off

Columbo must balance two competing objectives:
- **Efficiency**: Solve problems in as few steps as possible
- **Groundedness**: Gather sufficient evidence before concluding, ensuring trustworthy diagnoses

## Current Metrics (Implemented)

All scenarios include labeled ground truth data in `manifest.json` for scoring.

### 1. Probe Recall
- **Method**: Automated comparison against `manifest.json`
- **Question**: Did Columbo call all mandatory probes defined in the scenario?
- **Output**: Recall percentage (mandatory probes called / total mandatory probes)
- **Implementation**: `calculate_probe_recall()` in `evaluation/metrics.py`

### 2. Step Efficiency
- **Method**: Automated count comparison
- **Metrics**:
  - Total steps taken
  - Optimal steps (defined in manifest.json)
  - Efficiency score: min(1.0, optimal_steps / steps_used)
  - Efficiency ratio: optimal_steps / steps_used (uncapped)
- **Implementation**: `calculate_step_efficiency()` in `evaluation/metrics.py`

### 3. Groundedness
- **Method**: LLM-as-judge grading
- **Question**: Is the diagnosis well-supported by the evidence gathered? Did the agent jump to conclusions?
- **Purpose**: Measures whether claims are backed by concrete evidence from probes
- **Output**: Score (0-10) with justification
- **Implementation**: `calculate_groundedness()` using DSPy ChainOfThought in `evaluation/metrics.py`

### 4. Category Match (Placeholder)
- **Method**: Automated binary check against `manifest.json`
- **Question**: Did Columbo correctly identify the problem category?
- **Status**: **Not functional yet** - requires agent to track and output problem categories
- **Taxonomy**: Defined in `evaluation/categories_taxonomy.json`
- **Categories**: configuration, build-configuration, volumes, networking, permission, resource, dependency
- **Implementation**: `calculate_category_match()` - currently returns False until agent enhancement
- **Next Steps**: 
  1. Provide taxonomy to agent during investigation
  2. Add category field to DiagnosisResult schema
  3. Teach agent to classify problems

## Future Enhancements

Potential additions for later iterations:
- **Task Completion**: LLM judge comparing final diagnosis against expected root cause ID
- **Early Detection**: How many steps before identifying the correct category?
- **Tool Precision**: Percentage of probes that were relevant vs unnecessary
- **Evidence Quality**: Richness of gathered evidence per step
- **Reasoning Coherence**: Quality of hypothesis evolution over time

## Summary Table

| Metric | Type | Status | Data Source | Complexity |
|--------|------|--------|-------------|------------|
| Probe Recall | Automated | ✅ Implemented | manifest.json | Low |
| Step Efficiency | Automated | ✅ Implemented | Session log | Low |
| Groundedness | LLM Judge | ✅ Implemented | Diagnosis + Evidence | Medium |
| Category Match | Automated | ⚠️ Placeholder | manifest.json + taxonomy | Low |
| Task Completion | LLM Judge | ❌ Future | Diagnosis + Expected RC | Medium |