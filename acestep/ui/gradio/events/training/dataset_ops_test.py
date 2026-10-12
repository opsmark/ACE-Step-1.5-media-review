"""Unit tests for dataset_ops.py."""

import unittest
from unittest.mock import MagicMock, patch

from acestep.ui.gradio.events.training.dataset_ops import (
    get_sample_preview,
    save_sample_edit,
    update_settings,
    save_dataset,
)


class TestGetSamplePreview(unittest.TestCase):
    """Tests for get_sample_preview."""

    def test_none_builder_returns_empty(self):
        result = get_sample_preview(0, None)
        # Should return the empty tuple
        self.assertIsNone(result[0])  # audio_path
        self.assertEqual(result[1], "")  # filename

    def test_empty_samples_returns_empty(self):
        builder = MagicMock()
        builder.samples = []
        result = get_sample_preview(0, builder)
        self.assertIsNone(result[0])

    def test_none_index_returns_empty(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        result = get_sample_preview(None, builder)
        self.assertIsNone(result[0])

    def test_out_of_range_index_returns_empty(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        result = get_sample_preview(5, builder)
        self.assertIsNone(result[0])

    def test_valid_sample_returns_data(self):
        sample = MagicMock()
        sample.audio_path = "/path/to/audio.wav"
        sample.filename = "audio.wav"
        sample.caption = "Test caption"
        sample.genre = "rock"
        sample.prompt_override = "genre"
        sample.lyrics = "Hello world"
        sample.formatted_lyrics = ""
        sample.bpm = 120
        sample.keyscale = "C major"
        sample.timesignature = "4/4"
        sample.duration = 30.0
        sample.language = "en"
        sample.is_instrumental = False
        sample.raw_lyrics = ""
        sample.has_raw_lyrics.return_value = False

        builder = MagicMock()
        builder.samples = [sample]

        with patch(
            "acestep.ui.gradio.events.training.dataset_ops.authorize_builder_sample",
            return_value="/path/to/audio.wav",
        ):
            result = get_sample_preview(0, builder)
        self.assertEqual(result[0], "/path/to/audio.wav")
        self.assertEqual(result[1], "audio.wav")
        self.assertEqual(result[4], "Genre")  # prompt_override converted


class TestUpdateSettings(unittest.TestCase):
    """Tests for update_settings."""

    def test_none_builder_returns_none(self):
        result = update_settings("tag", "prefix", False, 50, None)
        self.assertIsNone(result)

    def test_updates_genre_ratio(self):
        builder = MagicMock()
        builder.metadata = MagicMock()
        result = update_settings("", "prefix", False, 75, builder)
        self.assertEqual(result.metadata.genre_ratio, 75)


class TestSaveDataset(unittest.TestCase):
    """Tests for save_dataset."""

    def test_none_builder(self):
        status, _ = save_dataset("path.json", "name", None)
        self.assertIn("❌", status)

    def test_empty_samples(self):
        builder = MagicMock()
        builder.samples = []
        status, _ = save_dataset("path.json", "name", builder)
        self.assertIn("❌", status)

    def test_empty_path(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        status, _ = save_dataset("", "name", builder)
        self.assertIn("❌", status)

    def test_save_uses_session_boundary_before_writing(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        builder.get_labeled_count.return_value = 1
        builder.save_dataset.return_value = "✅ saved"
        scope = "C" * 43

        with patch(
            "acestep.ui.gradio.events.training.dataset_ops.bind_builder_to_session"
        ) as bind, patch(
            "acestep.ui.gradio.events.training.dataset_ops.authorize_training_path",
            return_value="/safe/dataset.json",
        ) as authorize, patch(
            "acestep.ui.gradio.events.training.dataset_ops.validate_builder_audio_paths",
            return_value=(True, ""),
        ) as validate:
            status, _update = save_dataset("dataset", "name", builder, scope)

        self.assertEqual("✅ saved", status)
        bind.assert_called_once_with(builder, scope)
        authorize.assert_called_once_with("dataset.json", scope, must_exist=False)
        validate.assert_called_once_with(builder, must_exist=False)
        builder.save_dataset.assert_called_once_with("/safe/dataset.json", "name")

    def test_save_rejects_builder_owned_by_another_session(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        scope = "D" * 43

        with patch(
            "acestep.ui.gradio.events.training.dataset_ops.bind_builder_to_session",
            side_effect=ValueError("other session"),
        ):
            status, _update = save_dataset("dataset.json", "name", builder, scope)

        self.assertIn("outside this session", status)
        builder.save_dataset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
