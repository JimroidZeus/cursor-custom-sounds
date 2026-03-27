"""Build tier-1 candidate manifest from pre-selected Spriters Resource asset pages."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from .config import BuilderConfig, add_output_path_args, build_config_from_args

EVENT_ORDER = [
    "beforeSubmitPrompt_1.wav",
    "beforeSubmitPrompt_2.wav",
    "afterAgentThought_1.wav",
    "afterAgentThought_2.wav",
    "afterAgentResponse_1.wav",
    "afterAgentResponse_2.wav",
    "preToolUse.wav",
    "postToolUse.wav",
    "postToolUseFailure.wav",
    "stop.wav",
]

TARGET_TO_EVENT = {
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


def entry(
    *,
    universe: str,
    character: str,
    targetFile: str,
    url: str,
    pathInArchive: str,
    source_page: str,
    note: str | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "universe": universe,
        "character": character,
        "targetFile": targetFile,
        "event": TARGET_TO_EVENT.get(targetFile),
        "url": url,
        "pathInArchive": pathInArchive,
        "source_page": source_page,
    }
    if note:
        payload["note"] = note
    return payload


def build() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    warcraft_universe = "warcraft"
    warcraft_character = "orc-peon"
    warcraft_zip = (
        "https://sounds.spriters-resource.com/media/assets/422/425494.zip?updated=1755544622"
    )
    warcraft_page = "https://sounds.spriters-resource.com/pc_computer/warcraft3reignofchaos/asset/425494/"
    warcraft_paths = [
        "Orc/Peon/PeonReady1.wav",
        "Orc/Peon/PeonWhat2.wav",
        "Orc/Peon/PeonWhat3.wav",
        "Orc/Peon/PeonWhat4.wav",
        "Orc/Peon/PeonYes3.wav",
        "Orc/Peon/PeonYes4.wav",
        "Orc/Grunt/GruntYes4.wav",
        "Orc/Peon/PeonYesAttack3.wav",
        "Orc/Peon/PeonWarcry1.wav",
        "Orc/Peon/PeonYes4.wav",
    ]

    for target, p in zip(EVENT_ORDER, warcraft_paths):
        out.append(
            entry(
                universe=warcraft_universe,
                character=warcraft_character,
                targetFile=target,
                url=warcraft_zip,
                pathInArchive=p,
                source_page=warcraft_page,
                note="Picked from filename semantics (Ready/What/Yes/Warcry).",
            )
        )

    tf2_zip_demoman = (
        "https://sounds.spriters-resource.com/media/assets/409/412046.zip?updated=1755538031"
    )
    tf2_page_demoman = "https://sounds.spriters-resource.com/pc_computer/tf2/asset/412046/"
    demoman_paths = [
        "demoman/activatecharge01.mp3",
        "demoman/activatecharge02.mp3",
        "demoman/autocappedintelligence01.mp3",
        "demoman/autocappedintelligence02.mp3",
        "demoman/yes01.mp3",
        "demoman/yes02.mp3",
        "demoman/activatecharge03.mp3",
        "demoman/yes03.mp3",
        "demoman/no01.mp3",
        "demoman/battlecry01.mp3",
    ]
    for target, p in zip(EVENT_ORDER, demoman_paths):
        out.append(
            entry(
                universe="team-fortress-2",
                character="demoman",
                targetFile=target,
                url=tf2_zip_demoman,
                pathInArchive=p,
                source_page=tf2_page_demoman,
                note="Best-effort semantic mapping from TF2 clip name prefixes.",
            )
        )

    tf2_zip_scout = (
        "https://sounds.spriters-resource.com/media/assets/409/412051.zip?updated=1755538033"
    )
    tf2_page_scout = "https://sounds.spriters-resource.com/pc_computer/tf2/asset/412051/"
    scout_paths = [
        "scout/activatecharge01.mp3",
        "scout/activatecharge02.mp3",
        "scout/invinciblenotready01.mp3",
        "scout/invinciblenotready02.mp3",
        "scout/yes01.mp3",
        "scout/yes02.mp3",
        "scout/activatecharge03.mp3",
        "scout/yes03.mp3",
        "scout/no01.mp3",
        "scout/award01.mp3",
    ]
    for target, p in zip(EVENT_ORDER, scout_paths):
        out.append(
            entry(
                universe="team-fortress-2",
                character="scout",
                targetFile=target,
                url=tf2_zip_scout,
                pathInArchive=p,
                source_page=tf2_page_scout,
                note="Best-effort semantic mapping from TF2 clip name prefixes.",
            )
        )

    dbz_goku_zip = (
        "https://sounds.spriters-resource.com/media/assets/422/425476.zip?updated=1755544614"
    )
    dbz_goku_page = "https://sounds.spriters-resource.com/playstation_2/dragonballzbudokaitenkaichi3/asset/425476/"
    goku_paths = [
        "Base form/Main Voice Files/Goku_3(49174).wav",
        "Base form/Main Voice Files/Goku_3(49175).wav",
        "Base form/Main Voice Files/Goku_3(49177).wav",
        "Base form/Main Voice Files/Goku_3(49178).wav",
        "Base form/Main Voice Files/Goku_3(49180).wav",
        "Base form/Main Voice Files/Goku_3(49181).wav",
        "Base form/Main Voice Files/Goku_3(49182).wav",
        "Base form/Main Voice Files/Goku_3(49183).wav",
        "Base form/Main Voice Files/Goku_3(49184).wav",
        "Base form/Main Voice Files/Goku_3(49185).wav",
    ]
    for target, p in zip(EVENT_ORDER, goku_paths):
        out.append(
            entry(
                universe="dragon-ball-z",
                character="goku",
                targetFile=target,
                url=dbz_goku_zip,
                pathInArchive=p,
                source_page=dbz_goku_page,
                note="Best-effort: selected first available Goku voice clips.",
            )
        )

    dbz_krillin_zip = (
        "https://sounds.spriters-resource.com/media/assets/439/442190.zip?updated=1755552420"
    )
    dbz_krillin_page = "https://sounds.spriters-resource.com/psp/dragonballzshinbudokai2/asset/442190/"
    krillin_paths = [
        "Krillin (US)/00Normal/BCKLLSND2_00000.wav",
        "Krillin (US)/00Normal/BCKLLSND_00009.wav",
        "Krillin (US)/00Normal/BCKLLSND_00010.wav",
        "Krillin (US)/00Normal/BCKLLSND_00011.wav",
        "Krillin (US)/00Normal/BCKLLSND_00012.wav",
        "Krillin (US)/00Normal/BCKLLSND_00013.wav",
        "Krillin (US)/00Normal/BCKLLSND_00014.wav",
        "Krillin (US)/00Normal/BCKLLSND_00015.wav",
        "Krillin (US)/00Normal/BCKLLSND_00016.wav",
        "Krillin (US)/00Normal/BCKLLSND_00017.wav",
    ]
    for target, p in zip(EVENT_ORDER, krillin_paths):
        out.append(
            entry(
                universe="dragon-ball-z",
                character="krillin",
                targetFile=target,
                url=dbz_krillin_zip,
                pathInArchive=p,
                source_page=dbz_krillin_page,
                note="Best-effort: selected first available Krillin voice clips.",
            )
        )

    luffy_zip = (
        "https://sounds.spriters-resource.com/media/assets/396/399610.zip?updated=1755530000"
    )
    luffy_page = "https://sounds.spriters-resource.com/playstation_3/jstarsvictoryvs/asset/399610/"
    luffy_paths = [
        "Luffy/cv_000500_jp.wav",
        "Luffy/cv_000501_jp.wav",
        "Luffy/cv_000502_jp.wav",
        "Luffy/cv_000503_jp.wav",
        "Luffy/cv_000504_jp.wav",
        "Luffy/cv_000505_jp.wav",
        "Luffy/cv_000506_jp.wav",
        "Luffy/cv_000507_jp.wav",
        "Luffy/cv_000508_jp.wav",
        "Luffy/cv_000509_jp.wav",
    ]
    for target, p in zip(EVENT_ORDER, luffy_paths):
        out.append(
            entry(
                universe="one-piece",
                character="luffy",
                targetFile=target,
                url=luffy_zip,
                pathInArchive=p,
                source_page=luffy_page,
                note="Best-effort: selected first available Luffy voice clips.",
            )
        )

    bender_zip = (
        "https://sounds.spriters-resource.com/media/assets/511/525333.zip?updated=1772343108"
    )
    bender_page = "https://sounds.spriters-resource.com/xbox/futurama/asset/525333/"
    bender_paths = [
        "Bender Breaks Out/alarmloop.wav",
        "Bender Breaks Out/button_push.wav",
        "Bender Breaks Out/clock_loop.wav",
        "Bender Breaks Out/destalarm.wav",
        "Bender Breaks Out/door-small-close.wav",
        "Bender Breaks Out/door-small-open.wav",
        "Bender Breaks Out/fence-blipp.wav",
        "Bender Breaks Out/gas-fire.wav",
        "Bender Breaks Out/laser-charge.wav",
        "Bender Breaks Out/laser-fence-activate.wav",
    ]
    for target, p in zip(EVENT_ORDER, bender_paths):
        out.append(
            entry(
                universe="futurama",
                character="bender",
                targetFile=target,
                url=bender_zip,
                pathInArchive=p,
                source_page=bender_page,
                note="Best-effort: level SFX mapped into the event slots.",
            )
        )

    krabs_zip = (
        "https://sounds.spriters-resource.com/media/assets/395/398221.zip?updated=1755529389"
    )
    krabs_page = "https://sounds.spriters-resource.com/wii/spongebobstruthorsquare/asset/398221/"
    krabs_paths = [
        "Mr. Krabs/BOOT_nudge_Krabs.wav",
        "Mr. Krabs/CINE_1_KRABS_LINE1.wav",
        "Mr. Krabs/CINE_1_KRABS_LINE2.wav",
        "Mr. Krabs/CINE_1_KRABS_LINE3.wav",
        "Mr. Krabs/CINE_7_KRABS_LINE1.wav",
        "Mr. Krabs/CINE_7_KRABS_LINE2.wav",
        "Mr. Krabs/CINE_7_KRABS_LINE4.wav",
        "Mr. Krabs/CINE_7_KRABS_LINE5.wav",
        "Mr. Krabs/CINE_7_KRABS_LINE6.wav",
        "Mr. Krabs/CINE_PB_SL04_KRABS_LINE1.wav",
    ]
    for target, p in zip(EVENT_ORDER, krabs_paths):
        out.append(
            entry(
                universe="spongebob",
                character="mr-krabs",
                targetFile=target,
                url=krabs_zip,
                pathInArchive=p,
                source_page=krabs_page,
                note="Best-effort: selected early Mr. Krabs voice clips.",
            )
        )

    c3po_zip = (
        "https://sounds.spriters-resource.com/media/assets/418/421698.zip?updated=1755542663"
    )
    c3po_page = "https://sounds.spriters-resource.com/pc_computer/disneyinfinity30/asset/421698/"
    c3po_paths = [
        "C-3PO/THP0101.wav",
        "C-3PO/THP0102.wav",
        "C-3PO/THP0103.wav",
        "C-3PO/THP0104.wav",
        "C-3PO/THP0105.wav",
        "C-3PO/THP0107.wav",
        "C-3PO/THP0108.wav",
        "C-3PO/THP0109.wav",
        "C-3PO/THP0110.wav",
        "C-3PO/THP0111.wav",
    ]
    for target, p in zip(EVENT_ORDER, c3po_paths):
        out.append(
            entry(
                universe="star-wars",
                character="c-3po",
                targetFile=target,
                url=c3po_zip,
                pathInArchive=p,
                source_page=c3po_page,
                note="Best-effort: first 10 C-3PO dialogue clips.",
            )
        )

    genie_zip = (
        "https://sounds.spriters-resource.com/media/assets/509/524134.zip?updated=1771955873"
    )
    genie_page = "https://sounds.spriters-resource.com/pc_computer/disneyspeedstorm/asset/524134/"
    genie_paths = [
        "Genie/1.wav",
        "Genie/2.wav",
        "Genie/3.wav",
        "Genie/5.wav",
        "Genie/6.wav",
        "Genie/7.wav",
        "Genie/8.wav",
        "Genie/9.wav",
        "Genie/12.wav",
        "Genie/13.wav",
    ]
    for target, p in zip(EVENT_ORDER, genie_paths):
        out.append(
            entry(
                universe="disney",
                character="genie",
                targetFile=target,
                url=genie_zip,
                pathInArchive=p,
                source_page=genie_page,
                note="Best-effort: selected first available Genie SFX/clips.",
            )
        )

    return out


def write_candidates(cfg: BuilderConfig, *, out_name: str = "tier1-candidates.json") -> tuple[str, int]:
    candidates = build()
    out_path = cfg.manifests_dir / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"entries": candidates}, indent=2) + "\n", encoding="utf-8")
    return str(out_path), len(candidates)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build tier-1 candidate manifest.")
    add_output_path_args(parser)
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    out, count = write_candidates(cfg)
    print(json.dumps({"ok": True, "count": count, "out": out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
