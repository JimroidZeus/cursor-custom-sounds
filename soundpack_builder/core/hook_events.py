"""Single source of truth for hook event names, target WAV filenames, and slot counts."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

# Order matches transcript / classifier pipeline and template generation.
HOOK_EVENT_ORDER: Tuple[str, ...] = (
    "beforeSubmitPrompt",
    "afterAgentThought",
    "afterAgentResponse",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "stop",
)

EVENT_FILES: Dict[str, List[str]] = {
    "beforeSubmitPrompt": ["beforeSubmitPrompt_1.wav", "beforeSubmitPrompt_2.wav"],
    "afterAgentThought": ["afterAgentThought_1.wav", "afterAgentThought_2.wav"],
    "afterAgentResponse": ["afterAgentResponse_1.wav", "afterAgentResponse_2.wav"],
    "preToolUse": ["preToolUse.wav"],
    "postToolUse": ["postToolUse.wav"],
    "postToolUseFailure": ["postToolUseFailure.wav"],
    "stop": ["stop.wav"],
}

TARGET_TO_EVENT: Dict[str, str] = {
    "beforeSubmitPrompt_1.wav": "beforeSubmitPrompt",
    "beforeSubmitPrompt_2.wav": "beforeSubmitPrompt",
    "afterAgentThought_1.wav": "afterAgentThought",
    "afterAgentThought_2.wav": "afterAgentThought",
    "afterAgentResponse_1.wav": "afterAgentResponse",
    "afterAgentResponse_2.wav": "afterAgentResponse",
    "preToolUse.wav": "preToolUse",
    "postToolUse.wav": "postToolUse",
    "postToolUseFailure.wav": "postToolUseFailure",
    "stop.wav": "stop",
}

EVENT_TARGET_COUNTS: Dict[str, int] = {
    "beforeSubmitPrompt": 2,
    "afterAgentThought": 2,
    "afterAgentResponse": 2,
    "preToolUse": 1,
    "postToolUse": 1,
    "postToolUseFailure": 1,
    "stop": 1,
}


def target_filenames_in_order() -> List[str]:
    """Flat hook pack filenames in pipeline order (archive ZIP row alignment)."""
    return [name for ev in HOOK_EVENT_ORDER for name in EVENT_FILES[ev]]


def discovery_target_filename(index: int) -> str:
    """Neutral WAV basename for discovery-sourced clips (before hook assignment / mapping).

    ``index`` is zero-based; the first clip is ``discovery_001.wav``.
    """
    return f"discovery_{index + 1:03d}.wav"


def is_discovery_target_file(name: str) -> bool:
    """True if ``name`` looks like a discovery-pipeline filename (not a hook slot name)."""
    return Path(name).stem.lower().startswith("discovery")
