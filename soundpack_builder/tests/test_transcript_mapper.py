import unittest
from pathlib import Path

from soundpack_builder.transcript_mapper import build_mapping_report, recommend_event_mapping


class TranscriptMapperTest(unittest.TestCase):
    def test_recommendations_use_transcript_signals(self) -> None:
        clips = [
            Path("GokuStop.wav"),
            Path("GokuDone.wav"),
            Path("GokuThink.wav"),
        ]
        transcripts = {
            Path("GokuStop.wav"): "Stop right there.",
            Path("GokuDone.wav"): "All right, done.",
            Path("GokuThink.wav"): "Hmm... let me think.",
        }
        recommendations, _signals = recommend_event_mapping(clips, transcripts=transcripts)
        self.assertIn("stop", recommendations)
        self.assertEqual(recommendations["stop"][0], "GokuStop.wav")
        self.assertEqual(recommendations["postToolUse"][0], "GokuDone.wav")
        self.assertEqual(recommendations["afterAgentThought"][0], "GokuThink.wav")

    def test_recommendations_fallback_to_filename_only(self) -> None:
        clips = [
            Path("PeonReady1.wav"),
            Path("PeonWhat2.wav"),
        ]
        recommendations, _signals = recommend_event_mapping(clips, transcripts={})
        self.assertIn("beforeSubmitPrompt", recommendations)
        self.assertTrue(recommendations["beforeSubmitPrompt"])

    def test_mapping_report_contains_scores(self) -> None:
        clips = [Path("GokuStop.wav"), Path("GokuDone.wav")]
        transcripts = {Path("GokuStop.wav"): "stop", Path("GokuDone.wav"): "done"}
        report = build_mapping_report(clips, transcripts=transcripts)
        self.assertIn("events", report)
        self.assertIn("stop", report["events"])
        self.assertIn("candidates", report["events"]["stop"])
        self.assertTrue(report["events"]["stop"]["candidates"])
        for row in report["events"]["stop"]["candidates"]:
            self.assertIn("rankingTier", row)

    def test_model_score_outweighs_filename_heuristic_in_model_tier(self) -> None:
        """Tier A: higher modelScore ranks above a stronger filename hint (ready)."""
        clips = [Path("ready_clip.wav"), Path("neutral_clip.wav")]
        transcripts = {
            Path("ready_clip.wav"): "some words",
            Path("neutral_clip.wav"): "other words",
        }
        classifier_scores = {
            Path("ready_clip.wav"): {"beforeSubmitPrompt": 0.0},
            Path("neutral_clip.wav"): {"beforeSubmitPrompt": 0.6},
        }
        recommendations, _signals = recommend_event_mapping(
            clips,
            transcripts=transcripts,
            classifier_scores=classifier_scores,
            classifier_weight=5.0,
        )
        self.assertEqual(recommendations["beforeSubmitPrompt"][0], "neutral_clip.wav")

    def test_model_tier_ranked_before_heuristic_fallback(self) -> None:
        """Tier A clips fill `selected` before any Tier B clip, even with weak model scores."""
        clips = [Path("super_ready.wav"), Path("zzz.wav")]
        transcripts = {
            Path("super_ready.wav"): "",
            Path("zzz.wav"): "hello",
        }
        classifier_scores = {
            Path("zzz.wav"): {"beforeSubmitPrompt": 0.01},
        }
        recommendations, _signals = recommend_event_mapping(
            clips,
            transcripts=transcripts,
            classifier_scores=classifier_scores,
            classifier_weight=5.0,
        )
        self.assertEqual(recommendations["beforeSubmitPrompt"][0], "zzz.wav")


if __name__ == "__main__":
    unittest.main()
