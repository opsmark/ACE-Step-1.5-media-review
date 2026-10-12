#!/usr/bin/env python3
"""Apply exact, bounded sink wiring for imported dataset paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "acestep" / "training" / "dataset_builder_modules" / "preprocess.py"


def replace_once(old: str, new: str) -> None:
    text = TARGET.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{TARGET} expected one exact match, found {count}")
    TARGET.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "from .models import AudioSample\n",
    "from .models import AudioSample\n"
    "from .dataset_path_safety import (\n"
    "    DatasetPathError,\n"
    "    atomic_write_with,\n"
    "    resolve_dataset_audio_path,\n"
    "    resolve_tensor_output_dir,\n"
    "    resolve_tensor_output_path,\n"
    "    validate_sample_id,\n"
    ")\n"
    "from acestep.training.path_safety import get_safe_root\n",
)

replace_once(
    "        os.makedirs(output_dir, exist_ok=True)\n\n"
    "        output_paths: List[str] = []",
    "        try:\n"
    "            output_dir = resolve_tensor_output_dir(output_dir)\n"
    "        except DatasetPathError as exc:\n"
    "            return [], f\"❌ Unsafe tensor output directory: {exc}\"\n"
    "        os.makedirs(output_dir, exist_ok=True)\n\n"
    "        output_paths: List[str] = []",
)

replace_once(
    "        genre_indices = select_genre_indices(labeled_samples, self.metadata.genre_ratio)\n"
    "        debug_log_verbose_for(\"dataset\", f\"selected genre indices: count={len(genre_indices)}\")\n\n"
    "        for i, sample in enumerate(labeled_samples):",
    "        genre_indices = select_genre_indices(labeled_samples, self.metadata.genre_ratio)\n"
    "        debug_log_verbose_for(\"dataset\", f\"selected genre indices: count={len(genre_indices)}\")\n\n"
    "        approved_audio_root = (\n"
    "            getattr(self, \"_dataset_audio_root\", \"\")\n"
    "            or getattr(self, \"_current_dir\", \"\")\n"
    "            or get_safe_root()\n"
    "        )\n"
    "        try:\n"
    "            validated_ids = [validate_sample_id(sample.id) for sample in labeled_samples]\n"
    "            if len(set(validated_ids)) != len(validated_ids):\n"
    "                raise DatasetPathError(\"Duplicate sample ids would overwrite tensor outputs\")\n"
    "            validated_audio_paths = [\n"
    "                resolve_dataset_audio_path(sample.audio_path, approved_audio_root)\n"
    "                for sample in labeled_samples\n"
    "            ]\n"
    "            validated_tensor_paths = [\n"
    "                resolve_tensor_output_path(output_dir, sample_id)\n"
    "                for sample_id in validated_ids\n"
    "            ]\n"
    "        except DatasetPathError as exc:\n"
    "            return [], f\"❌ Rejected unsafe dataset sample: {exc}\"\n\n"
    "        for i, sample in enumerate(labeled_samples):",
)

replace_once(
    "            try:\n"
    "                debug_log_verbose_for(\"dataset\", f\"sample[{i}] id={sample.id} file={sample.filename}\")\n\n"
    "                if skip_existing:\n"
    "                    existing_path = os.path.join(output_dir, f\"{sample.id}.pt\")",
    "            try:\n"
    "                sample_id = validated_ids[i]\n"
    "                canonical_audio_path = resolve_dataset_audio_path(\n"
    "                    validated_audio_paths[i],\n"
    "                    approved_audio_root,\n"
    "                )\n"
    "                tensor_output_path = resolve_tensor_output_path(\n"
    "                    output_dir,\n"
    "                    sample_id,\n"
    "                )\n"
    "                if tensor_output_path != validated_tensor_paths[i]:\n"
    "                    raise DatasetPathError(\"Tensor destination changed after preflight\")\n"
    "                sample.id = sample_id\n"
    "                sample.audio_path = canonical_audio_path\n"
    "                debug_log_verbose_for(\"dataset\", f\"sample[{i}] id={sample.id} file={sample.filename}\")\n\n"
    "                if skip_existing:\n"
    "                    existing_path = tensor_output_path",
)

replace_once(
    "                audio, _ = load_audio_stereo(sample.audio_path, target_sample_rate, max_duration)",
    "                audio, _ = load_audio_stereo(canonical_audio_path, target_sample_rate, max_duration)",
)

replace_once(
    '                        "audio_path": sample.audio_path,',
    '                        "audio_path": canonical_audio_path,',
)

replace_once(
    "                output_path = os.path.join(output_dir, f\"{sample.id}.pt\")\n"
    "                t0 = debug_start_verbose_for(\"dataset\", f\"torch.save[{i}]\")\n"
    "                torch.save(output_data, output_path)",
    "                output_path = resolve_tensor_output_path(output_dir, sample_id)\n"
    "                t0 = debug_start_verbose_for(\"dataset\", f\"torch.save[{i}]\")\n"
    "                atomic_write_with(\n"
    "                    output_path,\n"
    "                    lambda temporary: torch.save(output_data, temporary),\n"
    "                )",
)

print("preprocess sink wiring applied")
