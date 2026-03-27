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

## Sound configuration

Edit `.cursor/hooks/sound-config.json`:

- `enabled`: toggle all sound playback
- `soundRoot`: base path for relative sound files
- `soundPack`: optional pack folder under `soundRoot` (for example `wc3-orc-soundpack`)
- `events.<hookEvent>`: either a single file path string or an array for random selection

Relative paths resolve from `soundRoot/soundPack` first (when `soundPack` is set), then from `soundRoot`, then project root fallback.

## Global user override (all projects)

You can override defaults with:

- `~/.cursor/sound-hooks.json`

The hook runner merges user config over project config.

Example `~/.cursor/sound-hooks.json`:

```json
{
  "enabled": true,
  "soundRoot": "C:/Users/JimroidZeus/source/repos/cursor-custom-sounds/sounds",
  "soundPack": "wc3-orc-soundpack",
  "events": {
    "afterAgentResponse": [
      "PeonYes3.wav",
      "PeonYes4.wav"
    ],
    "postToolUseFailure": "PeonWarcry1.wav"
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
