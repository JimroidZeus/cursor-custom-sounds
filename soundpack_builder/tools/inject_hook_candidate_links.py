"""Optional advanced helper: merge curated URL blocks into universe-character-hook-candidates.json.

Not part of the default pipeline (prefer hand-editing + ``search_hints`` / ``candidates``).

Run from repo root:
  python -m soundpack_builder.tools.inject_hook_candidate_links
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# (universe, character) -> hook name -> list of link objects
MERGE: Dict[Tuple[str, str], Dict[str, List[Dict[str, Any]]]] = {
    ("star-trek", "jean-luc-picard"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://freesound.org/s/243601/",
                "siteId": "freesound",
                "label": "miked312 — Borg Voices (Star Trek franchise VO pack; not “make it so”)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/search/?q=picard+make+it+so",
                "siteId": "freesound",
                "label": "Freesound search (text): picard make it so",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("lord-of-the-rings", "gandalf"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://freesound.org/s/181221/",
                "siteId": "freesound",
                "label": "unfa — You Shall Not Pass (multi-voice line read)",
                "matchQuality": "paraphrase_quote",
            },
            {
                "url": "https://freesound.org/s/402072/",
                "siteId": "freesound",
                "label": "chestnutjam — “you shall not pass” ORC voice (LOTR-tagged)",
                "matchQuality": "paraphrase_quote",
            },
            {
                "url": "https://freesound.org/browse/tags/gandalf/",
                "siteId": "freesound",
                "label": "Freesound tag browse: gandalf",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("harry-potter", "spell-incantations"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://freesound.org/people/joe93barlow/packs/6726/",
                "siteId": "freesound",
                "label": "Pack: Harry Potter Spells (pick individual clips from pack listing)",
                "matchQuality": "thematic_pack",
            },
            {
                "url": "https://freesound.org/people/Pablobd/packs/29260/",
                "siteId": "freesound",
                "label": "Pack: Harry Potter (magic spell / wand SFX)",
                "matchQuality": "thematic_pack",
            },
            {
                "url": "https://freesound.org/browse/tags/Harry-Potter/",
                "siteId": "freesound",
                "label": "Tag: Harry-Potter",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("one-piece", "luffy"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://sounds.spriters-resource.com/playstation_3/jstarsvictoryvs/asset/399610/",
                "siteId": "spriters-resource-sounds",
                "label": "J-Stars Victory VS — Luffy VO asset page (ZIP on page; same source as archive_entries)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://sounds.spriters-resource.com/media/assets/396/399610.zip?updated=1755530000",
                "siteId": "spriters-resource-sounds",
                "label": "Direct ZIP (from archive_entries) — verify license",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/search/?q=one+piece+luffy",
                "siteId": "freesound",
                "label": "Freesound search: one piece luffy",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("dragon-ball", "goku"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://sounds.spriters-resource.com/playstation_2/dragonballzbudokaitenkaichi3/asset/425476/",
                "siteId": "spriters-resource-sounds",
                "label": "DBZ Budokai Tenkaichi 3 — Goku VO page (game-archive manifest)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://sounds.spriters-resource.com/media/assets/422/425476.zip?updated=1755544614",
                "siteId": "spriters-resource-sounds",
                "label": "Direct ZIP (archive_entries)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/s/168908/",
                "siteId": "freesound",
                "label": "erickjohanzm — DBZ saiyan aura + kamehameha (long; NC license on page)",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/649661/",
                "siteId": "freesound",
                "label": "potato_on_bacon — short Goku drip-style tagged DBZ",
                "matchQuality": "franchise_adjacent",
            },
        ]
    },
    ("marvel", "captain-america"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://freesound.org/s/342603/",
                "siteId": "freesound",
                "label": "oscaraudiogeek — “shield-like” metallic ring (film-inspired SFX, not a spoken line)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/browse/tags/avengers/",
                "siteId": "freesound",
                "label": "Tag: avengers",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=captain+america+all+day",
                "siteId": "freesound",
                "label": "Freesound search: captain america all day",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("portal", "glados"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/portal2/asset/395531/",
                "siteId": "spriters-resource-sounds",
                "label": "Portal 2 — GLaDOS asset bundle page (download from site)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/s/718337/",
                "siteId": "freesound",
                "label": "moodyfingers — GLaDOS (Snare) synthesized voice snippet (Portal-tagged)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/search/?q=cake+is+a+lie+glados",
                "siteId": "freesound",
                "label": "Freesound search: cake is a lie glados",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://www.nexusmods.com/portal2/mods/",
                "siteId": "nexus-mods",
                "label": "Nexus — Portal 2 mods (search voice / audio)",
                "matchQuality": "search_portal",
            },
        ],
        "postToolUseFailure": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/portal2/asset/395531/",
                "siteId": "spriters-resource-sounds",
                "label": "Portal 2 GLaDOS lines (pick failure / sarcastic clip from bundle)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/s/718337/",
                "siteId": "freesound",
                "label": "GLaDOS-ish synthesized snippet (not “triumph” line)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/search/?q=glados+triumph+portal",
                "siteId": "freesound",
                "label": "Freesound search: glados triumph portal",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://www.nexusmods.com/portal2/mods/",
                "siteId": "nexus-mods",
                "label": "Nexus — Portal 2 mods hub (search GLaDOS / VO)",
                "matchQuality": "search_portal",
            },
        ],
    },
    ("mass-effect", "commander-shepard"): {
        "beforeSubmitPrompt": [
            {
                "url": "https://freesound.org/s/345870/",
                "siteId": "freesound",
                "label": "cylon8472 — Reaper voice effect (Mass Effect–inspired)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/s/248261/",
                "siteId": "freesound",
                "label": "cylon8472 — Reaper voice impression",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/browse/tags/Mass-Effect/",
                "siteId": "freesound",
                "label": "Tag: Mass-Effect",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=shepard+i+should+go",
                "siteId": "freesound",
                "label": "Freesound search: shepard i should go",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://www.nexusmods.com/masseffectlegendaryedition/mods/",
                "siteId": "nexus-mods",
                "label": "Nexus — Mass Effect LE mods (search audio / voice)",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("sherlock-holmes", "sherlock"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/s/25481/",
                "siteId": "freesound",
                "label": "FreqMan — violin minuet for Sherlock play (not a spoken “elementary”)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/browse/tags/detective/",
                "siteId": "freesound",
                "label": "Tag: detective",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=sherlock+elementary",
                "siteId": "freesound",
                "label": "Freesound search: sherlock elementary",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("star-trek", "spock"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/s/635160/",
                "siteId": "freesound",
                "label": "Timbre — UberDuck Leonard Nimoy replicated (synthetic; check license/ethics)",
                "matchQuality": "synthetic_voice",
            },
            {
                "url": "https://freesound.org/s/670637/",
                "siteId": "freesound",
                "label": "Timbre — UberDuck Spock deepfake cleaned",
                "matchQuality": "synthetic_voice",
            },
            {
                "url": "https://freesound.org/s/846331/",
                "siteId": "freesound",
                "label": "Iceofdoom — fascinated male reaction (“whoah, no way”)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("watchmen", "rorschach"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/s/388208/",
                "siteId": "freesound",
                "label": "nioczkus — 1911 Comedian Pistol (Watchmen Comedian weapon SFX)",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/830480/",
                "siteId": "freesound",
                "label": "Ultra-Edward — ominous ticking (Watchmen-tagged on site)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/search/?q=rorschach",
                "siteId": "freesound",
                "label": "Freesound search: rorschach",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("hitchhikers-guide", "marvin"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/search/?q=depressed+robot+voice",
                "siteId": "freesound",
                "label": "Freesound search: depressed robot voice",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=marvin+hitchhiker",
                "siteId": "freesound",
                "label": "Freesound search: marvin hitchhiker",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("batman", "batman-animated"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/s/205936/",
                "siteId": "freesound",
                "label": "pikachu09 — “I'm Batman” impression (gravelly)",
                "matchQuality": "paraphrase_quote",
            },
            {
                "url": "https://freesound.org/s/334058/",
                "siteId": "freesound",
                "label": "randomP_J_G — Bane line (gravelly DC)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("doctor-who", "the-doctor"): {
        "afterAgentThought": [
            {
                "url": "https://freesound.org/s/186675/",
                "siteId": "freesound",
                "label": "Dimi194 — TARDIS-like noise",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/582329/",
                "siteId": "freesound",
                "label": "EvanSki — tardis_noise",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/browse/tags/dr-who/",
                "siteId": "freesound",
                "label": "Tag: dr-who",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=allons+y+doctor+who",
                "siteId": "freesound",
                "label": "Freesound search: allons y doctor who",
                "matchQuality": "search_portal",
            },
        ],
        "stop": [
            {
                "url": "https://freesound.org/browse/tags/dr-who/",
                "siteId": "freesound",
                "label": "Tag: dr-who (browse for farewell / run lines)",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=doctor+who+run",
                "siteId": "freesound",
                "label": "Freesound search: doctor who run",
                "matchQuality": "search_portal",
            },
        ],
    },
    ("marvel", "tony-stark"): {
        "afterAgentResponse": [
            {
                "url": "https://freesound.org/s/749816/",
                "siteId": "freesound",
                "label": "drvgcvltvre — Black Sabbath “Iron Man” intro vocoder (song, not MCU Tony)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/s/759715/",
                "siteId": "freesound",
                "label": "Artninja — MCU-inspired Iron Man chest attach SFX",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/browse/tags/iron-man/",
                "siteId": "freesound",
                "label": "Tag: iron-man",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("ace-attorney", "phoenix-wright"): {
        "afterAgentResponse": [
            {
                "url": "https://freesound.org/s/351809/",
                "siteId": "freesound",
                "label": "plasterbrain — Press Start Phoenix Wright (music sting)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/s/580684/",
                "siteId": "freesound",
                "label": "GamingWithJumbo — edgeworth desk slam SFX",
                "matchQuality": "game_sfx",
            },
            {
                "url": "https://freesound.org/s/580683/",
                "siteId": "freesound",
                "label": "GamingWithJumbo — witness testimony clip",
                "matchQuality": "game_voice",
            },
            {
                "url": "https://freesound.org/s/364835/",
                "siteId": "freesound",
                "label": "KenRT — Table slam (courtroom bang substitute)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/people/pfranzen/",
                "siteId": "freesound",
                "label": "pfranzen profile — includes “Banging a table (Phoenix Wright style)” (open profile, pick sound)",
                "matchQuality": "game_sfx",
            },
        ]
    },
    ("monty-python", "holy-grail-narrator-knight"): {
        "afterAgentResponse": [
            {
                "url": "https://freesound.org/s/696511/",
                "siteId": "freesound",
                "label": "mythmade — Much Rejoicing.wav (Monty Python–tagged crowd “yay”)",
                "matchQuality": "paraphrase_quote",
            },
        ]
    },
    ("star-wars", "obi-wan"): {
        "afterAgentResponse": [
            {
                "url": "https://freesound.org/people/s4568769/",
                "siteId": "freesound",
                "label": "s4568769 profile — clip titled Hello There / General Kenobi (verify content + license)",
                "matchQuality": "paraphrase_quote",
            },
            {
                "url": "https://freesound.org/browse/tags/Kenobi/",
                "siteId": "freesound",
                "label": "Tag: Kenobi",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/s/50780/",
                "siteId": "freesound",
                "label": "smcameron — hello.ogg (generic, weak)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("futurama", "bender"): {
        "afterAgentResponse": [
            {
                "url": "https://sounds.spriters-resource.com/xbox/futurama/asset/525333/",
                "siteId": "spriters-resource-sounds",
                "label": "Futurama (Xbox) asset page — mostly level SFX; game-archive manifest uses this ZIP",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://sounds.spriters-resource.com/media/assets/511/525333.zip?updated=1772343108",
                "siteId": "spriters-resource-sounds",
                "label": "Direct ZIP (archive_entries)",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/search/?q=bender+futurama",
                "siteId": "freesound",
                "label": "Freesound search: bender futurama",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("team-fortress-2", "engineer"): {
        "preToolUse": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/tf2/asset/412047/",
                "siteId": "spriters-resource-sounds",
                "label": "TF2 Engineer full VO archive page",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/s/245604/",
                "siteId": "freesound",
                "label": "unfa — TF2 Demoman “Ka-Boom!” (wrong class; proves Freesound has TF2 vo)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://www.nexusmods.com/teamfortress2/mods/",
                "siteId": "nexus-mods",
                "label": "Nexus — TF2 mods (search engineer / VO)",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("star-trek", "scotty"): {
        "preToolUse": [
            {
                "url": "https://freesound.org/search/?q=scotty+star+trek+all+she+got",
                "siteId": "freesound",
                "label": "Freesound search: scotty star trek all she got",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/browse/tags/Star-Trek/",
                "siteId": "freesound",
                "label": "Tag: Star-Trek (if present)",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("ghostbusters", "venkman-team"): {
        "preToolUse": [
            {
                "url": "https://freesound.org/s/478849/",
                "siteId": "freesound",
                "label": "JadeJohnsonIndustries — Ghost Busters.wav (C64-style shout)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/s/98524/",
                "siteId": "freesound",
                "label": "xXlegendXx — Ecto-1 siren long",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/98530/",
                "siteId": "freesound",
                "label": "xXlegendXx — ecto 1 siren short wav",
                "matchQuality": "franchise_sfx",
            },
        ]
    },
    ("warcraft", "orc-peon"): {
        "preToolUse": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/warcraft3reignofchaos/asset/425494/",
                "siteId": "spriters-resource-sounds",
                "label": "WC3 voices bundle (Peon + others) — archive_entries page",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://sounds.spriters-resource.com/media/assets/422/425494.zip?updated=1755544622",
                "siteId": "spriters-resource-sounds",
                "label": "Direct ZIP (archive_entries)",
                "matchQuality": "game_archive",
            },
        ],
        "postToolUseFailure": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/warcraft3reignofchaos/asset/425494/",
                "siteId": "spriters-resource-sounds",
                "label": "Same bundle — pick PeonPissed / PeonDeath / error barks",
                "matchQuality": "game_archive",
            },
        ],
    },
    ("james-bond", "bond"): {
        "preToolUse": [
            {
                "url": "https://freesound.org/s/464142/",
                "siteId": "freesound",
                "label": "TheRealAmandaStone — shakennotstirred.wav (drink shake, not spoken line)",
                "matchQuality": "thematic_sfx",
            },
            {
                "url": "https://freesound.org/s/71415/",
                "siteId": "freesound",
                "label": "philberts — martini_shake_pour.wav",
                "matchQuality": "thematic_sfx",
            },
        ]
    },
    ("the-a-team", "hannibal"): {
        "preToolUse": [
            {
                "url": "https://freesound.org/search/?q=a+team+plan+comes+together",
                "siteId": "freesound",
                "label": "Freesound search: a team plan comes together",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://pixabay.com/sound-effects/search/military%20radio/",
                "siteId": "pixabay",
                "label": "Pixabay: military radio SFX (tone substitute for Hannibal ops chatter)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("star-wars", "han-solo"): {
        "postToolUse": [
            {
                "url": "https://freesound.org/browse/tags/star-wars/",
                "siteId": "freesound",
                "label": "Tag: star-wars (109+ clips — browse)",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/s/466867/",
                "siteId": "freesound",
                "label": "MikeE63 — blaster shot (franchise SFX, not Han’s voice)",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/search/?q=han+solo+great+kid",
                "siteId": "freesound",
                "label": "Freesound search: han solo great kid",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("toy-story", "buzz-lightyear"): {
        "postToolUse": [
            {
                "url": "https://freesound.org/search/?q=infinity+and+beyond",
                "siteId": "freesound",
                "label": "Freesound search: infinity and beyond",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://pixabay.com/sound-effects/search/hooray/",
                "siteId": "pixabay",
                "label": "Pixabay search: hooray (kids cheer substitute)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("portal", "wheatley"): {
        "postToolUse": [
            {
                "url": "https://sounds.spriters-resource.com/pc_computer/portal2/asset/395527/",
                "siteId": "spriters-resource-sounds",
                "label": "Portal 2 Wheatley VO archive page",
                "matchQuality": "game_archive",
            },
            {
                "url": "https://freesound.org/s/648147/",
                "siteId": "freesound",
                "label": "EpicAllay — “That was easy” staples-style button (not Wheatley)",
                "matchQuality": "weak_substitute",
            },
        ]
    },
    ("mario", "mario"): {
        "postToolUse": [
            {
                "url": "https://freesound.org/s/448256/",
                "siteId": "freesound",
                "label": "awhhhyeah — Mario.mp3 (Mario-tagged SFX / voice)",
                "matchQuality": "franchise_adjacent",
            },
            {
                "url": "https://freesound.org/s/362328/",
                "siteId": "freesound",
                "label": "Jofae — Platform Jump (Mario-tagged)",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://opengameart.org/content/level-up-power-up-coin-get-13-sounds",
                "siteId": "opengameart",
                "label": "OpenGameArt — coin / level-up pack (CC0)",
                "matchQuality": "thematic_sfx",
            },
            {
                "url": "https://pixabay.com/sound-effects/search/success/",
                "siteId": "pixabay",
                "label": "Pixabay search: success",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("lord-of-the-rings", "sam-frodo"): {
        "postToolUse": [
            {
                "url": "https://freesound.org/search/?q=well+i%27m+back+sam",
                "siteId": "freesound",
                "label": "Freesound search: well i'm back sam",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/browse/tags/LOTR/",
                "siteId": "freesound",
                "label": "Tag browse: LOTR (if indexed)",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("star-wars", "c3po"): {
        "postToolUseFailure": [
            {
                "url": "https://freesound.org/browse/tags/C-3PO/",
                "siteId": "freesound",
                "label": "Tag: C-3PO (robot servo sounds; may not be “we’re doomed”)",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/s/506722/",
                "siteId": "freesound",
                "label": "PitchyWobble — dying droid by Tony (generic droid fail)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/search/?q=c3po+doomed",
                "siteId": "freesound",
                "label": "Freesound search: c3po doomed",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("simpsons", "homer"): {
        "postToolUseFailure": [
            {
                "url": "https://freesound.org/s/828385/",
                "siteId": "freesound",
                "label": "riippumattog — D'oh (unhappy sound) — not official cast",
                "matchQuality": "paraphrase_quote",
            },
            {
                "url": "https://freesound.org/browse/tags/Simpsons/",
                "siteId": "freesound",
                "label": "Tag: Simpsons",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("dark-souls", "solaire"): {
        "postToolUseFailure": [
            {
                "url": "https://freesound.org/search/?q=praise+the+sun",
                "siteId": "freesound",
                "label": "Freesound search: praise the sun",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=dark+souls+you+died",
                "siteId": "freesound",
                "label": "Freesound search: dark souls you died",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("metal-gear", "snake"): {
        "postToolUseFailure": [
            {
                "url": "https://freesound.org/s/531750/",
                "siteId": "freesound",
                "label": "PixelProphecy — MGS guard alert exclamation",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/413641/",
                "siteId": "freesound",
                "label": "djlprojects — MGS-inspired alert surprise",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/s/493941/",
                "siteId": "freesound",
                "label": "jozef_sound — Metal Gear Solid Alarm",
                "matchQuality": "franchise_sfx",
            },
        ]
    },
    ("terminator", "t800"): {
        "stop": [
            {
                "url": "https://freesound.org/s/431605/",
                "siteId": "freesound",
                "label": "owly-bee — I'm Baaaack! (female singsong; not Arnold)",
                "matchQuality": "weak_substitute",
            },
            {
                "url": "https://freesound.org/s/157969/",
                "siteId": "freesound",
                "label": "jobro — Terminator slam (T2 truck sting, no dialogue)",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/search/?q=ill+be+back+terminator",
                "siteId": "freesound",
                "label": "Freesound search: ill be back terminator",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("the-princess-bride", "inigo-vizzini"): {
        "stop": [
            {
                "url": "https://freesound.org/search/?q=inconceivable",
                "siteId": "freesound",
                "label": "Freesound search: inconceivable",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/search/?q=princess+bride",
                "siteId": "freesound",
                "label": "Freesound search: princess bride",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("looney-tunes", "porky-pig"): {
        "stop": [
            {
                "url": "https://freesound.org/search/?q=that%27s+all+folks",
                "siteId": "freesound",
                "label": "Freesound search: that's all folks",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/browse/tags/cartoon/",
                "siteId": "freesound",
                "label": "Tag: cartoon — browse for classic-era outros",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("marvel", "loki"): {
        "stop": [
            {
                "url": "https://freesound.org/search/?q=loki+avengers+falling",
                "siteId": "freesound",
                "label": "Freesound search: loki avengers falling",
                "matchQuality": "search_portal",
            },
        ]
    },
    ("halo", "cortana"): {
        "stop": [
            {
                "url": "https://freesound.org/browse/tags/Halo/",
                "siteId": "freesound",
                "label": "Tag: Halo — shield / UI SFX (not Cortana VO)",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://freesound.org/s/501750/",
                "siteId": "freesound",
                "label": "Pablobd — Halo-style sci-fi shield wav",
                "matchQuality": "franchise_sfx",
            },
            {
                "url": "https://freesound.org/search/?q=cortana+halo+voice",
                "siteId": "freesound",
                "label": "Freesound search: cortana halo voice",
                "matchQuality": "search_portal",
            },
            {
                "url": "https://www.nexusmods.com/halothemasterchiefcollection/mods/",
                "siteId": "nexus-mods",
                "label": "Nexus — Halo MCC mods (search audio / Cortana)",
                "matchQuality": "search_portal",
            },
        ]
    },
}

CROSS_MERGE: Dict[Tuple[str, str], List[Dict[str, Any]]] = {
    ("team-fortress-2", "_nine-classes-overview"): [
        {
            "url": "https://sounds.spriters-resource.com/pc_computer/tf2/",
            "siteId": "spriters-resource-sounds",
            "label": "TF2 master list — all class VO bundles",
            "matchQuality": "game_archive",
        },
        {
            "url": "https://sounds.spriters-resource.com/pc_computer/tf2/asset/412046/",
            "siteId": "spriters-resource-sounds",
            "label": "Demoman archive (game-archive manifest)",
            "matchQuality": "game_archive",
        },
        {
            "url": "https://sounds.spriters-resource.com/pc_computer/tf2/asset/412047/",
            "siteId": "spriters-resource-sounds",
            "label": "Engineer archive",
            "matchQuality": "game_archive",
        },
    ],
    ("warcraft", "_orc-unit-set"): [
        {
            "url": "https://sounds.spriters-resource.com/pc_computer/warcraft3reignofchaos/asset/425494/",
            "siteId": "spriters-resource-sounds",
            "label": "WC3 voices (orc peon + other units)",
            "matchQuality": "game_archive",
        },
    ],
    ("one-piece", "_straw-hat-crew"): [
        {
            "url": "https://sounds.spriters-resource.com/playstation_3/jstarsvictoryvs/asset/399610/",
            "siteId": "spriters-resource-sounds",
            "label": "J-Stars — Luffy bundle (other crew may need different game assets)",
            "matchQuality": "game_archive",
        },
        {
            "url": "https://freesound.org/search/?q=one+piece+zoro",
            "siteId": "freesound",
            "label": "Freesound search: one piece zoro",
            "matchQuality": "search_portal",
        },
    ],
    ("ace-attorney", "_courtroom-kit"): [
        {
            "url": "https://freesound.org/s/580683/",
            "siteId": "freesound",
            "label": "Ace Attorney witness testimony",
            "matchQuality": "game_voice",
        },
        {
            "url": "https://freesound.org/s/580684/",
            "siteId": "freesound",
            "label": "Ace Attorney desk slam",
            "matchQuality": "game_sfx",
        },
    ],
}


def main() -> None:
    # tools/inject_hook_candidate_links.py -> soundpack_builder -> repo root
    root = Path(__file__).resolve().parents[2]
    path = root / "manifests" / "universe-character-hook-candidates.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["description"] = (
        "schemaVersion 3 discovery manifest: flat candidateLinks per character; optional discoveryHints; "
        "site ids in manifests/sound-sites.json. "
        "Verify license and copyright before download. matchQuality explains clip fit."
    )

    for ch in data.get("characters", []):
        key = (ch["universe"], ch["character"])
        patch = MERGE.get(key)
        if not patch:
            continue
        merged = list(ch.get("candidateLinks") or [])
        for _ev_name, links in patch.items():
            merged.extend(links)
        ch["candidateLinks"] = merged

    for pack in data.get("crossFranchiseOneVoicePacks", []):
        ck = CROSS_MERGE.get((pack.get("universe", ""), pack.get("character", "")))
        if ck:
            pack["candidateLinks"] = ck

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
