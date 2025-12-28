# Copilot Instructions – Columbo Project

This project implements a deterministic, hypothesis-driven debugging agent
for containerized systems. Preserve its investigative semantics at all times.

## General Principles
- Prefer clarity and explicitness over cleverness
- Avoid adding abstractions unless they already exist in the architecture
- Do not refactor across modules without strong justification
- Follow existing patterns exactly when extending functionality

## Determinism & Safety
- Probes MUST be deterministic
- Probes MUST NEVER raise exceptions
- Always return structured dictionaries suitable for LLM digestion
- Handle failures explicitly in returned evidence, not via exceptions

## Architecture Rules
- Keep strict separation between:
  - reasoning (DSPy modules)
  - orchestration (debug loop)
  - probing (infrastructure inspection)
  - data models (Pydantic schemas)
- Never mix probing logic with reasoning logic
- Never mutate session state outside defined update paths

## Pydantic & Typing
- Use Pydantic models consistently
- Do not introduce untyped dicts where models exist
- Preserve existing field names and semantics
- Prefer explicit Optional[...] over implicit None usage

## LLM Interaction
- LLM outputs must be structured and schema-aligned
- Do not rely on free-form text parsing
- Avoid adding “helpful” natural language explanations inside data objects

## Style
- Python 3.11+
- Type hints everywhere
- Docstrings for public functions
- Favor small, composable functions

When uncertain about intent, ask clarifying questions instead of guessing.
