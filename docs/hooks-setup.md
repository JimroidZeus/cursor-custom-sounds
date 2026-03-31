# Cursor hooks sound setup

This project uses Cursor's official Hooks system to play sounds for agent lifecycle events.

## Project-level setup

Project hooks are already configured in:

- `.cursor/hooks.json`
- `.cursor/hooks/play-sound.py`
- `.cursor/hooks/sound-config.json`

When this repo is opened in Cursor, these hooks run for the configured events.

## Events currently wired

- `beforeSubmitPrompt`
- `afterAgentThought`
- `afterAgentResponse`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`
- `stop`

## What each event means

- `beforeSubmitPrompt`: runs when you submit a prompt in chat.
- `afterAgentThought`: runs after an internal reasoning/thought step.
- `afterAgentResponse`: runs when the agent posts a response.
- `preToolUse`: runs immediately before a tool call.
- `postToolUse`: runs after a successful tool call.
- `postToolUseFailure`: runs after a failed tool call.
- `stop`: runs when generation is interrupted/stopped.

## Sound configuration

Edit `.cursor/hooks/sound-config.json`:

- `enabled`: toggle all sound playback
- `debounceMs`: per-event duplicate suppression window in milliseconds (for example `500`)
- `soundRoot`: base path for relative sound files
- `soundPack`: optional pack folder under `soundRoot` (for example `wc3-orc-soundpack`)
- `soundSubdir`: optional character folder under `soundPack` (for example `orc-peon`)
- `events.<hookEvent>`: either a single file path string or an array for random selection

Relative paths resolve from `soundRoot/soundPack` first (when `soundPack` is set), then from `soundRoot`, then project root fallback.
If `soundSubdir` is set and an event entry is just a filename (no slash), it resolves from `soundRoot/soundPack/soundSubdir/`.

## Global user override (all projects)

You can override defaults with:

- `~/.cursor/sound-hooks.json`

The hook runner merges user config over project config.

Example `~/.cursor/sound-hooks.json`:

```json
{
  "enabled": true,
  "debounceMs": 500,
  "soundRoot": "C:/Users/JimroidZeus/source/repos/cursor-custom-sounds/sounds",
  "soundPack": "warcraft",
  "soundSubdir": "orc-peon",
  "events": {
    "afterAgentResponse": [
      "afterAgentResponse_1.wav",
      "afterAgentResponse_2.wav"
    ],
    "postToolUseFailure": "postToolUseFailure.wav"
  }
}
```

## Optional global hook registration

If you want this behavior in other projects without copying files, add a user hooks file at `~/.cursor/hooks.json` that invokes your preferred script path.

Example:

```json
{
  "version": 1,
  "hooks": {
    "afterAgentResponse": [
      {
        "command": "python C:/Users/JimroidZeus/source/repos/cursor-custom-sounds/.cursor/hooks/play-sound.py afterAgentResponse"
      }
    ]
  }
}
```

## Quick test

Run from this repo:

```bash
python .cursor/hooks/play-sound.py --test afterAgentResponse
```

If the script runs, it prints a JSON status object and should play a sound in the background.

## See also

- **Building or swapping soundpacks** (manifests, downloader, templates): [`sound-sourcing.md`](sound-sourcing.md), the repo root **README** section *Manifest workflow*, and [`soundpack_builder/README.md`](../soundpack_builder/README.md) (CLI flags, `sourcing-config` fetch options, **`freesound_resolve`**, transcript mapping).
