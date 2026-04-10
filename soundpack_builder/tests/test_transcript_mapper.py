import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from soundpack_builder.audio.transcript_mapper import (
    EVENT_LABEL_DESCRIPTIONS,
    EVENT_ORDER,
    _hook_event_criteria_for_embedding,
    _similarities_to_event_scores,
    _transcript_text_for_embedding_compare,
    build_mapping_report,
    partition_clips_by_speech,
    provisional_classify_progress_note,
    recommend_event_mapping,
    speech_eligibility,
)


class ProvisionalClassifyNoteTest(unittest.TestCase):
    def test_empty_scores_returns_none(self) -> None:
        self.assertIsNone(provisional_classify_progress_note({}))

    def test_argmax_event_in_note(self) -> None:
        scores = {"stop": 0.2, "beforeSubmitPrompt": 0.91}
        note = provisional_classify_progress_note(scores)
        self.assertIsNotNone(note)
        assert note is not None
        self.assertIn("beforeSubmitPrompt", note)
        self.assertIn("0.910", note)


class EmbeddingCompareTextTest(unittest.TestCase):
    def test_transcript_side_contains_utterance(self) -> None:
        t = _transcript_text_for_embedding_compare("  Stop!  ")
        self.assertIn("Stop!", t)

    def test_hook_criteria_includes_event_key_and_description(self) -> None:
        text = _hook_event_criteria_for_embedding("stop")
        self.assertIn("stop", text.lower())
        self.assertIn(EVENT_LABEL_DESCRIPTIONS["stop"], text)


class SimilaritiesToScoresTest(unittest.TestCase):
    def test_maps_cosine_range_to_unit_interval(self) -> None:
        sims = [1.0, 0.0, -1.0] + [0.0] * (len(EVENT_ORDER) - 3)
        scores = _similarities_to_event_scores(sims)
        self.assertAlmostEqual(scores["beforeSubmitPrompt"], 1.0, places=5)
        self.assertAlmostEqual(scores["afterAgentThought"], 0.5, places=5)
        self.assertAlmostEqual(scores["afterAgentResponse"], 0.0, places=5)


class SpeechEligibilityTest(unittest.TestCase):
    def test_empty_and_whitespace(self) -> None:
        self.assertEqual(speech_eligibility(""), (False, "empty"))
        self.assertEqual(speech_eligibility("   "), (False, "empty"))

    def test_pure_bracket_noise(self) -> None:
        self.assertEqual(speech_eligibility("[music]"), (False, "noise_or_music_markers"))
        self.assertEqual(speech_eligibility("[MUSIC] [laughter]"), (False, "noise_or_music_markers"))

    def test_mixed_brackets_and_words(self) -> None:
        ok, reason = speech_eligibility("[music] Hello there")
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_normal_sentence(self) -> None:
        self.assertEqual(speech_eligibility("Objection!"), (True, "ok"))

    def test_non_lexical_punctuation_only(self) -> None:
        self.assertEqual(speech_eligibility("... ---"), (False, "non_lexical_only"))

    def test_partition_clips_by_speech(self) -> None:
        a = Path("a.wav")
        b = Path("b.wav")
        c = Path("c.wav")
        transcripts = {a: "[music]", b: "Say hello", c: ""}
        eligible, excluded = partition_clips_by_speech([a, b, c], transcripts)
        self.assertEqual(eligible, [b])
        self.assertEqual(len(excluded), 2)
        reasons = {row["file"]: row["reason"] for row in excluded}
        self.assertEqual(reasons["a.wav"], "noise_or_music_markers")
        self.assertEqual(reasons["c.wav"], "empty")


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

    def test_mapping_report_speech_verification_and_clips_override(self) -> None:
        clips = [Path("a.wav")]
        report = build_mapping_report(
            clips,
            transcripts={Path("a.wav"): "hi"},
            speech_verification={"mode": "whisper", "filter": "applied"},
            clips_override=[{"file": "a.wav", "transcript": "hi", "speechEligible": True}],
        )
        self.assertEqual(report["speechVerification"]["mode"], "whisper")
        self.assertEqual(report["clips"][0]["speechEligible"], True)

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

    def test_unique_clip_per_slot_when_ten_clips(self) -> None:
        clips = [Path(f"clip{i}.wav") for i in range(10)]
        transcripts = {Path(f"clip{i}.wav"): f"phrase number {i}" for i in range(10)}
        recommendations, _signals = recommend_event_mapping(clips, transcripts=transcripts)
        flat = [fn for _ev, names in recommendations.items() for fn in names]
        self.assertEqual(len(flat), 10)
        self.assertEqual(len(flat), len(set(flat)))

    def test_model_tier_ranked_before_heuristic_fallback(self) -> None:
        """Tier A clip is preferred for beforeSubmitPrompt over filename-only Tier B."""
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
        self.assertIn("zzz.wav", recommendations["beforeSubmitPrompt"])


