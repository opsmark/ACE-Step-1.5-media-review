"""Regression tests for dependency-lazy ``acestep.training`` imports."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest


class TrainingLazyImportTests(unittest.TestCase):
    def run_isolated(self, body: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(body)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_path_safety_import_does_not_load_audio_or_tensor_stack(self) -> None:
        result = self.run_isolated(
            """
            import sys
            import acestep.training.path_safety
            import acestep.training as training
            assert 'acestep.training.dataset_builder' not in sys.modules
            assert 'torch' not in sys.modules
            assert 'torchaudio' not in sys.modules
            assert 'lightning' not in sys.modules
            assert 'pytorch_lightning' not in sys.modules
            assert 'DatasetBuilder' in dir(training)
            """
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_lightweight_config_export_remains_backward_compatible(self) -> None:
        result = self.run_isolated(
            """
            import sys
            from acestep.training import LoRAConfig
            config = LoRAConfig(r=4, alpha=8)
            assert config.r == 4
            assert config.alpha == 8
            assert 'acestep.training.configs' in sys.modules
            assert 'acestep.training.dataset_builder' not in sys.modules
            assert 'torch' not in sys.modules
            assert 'torchaudio' not in sys.modules
            """
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_unknown_export_raises_normal_attribute_error(self) -> None:
        result = self.run_isolated(
            """
            import acestep.training as training
            try:
                training.not_a_real_export
            except AttributeError:
                pass
            else:
                raise AssertionError('missing AttributeError')
            """
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
