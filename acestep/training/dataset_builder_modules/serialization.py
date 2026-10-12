import json
import os
from datetime import datetime
from typing import List, Optional, Tuple

from loguru import logger

from acestep.training.path_safety import safe_path
from .dataset_path_safety import (
    MAX_DATASET_MANIFEST_BYTES,
    MAX_DATASET_MANIFEST_SAMPLES,
    DatasetPathError,
    atomic_write_with,
    resolve_dataset_audio_path,
    resolve_dataset_audio_root,
    validate_sample_id,
)
from .models import AudioSample, DatasetMetadata


class SerializationMixin:
    """Save/load dataset JSON through an explicit embedded-path boundary."""

    def _trusted_audio_root_for_manifest(
        self,
        manifest_path: str,
        explicit_root: Optional[str] = None,
    ) -> str:
        """Resolve a trusted root without accepting one from manifest content."""

        trusted = explicit_root or getattr(self, "_dataset_audio_root", "") or None
        return resolve_dataset_audio_root(manifest_path, explicit_root=trusted)

    def save_dataset(self, output_path: str, dataset_name: str = None) -> str:
        """Save the dataset after revalidating every security-sensitive field.

        Metadata updates are staged with the serialized payload and become
        visible on the builder only after the atomic file replacement succeeds.
        A rejected or interrupted save therefore preserves the caller's prior
        in-memory dataset state.
        """

        if not self.samples:
            return "❌ No samples to save"

        try:
            validated_output = safe_path(output_path)
            approved_root = self._trusted_audio_root_for_manifest(validated_output)

            serialized_samples = []
            seen_ids = set()
            for index, sample in enumerate(self.samples):
                identifier = validate_sample_id(sample.id)
                if identifier in seen_ids:
                    raise DatasetPathError(
                        f"Duplicate dataset sample id at index {index}: {identifier!r}"
                    )
                seen_ids.add(identifier)

                canonical_audio = resolve_dataset_audio_path(
                    sample.audio_path,
                    approved_root,
                    require_exists=True,
                )
                payload = sample.to_dict()
                payload["id"] = identifier
                payload["audio_path"] = canonical_audio
                payload["filename"] = os.path.basename(canonical_audio)
                serialized_samples.append(payload)

            staged_name = dataset_name if dataset_name is not None else self.metadata.name
            staged_created_at = datetime.now().isoformat()
            staged_metadata = self.metadata.to_dict()
            staged_metadata.update(
                {
                    "name": staged_name,
                    "num_samples": len(self.samples),
                    "created_at": staged_created_at,
                }
            )
            dataset = {
                "metadata": staged_metadata,
                "samples": serialized_samples,
            }
            encoded = json.dumps(dataset, indent=2, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > MAX_DATASET_MANIFEST_BYTES:
                raise DatasetPathError(
                    f"Dataset manifest exceeds {MAX_DATASET_MANIFEST_BYTES} bytes"
                )

            def _write_manifest(temporary: str) -> None:
                with open(temporary, "w", encoding="utf-8") as file_obj:
                    file_obj.write(encoded)
                    file_obj.flush()
                    os.fsync(file_obj.fileno())

            atomic_write_with(validated_output, _write_manifest)

            # Publish metadata only after the durable replacement completed.
            self.metadata.name = staged_name
            self.metadata.num_samples = len(self.samples)
            self.metadata.created_at = staged_created_at
            return (
                f"✅ Dataset saved to {validated_output}\n"
                f"{len(self.samples)} samples, tag: '{self.metadata.custom_tag}'"
            )
        except Exception as exc:
            logger.exception("Error saving dataset")
            return f"❌ Failed to save dataset: {str(exc)}"

    def load_dataset(
        self,
        dataset_path: str,
        audio_root: Optional[str] = None,
    ) -> Tuple[List[AudioSample], str]:
        """Load a dataset while confining embedded audio paths and tensor IDs.

        ``audio_root`` is a trusted caller/admin value. When absent, an
        existing builder root, ``ACESTEP_DATASET_AUDIO_ROOT``, or the manifest
        directory supplies the boundary. JSON metadata cannot expand it.
        """

        try:
            validated_path = safe_path(dataset_path)
        except ValueError:
            return [], f"❌ Rejected unsafe dataset path: {dataset_path}"

        if not os.path.isfile(validated_path):
            return [], f"❌ Dataset not found: {dataset_path}"

        try:
            manifest_size = os.path.getsize(validated_path)
            if manifest_size > MAX_DATASET_MANIFEST_BYTES:
                raise DatasetPathError(
                    f"Dataset manifest exceeds {MAX_DATASET_MANIFEST_BYTES} bytes"
                )

            with open(validated_path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)

            if not isinstance(data, dict):
                raise DatasetPathError("Dataset manifest root must be a JSON object")

            metadata_payload = data.get("metadata", {})
            if not isinstance(metadata_payload, dict):
                raise DatasetPathError("Dataset metadata must be a JSON object")

            sample_payloads = data.get("samples", [])
            if not isinstance(sample_payloads, list):
                raise DatasetPathError("Dataset samples must be a JSON array")
            if len(sample_payloads) > MAX_DATASET_MANIFEST_SAMPLES:
                raise DatasetPathError(
                    f"Dataset contains more than {MAX_DATASET_MANIFEST_SAMPLES} samples"
                )

            approved_root = self._trusted_audio_root_for_manifest(
                validated_path,
                explicit_root=audio_root,
            )
            staged_samples: List[AudioSample] = []
            seen_ids = set()
            for index, sample_payload in enumerate(sample_payloads):
                if not isinstance(sample_payload, dict):
                    raise DatasetPathError(
                        f"Dataset sample at index {index} must be a JSON object"
                    )
                sample = AudioSample.from_dict(sample_payload)
                identifier = validate_sample_id(sample.id)
                if identifier in seen_ids:
                    raise DatasetPathError(
                        f"Duplicate dataset sample id at index {index}: {identifier!r}"
                    )
                seen_ids.add(identifier)
                sample.id = identifier
                sample.audio_path = resolve_dataset_audio_path(
                    sample.audio_path,
                    approved_root,
                    require_exists=True,
                )
                sample.filename = os.path.basename(sample.audio_path)
                staged_samples.append(sample)

            staged_metadata = DatasetMetadata(
                name=metadata_payload.get("name", "untitled"),
                custom_tag=metadata_payload.get("custom_tag", ""),
                tag_position=metadata_payload.get("tag_position", "prepend"),
                created_at=metadata_payload.get("created_at", ""),
                num_samples=len(staged_samples),
                all_instrumental=metadata_payload.get("all_instrumental", True),
                genre_ratio=metadata_payload.get("genre_ratio", 0),
            )

            # Commit only after the complete manifest and every embedded path
            # has passed. A failed import cannot leave a partially replaced
            # builder.
            self.metadata = staged_metadata
            self.samples = staged_samples
            self._current_dir = approved_root
            self._dataset_audio_root = approved_root
            return (
                self.samples,
                f"✅ Loaded {len(self.samples)} samples from {validated_path}",
            )
        except Exception as exc:
            logger.exception("Error loading dataset")
            return [], f"❌ Failed to load dataset: {str(exc)}"