class PartitionTranscriptionWorkTest(unittest.TestCase):
    def test_resume_false_returns_all_pending(self) -> None:
        from soundpack_builder.audio.transcript_mapper import partition_transcription_work

        with tempfile.TemporaryDirectory() as td:
            pack = Path(td)
            a = pack / "a.wav"
            b = pack / "b.wav"
            pending, pre = partition_transcription_work([a, b], pack, resume=False)
            self.assertEqual(pending, [a, b])
            self.assertEqual(pre, {})

    def test_resume_loads_existing_into_preloaded(self) -> None:
        from soundpack_builder.audio.transcript_mapper import (
            partition_transcription_work,
            save_transcripts_sidecar,
        )

        with tempfile.TemporaryDirectory() as td:
            pack = Path(td)
            a = pack / "a.wav"
            b = pack / "b.wav"
            a.write_text("x")
            b.write_text("y")
            save_transcripts_sidecar(pack, {a: "hello"})
            pending, pre = partition_transcription_work([a, b], pack, resume=True)
            self.assertEqual(pending, [b])
            self.assertEqual(pre.get(a), "hello")


class SaveTranscriptsSidecarTest(unittest.TestCase):
    def test_atomic_write_produces_valid_json(self) -> None:
        from soundpack_builder.audio.transcript_mapper import (
            TRANSCRIPTS_JSON_NAME,
            save_transcripts_sidecar,
        )

        with tempfile.TemporaryDirectory() as td:
            pack = Path(td)
            p = pack / "x.wav"
            save_transcripts_sidecar(pack, {p: "hi"})
            path = pack / TRANSCRIPTS_JSON_NAME
            self.assertTrue(path.is_file())
            self.assertFalse((pack / (TRANSCRIPTS_JSON_NAME + ".tmp")).exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["clips"]["x.wav"], "hi")


class ZeroShotPremiseSanitizeTest(unittest.TestCase):
    def test_empty_and_zwsp_only_skipped(self) -> None:
        class Tok:
            def encode(self, t: str, add_special_tokens: bool = False, truncation: bool = False):
                return [1] if t else []

        from soundpack_builder.audio.transcript_mapper import _zero_shot_safe_premise

        tok = Tok()
        self.assertIsNone(_zero_shot_safe_premise(tok, "   "))
        self.assertIsNone(_zero_shot_safe_premise(tok, "\u200b\u200b"))

    def test_nonempty_premise_preserved(self) -> None:
        class Tok:
            def encode(self, t: str, add_special_tokens: bool = False, truncation: bool = False):
                return [1, 2, 3]

        from soundpack_builder.audio.transcript_mapper import _zero_shot_safe_premise

        self.assertEqual(_zero_shot_safe_premise(Tok(), "  hello  "), "hello")


class DefaultClassifierBackendTest(unittest.TestCase):
    @patch("soundpack_builder.audio.transcript_mapper.sys.platform", "linux")
    @patch("soundpack_builder.audio.transcript_mapper.classifier_runs_on_cpu", return_value=True)
    def test_non_windows_uses_zero_shot_even_on_cpu(self, _m: object) -> None:
        from soundpack_builder.audio.transcript_mapper import default_classifier_backend_for_environment

        self.assertEqual(default_classifier_backend_for_environment("cpu"), "zero-shot")

    @patch("soundpack_builder.audio.transcript_mapper.sys.platform", "win32")
    @patch("soundpack_builder.audio.transcript_mapper.classifier_runs_on_cpu", return_value=True)
    def test_windows_cpu_uses_sentence_embedding(self, _m: object) -> None:
        from soundpack_builder.audio.transcript_mapper import default_classifier_backend_for_environment

        self.assertEqual(default_classifier_backend_for_environment("cpu"), "sentence-embedding")

    @patch("soundpack_builder.audio.transcript_mapper.sys.platform", "win32")
    @patch("soundpack_builder.audio.transcript_mapper.classifier_runs_on_cpu", return_value=False)
    def test_windows_cuda_prefers_zero_shot(self, _m: object) -> None:
        from soundpack_builder.audio.transcript_mapper import default_classifier_backend_for_environment

        self.assertEqual(default_classifier_backend_for_environment("cuda:0"), "zero-shot")


class DefaultZeroShotModelTest(unittest.TestCase):
    def test_cpu_explicit_uses_distilbert_mnli(self) -> None:
        from soundpack_builder.audio.transcript_mapper import (
            DEFAULT_ZERO_SHOT_MODEL_CPU,
            default_zero_shot_model_for_classifier_device,
        )

        self.assertEqual(
            default_zero_shot_model_for_classifier_device("cpu"),
            DEFAULT_ZERO_SHOT_MODEL_CPU,
        )

    @patch("soundpack_builder.audio.transcript_mapper.classifier_runs_on_cpu", return_value=True)
    def test_when_classifier_runs_on_cpu_uses_distilbert(self, _mock: object) -> None:
        from soundpack_builder.audio.transcript_mapper import (
            DEFAULT_ZERO_SHOT_MODEL_CPU,
            default_zero_shot_model_for_classifier_device,
        )

        self.assertEqual(
            default_zero_shot_model_for_classifier_device("auto"),
            DEFAULT_ZERO_SHOT_MODEL_CPU,
        )

    @patch("soundpack_builder.audio.transcript_mapper.classifier_runs_on_cpu", return_value=False)
    def test_when_classifier_runs_on_gpu_uses_distilbart(self, _mock: object) -> None:
        from soundpack_builder.audio.transcript_mapper import (
            DEFAULT_ZERO_SHOT_MODEL,
            default_zero_shot_model_for_classifier_device,
        )

        self.assertEqual(
            default_zero_shot_model_for_classifier_device("auto"),
            DEFAULT_ZERO_SHOT_MODEL,
        )


if __name__ == "__main__":
    unittest.main()
