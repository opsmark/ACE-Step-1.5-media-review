from __future__ import annotations

import unittest
from pathlib import Path


class DatasetManifestSourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module_dir = Path(__file__).resolve().parent

    def test_scan_establishes_audio_root(self):
        source = (self.module_dir / "scan.py").read_text(encoding="utf-8")
        self.assertIn("self._dataset_audio_root = directory", source)

    def test_preprocess_revalidates_before_decode_and_write(self):
        source = (self.module_dir / "preprocess.py").read_text(encoding="utf-8")
        self.assertIn("validated_audio_paths = [", source)
        self.assertIn("resolve_dataset_audio_path(", source)
        self.assertIn("resolve_tensor_output_path(", source)
        self.assertIn("atomic_write_with(", source)
        self.assertNotIn('os.path.join(output_dir, f"{sample.id}.pt")', source)
        self.assertNotIn("torch.save(output_data, output_path)", source)

    def test_serialization_stages_before_commit(self):
        source = (self.module_dir / "serialization.py").read_text(encoding="utf-8")
        commit_index = source.index("self.metadata = staged_metadata")
        validation_index = source.index("staged_samples.append(sample)")
        self.assertGreater(commit_index, validation_index)
        self.assertNotIn('metadata_payload.get("audio_root"', source)


if __name__ == "__main__":
    unittest.main()
