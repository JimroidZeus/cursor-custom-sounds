# Cursor Custom Sounds

This repository now uses Cursor's official Hooks system for chat lifecycle sounds.

## Config

Primary configuration lives in:

- `.cursor/hooks.json`
- `.cursor/hooks/sound-config.json`

For full setup and override details, see `docs/hooks-setup.md`.

Example `.cursor/hooks/sound-config.json`:

```json
{
  "enabled": true,
  "soundRoot": "sounds",
  "soundPack": "wc3-orc-soundpack",
  "events": {
    "beforeSubmitPrompt": [
      "PeonReady1.wav",
      "PeonWhat2.wav"
    ],
    "afterAgentThought": "PeonWhat3.wav",
    "afterAgentResponse": "PeonYes3.wav",
    "preToolUse": "GruntYes4.wav",
    "postToolUse": "PeonYesAttack3.wav",
    "postToolUseFailure": "PeonWarcry1.wav",
    "stop": "PeonYes4.wav"
  }
}
```

Each event value can be either:
- a single path string, or
- an array of path strings (one is picked randomly each time).

Paths can be absolute or workspace-relative.
If `soundRoot` is set, relative paths resolve from that folder first.
If `soundPack` is set, relative event paths resolve under `soundRoot/<soundPack>/`.

## Platform support

- Windows: supported via PowerShell `MediaPlayer`.
- macOS: supported via `afplay`.
- Linux: supported via `paplay` (preferred) or `aplay` fallback.
- Playback runs as detached background processes to avoid blocking editor workflow.

## Tuning tips

- If it feels too noisy, remove `afterAgentThought` first.
- If tool sounds are too chatty, keep only `postToolUseFailure`.
- Use 2-3 sounds per event for variety; random selection is automatic.
- Keep success and failure sounds distinct so status is obvious.
- Prefer short sounds for `beforeSubmitPrompt` and `preToolUse`.

## Manual test

Run from repo root:

```bash
python .cursor/hooks/play-sound.py --test afterAgentResponse
```
