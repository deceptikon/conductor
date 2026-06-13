"""conductor — model-agnostic orchestration harness.

Hermes is the conductor; Claude Code / Gemini CLI / Qwen Code are stateless
headless workers driven through a LangGraph Plan->Approve->Act->QA->Commit
pipeline. All durable state lives in the SQLite checkpointer + the RVC vault,
never in a worker's private session memory.
"""
__version__ = "0.1.0"
