"""Focused tests for bounded pre-decode audio inspection.

These tests intentionally use inert metadata and decoder doubles so they do not
need a native codec, PyTorch, or a real untrusted media file.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


SOURCE_ROOT = Path(__file__).resolve().parents[3]
LIMITS_PATH = Path(__file__).with_name("audio_input_limits.py")
IO_PATH = Path(__file__).with_name("io_audio.py")
UI_VALIDATION_PATH = (
    SOURCE_ROOT / "ui" / "gradio" / "events" / "generation" / "validation.py"
)
PIPELINE_PATH = SOURCE_ROOT / "acestep_v15_pipeline.py"


def _load_limits_module():
    fake_soundfile = types.ModuleType("soundfile")
    fake_soundfile.info = MagicMock()
    prior = sys.modules.get("soundfile")
    sys.modules["soundfile"] = fake_soundfile
    try:
        spec = importlib.util.spec_from_file_location(
            "audio_input_limits_under_test", LIMITS_PATH
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if prior is None:
            sys.modules.pop("soundfile", None)
        else:
            sys.modules["soundfile"] = prior


limits_mod = _load_limits_module()


class _Info:
    def __init__(self, *, samplerate=48_000, channels=2, frames=48_000):
        self.samplerate = samplerate
        self.channels = channels
        self.frames = frames


class AudioInputLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.write(b"audio-fixture")
        self.tmp.close()
        limits_mod.sf.info.reset_mock()
        limits_mod.sf.info.side_effect = None
        limits_mod.sf.info.return_value = _Info()

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass

    def test_defaults_cannot_be_widened_by_environment(self):
        with patch.dict(
            os.environ,
            {
                "ACESTEP_MAX_INPUT_AUDIO_BYTES": str(
                    limits_mod.ABSOLUTE_MAX_AUDIO_FILE_BYTES * 4
                ),
                "ACESTEP_MAX_INPUT_AUDIO_SECONDS": "999999",
                "ACESTEP_MAX_INPUT_AUDIO_SAMPLE_RATE": "999999",
                "ACESTEP_MAX_INPUT_AUDIO_CHANNELS": "99",
                "ACESTEP_MAX_INPUT_AUDIO_SAMPLES": "999999999",
            },
            clear=False,
        ):
            value = limits_mod.get_audio_input_limits()
        self.assertEqual(
            value.max_file_bytes, limits_mod.ABSOLUTE_MAX_AUDIO_FILE_BYTES
        )
        self.assertEqual(
            value.max_duration_seconds,
            limits_mod.ABSOLUTE_MAX_AUDIO_DURATION_SECONDS,
        )
        self.assertEqual(
            value.max_sample_rate, limits_mod.ABSOLUTE_MAX_AUDIO_SAMPLE_RATE
        )
        self.assertEqual(value.max_channels, limits_mod.ABSOLUTE_MAX_AUDIO_CHANNELS)
        self.assertEqual(
            value.max_decoded_samples,
            limits_mod.ABSOLUTE_MAX_DECODED_SAMPLES,
        )

    def test_invalid_environment_fails_closed(self):
        with patch.dict(
            os.environ, {"ACESTEP_MAX_INPUT_AUDIO_BYTES": "not-an-int"}, clear=False
        ):
            with self.assertRaises(limits_mod.AudioInputLimitError):
                limits_mod.get_audio_input_limits()

    def test_soundfile_metadata_passes_without_decoder_or_ffprobe(self):
        with patch.object(limits_mod.subprocess, "run") as run:
            metadata = limits_mod.validate_audio_file_limits(self.tmp.name)
        self.assertEqual(metadata.probe, "soundfile")
        self.assertEqual(metadata.sample_rate, 48_000)
        self.assertEqual(metadata.channels, 2)
        self.assertEqual(metadata.frames, 48_000)
        run.assert_not_called()

    def test_byte_limit_rejects_before_any_metadata_probe(self):
        custom = limits_mod.AudioInputLimits(
            max_file_bytes=3,
            max_duration_seconds=600,
            max_sample_rate=192_000,
            max_channels=8,
            max_decoded_samples=64_000_000,
        )
        with self.assertRaisesRegex(
            limits_mod.AudioInputLimitError, "byte limit"
        ):
            limits_mod.validate_audio_file_limits(self.tmp.name, custom)
        limits_mod.sf.info.assert_not_called()

    def test_duration_rate_channels_and_sample_budget_are_enforced(self):
        custom = limits_mod.AudioInputLimits(
            max_file_bytes=10_000,
            max_duration_seconds=10,
            max_sample_rate=48_000,
            max_channels=2,
            max_decoded_samples=500_000,
        )
        cases = [
            (_Info(samplerate=48_000, channels=2, frames=480_000), "sample budget"),
            (_Info(samplerate=96_000, channels=1, frames=96_000), "sample rate"),
            (_Info(samplerate=48_000, channels=3, frames=48_000), "channel count"),
            (_Info(samplerate=48_000, channels=1, frames=500_000), "duration"),
        ]
        for info, message in cases:
            with self.subTest(message=message):
                limits_mod.sf.info.return_value = info
                with self.assertRaisesRegex(
                    limits_mod.AudioInputLimitError, message
                ):
                    limits_mod.validate_audio_file_limits(self.tmp.name, custom)

    def test_ffprobe_fallback_is_shell_free_and_bounded(self):
        limits_mod.sf.info.side_effect = RuntimeError("unsupported")
        payload = {
            "streams": [
                {
                    "sample_rate": "44100",
                    "channels": 2,
                    "duration": "2.5",
                    "nb_frames": "110250",
                }
            ],
            "format": {"duration": "2.5"},
        }
        completed = types.SimpleNamespace(
            returncode=0, stdout=json.dumps(payload).encode(), stderr=b""
        )
        with patch.object(limits_mod.shutil, "which", return_value="/usr/bin/ffprobe"):
            with patch.object(
                limits_mod.subprocess, "run", return_value=completed
            ) as run:
                metadata = limits_mod.validate_audio_file_limits(self.tmp.name)
        self.assertEqual(metadata.probe, "ffprobe")
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"], limits_mod.FFPROBE_TIMEOUT_SECONDS)
        self.assertEqual(metadata.frames, 110_250)

    def test_ffprobe_timeout_and_oversized_output_fail_closed(self):
        limits_mod.sf.info.side_effect = RuntimeError("unsupported")
        with patch.object(limits_mod.shutil, "which", return_value="ffprobe"):
            with patch.object(
                limits_mod.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("ffprobe", 5),
            ):
                with self.assertRaisesRegex(
                    limits_mod.AudioInputLimitError, "probe failed"
                ):
                    limits_mod.validate_audio_file_limits(self.tmp.name)
            completed = types.SimpleNamespace(
                returncode=0,
                stdout=b"x" * (limits_mod.FFPROBE_OUTPUT_LIMIT_BYTES + 1),
                stderr=b"",
            )
            with patch.object(limits_mod.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(
                    limits_mod.AudioInputLimitError, "output exceeded"
                ):
                    limits_mod.validate_audio_file_limits(self.tmp.name)

    def test_decode_ceiling_reads_one_frame_over_and_postchecks_resampling(self):
        custom = limits_mod.AudioInputLimits(
            max_file_bytes=100,
            max_duration_seconds=10,
            max_sample_rate=192_000,
            max_channels=8,
            max_decoded_samples=960_000,
        )
        metadata = limits_mod.AudioFileMetadata(
            path=self.tmp.name,
            file_size=12,
            sample_rate=48_000,
            channels=2,
            frames=480_000,
            duration_seconds=10,
            probe="soundfile",
        )
        self.assertEqual(limits_mod.decode_frame_limit(metadata, custom), 480_001)
        limits_mod.validate_decoded_audio(
            frames=480_000, channels=2, sample_rate=48_000, limits=custom
        )
        resample_limits = limits_mod.AudioInputLimits(
            max_file_bytes=100,
            max_duration_seconds=10,
            max_sample_rate=192_000,
            max_channels=8,
            max_decoded_samples=500_000,
        )
        with self.assertRaisesRegex(
            limits_mod.AudioInputLimitError, "Resampled"
        ):
            limits_mod.validate_decoded_audio(
                frames=80_000, channels=1, sample_rate=8_000, limits=resample_limits
            )

    def test_directory_and_empty_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                limits_mod.AudioInputLimitError, "regular file"
            ):
                limits_mod.validate_audio_file_limits(directory)
        empty = tempfile.NamedTemporaryFile(delete=False)
        empty.close()
        try:
            with self.assertRaisesRegex(limits_mod.AudioInputLimitError, "empty"):
                limits_mod.validate_audio_file_limits(empty.name)
        finally:
            os.unlink(empty.name)


class _Array:
    def __init__(self, shape, ndim):
        self.shape = shape
        self.ndim = ndim


class _NumpyResult:
    def __init__(self):
        self.T = self

    def squeeze(self, _axis):
        return self

    def astype(self, _dtype):
        return self


class _Waveform:
    def __init__(self, shape):
        self.shape = shape
        self.ndim = 2

    def numpy(self):
        return _NumpyResult()


class IoAudioSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(IO_PATH.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_read_audio_file"
        )
        cls.function_code = compile(
            ast.Module(body=[function], type_ignores=[]), str(IO_PATH), "exec"
        )

    def _make_function(self):
        fake_sf = MagicMock()
        fake_np = types.SimpleNamespace(float32="float32")
        fake_logger = MagicMock()
        error = limits_mod.AudioInputLimitError
        validate_file = MagicMock(
            return_value=limits_mod.AudioFileMetadata(
                path="audio.wav",
                file_size=12,
                sample_rate=48_000,
                channels=1,
                frames=10,
                duration_seconds=10 / 48_000,
                probe="soundfile",
            )
        )
        get_limits = MagicMock(return_value=limits_mod.get_audio_input_limits())
        frame_limit = MagicMock(return_value=11)
        validate_decoded = MagicMock()
        namespace = {
            "Tuple": tuple,
            "np": fake_np,
            "sf": fake_sf,
            "logger": fake_logger,
            "AudioInputLimitError": error,
            "validate_audio_file_limits": validate_file,
            "get_audio_input_limits": get_limits,
            "decode_frame_limit": frame_limit,
            "validate_decoded_audio": validate_decoded,
        }
        exec(self.function_code, namespace)
        return namespace["_read_audio_file"], namespace

    def test_preflight_runs_before_soundfile_decode_and_frames_are_bounded(self):
        function, ns = self._make_function()
        ns["sf"].read.return_value = (_Array((10,), 1), 48_000)
        result, rate = function("audio.wav")
        self.assertEqual(result.shape, (10,))
        self.assertEqual(rate, 48_000)
        ns["validate_audio_file_limits"].assert_called_once()
        ns["sf"].read.assert_called_once_with(
            "audio.wav", dtype="float32", frames=11
        )
        ns["validate_decoded_audio"].assert_called_once_with(
            frames=10,
            channels=1,
            sample_rate=48_000,
            limits=ns["get_audio_input_limits"].return_value,
        )

    def test_limit_rejection_never_reaches_a_decoder(self):
        function, ns = self._make_function()
        ns["validate_audio_file_limits"].side_effect = limits_mod.AudioInputLimitError(
            "rejected"
        )
        with self.assertRaises(limits_mod.AudioInputLimitError):
            function("audio.wav")
        ns["sf"].read.assert_not_called()

    def test_soundfile_failure_uses_bounded_torchaudio_load(self):
        function, ns = self._make_function()
        ns["sf"].read.side_effect = RuntimeError("unsupported")
        fake_torchaudio = types.ModuleType("torchaudio")
        fake_torchaudio.load = MagicMock(return_value=(_Waveform((1, 10)), 48_000))
        prior = sys.modules.get("torchaudio")
        sys.modules["torchaudio"] = fake_torchaudio
        try:
            result, rate = function("audio.aac")
        finally:
            if prior is None:
                sys.modules.pop("torchaudio", None)
            else:
                sys.modules["torchaudio"] = prior
        self.assertEqual(rate, 48_000)
        self.assertIsInstance(result, _NumpyResult)
        fake_torchaudio.load.assert_called_once_with("audio.aac", num_frames=11)

    def test_decoder_limit_error_does_not_fall_through_to_second_decoder(self):
        function, ns = self._make_function()
        ns["sf"].read.return_value = (_Array((11,), 1), 48_000)
        ns["validate_decoded_audio"].side_effect = limits_mod.AudioInputLimitError(
            "overflow"
        )
        fake_torchaudio = types.ModuleType("torchaudio")
        fake_torchaudio.load = MagicMock()
        prior = sys.modules.get("torchaudio")
        sys.modules["torchaudio"] = fake_torchaudio
        try:
            with self.assertRaises(limits_mod.AudioInputLimitError):
                function("audio.wav")
        finally:
            if prior is None:
                sys.modules.pop("torchaudio", None)
            else:
                sys.modules["torchaudio"] = prior
        fake_torchaudio.load.assert_not_called()

    def test_source_contains_no_unbounded_decoder_call(self):
        tree = ast.parse(IO_PATH.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        sf_reads = [
            node
            for node in calls
            if isinstance(node.func, ast.Attribute)
            and node.func.attr == "read"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sf"
        ]
        ta_loads = [
            node
            for node in calls
            if isinstance(node.func, ast.Attribute)
            and node.func.attr == "load"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "torchaudio"
        ]
        self.assertEqual(len(sf_reads), 1)
        self.assertIn("frames", {kw.arg for kw in sf_reads[0].keywords})
        self.assertEqual(len(ta_loads), 1)
        self.assertIn("num_frames", {kw.arg for kw in ta_loads[0].keywords})


class UiValidationSourceTests(unittest.TestCase):
    def _load_functions(self):
        tree = ast.parse(UI_VALIDATION_PATH.read_text(encoding="utf-8"))
        wanted = {
            "_extract_audio_path",
            "validate_uploaded_audio_file",
        }
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        warning = MagicMock()
        gr = types.SimpleNamespace(
            skip=MagicMock(return_value={"__type__": "update"}),
            update=MagicMock(side_effect=lambda **kwargs: kwargs),
            Warning=warning,
        )
        validator = MagicMock()
        labels = {
            "generation.source_audio": "Source Audio",
            "generation.reference_audio": "Reference Audio",
        }

        def translate(key, **kwargs):
            if key == "messages.audio_format_invalid":
                return f"{kwargs['role']} invalid"
            return labels.get(key, key)

        namespace = {
            "Any": object,
            "Optional": object,
            "gr": gr,
            "t": translate,
            "AudioInputLimitError": limits_mod.AudioInputLimitError,
            "validate_audio_file_limits": validator,
        }
        exec(
            compile(ast.Module(body=functions, type_ignores=[]), str(UI_VALIDATION_PATH), "exec"),
            namespace,
        )
        return namespace, gr, validator, warning

    def test_valid_upload_passes_after_metadata_gate(self):
        ns, gr, validator, warning = self._load_functions()
        out = ns["validate_uploaded_audio_file"]("ok.wav", "reference")
        self.assertEqual(out, {"__type__": "update"})
        validator.assert_called_once_with("ok.wav")
        warning.assert_not_called()

    def test_overlimit_upload_is_cleared_with_role_specific_warning(self):
        ns, gr, validator, warning = self._load_functions()
        validator.side_effect = limits_mod.AudioInputLimitError("too large")
        out = ns["validate_uploaded_audio_file"]("huge.wav", "source")
        self.assertEqual(out, {"value": None})
        warning.assert_called_once_with("Source Audio invalid")

    def test_ui_no_longer_probes_with_soundfile_directly(self):
        source = UI_VALIDATION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("soundfile.info", source)
        self.assertIn("validate_audio_file_limits(audio_path)", source)


class GradioIngressSourceTests(unittest.TestCase):
    def test_every_launch_has_a_bounded_upload_size(self):
        tree = ast.parse(PIPELINE_PATH.read_text(encoding="utf-8"))
        launches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "launch"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "demo"
        ]
        self.assertEqual(len(launches), 2)
        for call in launches:
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            self.assertIn("max_file_size", keywords)
            value = keywords["max_file_size"]
            self.assertIsInstance(value, ast.Name)
            self.assertEqual(value.id, "max_upload_bytes")

    def test_ingress_limit_comes_from_the_same_central_policy(self):
        source = PIPELINE_PATH.read_text(encoding="utf-8")
        self.assertIn("get_audio_input_limits().max_file_bytes", source)



if __name__ == "__main__":
    unittest.main()
