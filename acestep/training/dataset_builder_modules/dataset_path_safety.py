"""Security boundaries for imported dataset manifest paths.

Dataset JSON is an artifact boundary. Validating the manifest file itself is
not sufficient because its embedded ``audio_path`` and ``id`` fields later
reach decoders and tensor-file writes.
"""

from __future__ import annotations

import ntpath
import os
import re
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, TypeVar

from acestep.training.path_safety import safe_path


MAX_DATASET_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_DATASET_MANIFEST_SAMPLES = 100_000
MAX_DATASET_PATH_CHARS = 4096
SUPPORTED_DATASET_AUDIO_FORMATS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".opus"})

_SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_T = TypeVar("_T")


class DatasetPathError(ValueError):
    """An imported dataset path or filename violates the security contract."""


def validate_sample_id(value: Any) -> str:
    """Return a tensor-safe sample identifier.

    IDs are deliberately narrower than general filenames because the value is
    later used as ``<id>.pt``. The grammar is portable across Windows and
    POSIX and cannot contain separators, drives, traversal tokens or alternate
    data-stream syntax.
    """

    if not isinstance(value, str):
        raise DatasetPathError("Dataset sample id must be a string")
    if value != value.strip():
        raise DatasetPathError("Dataset sample id must not contain surrounding whitespace")
    if not _SAMPLE_ID_RE.fullmatch(value):
        raise DatasetPathError(
            "Dataset sample id must use 1-64 ASCII letters, digits, underscores or hyphens"
        )
    if value.upper() in _WINDOWS_RESERVED_NAMES:
        raise DatasetPathError(f"Dataset sample id is reserved on Windows: {value!r}")
    return value


def _contains(parent: str, child: str) -> bool:
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def _has_ambiguous_windows_syntax(value: str) -> bool:
    drive, _tail = ntpath.splitdrive(value)
    return bool(drive) or value.startswith(("\\\\", "//")) or "\\" in value


def _reject_controls(value: str, *, label: str) -> None:
    if not value:
        raise DatasetPathError(f"{label} is required")
    if len(value) > MAX_DATASET_PATH_CHARS:
        raise DatasetPathError(f"{label} is too long")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise DatasetPathError(f"{label} contains control characters")
    if os.name != "nt" and _has_ambiguous_windows_syntax(value):
        raise DatasetPathError(f"{label} uses Windows/UNC syntax on a non-Windows host")


def _reject_symlink_components(path: str, root: str, *, label: str) -> None:
    """Reject every existing symlink from *root* through *path*.

    The canonical containment check prevents a current escape. Refusing
    symlinked components additionally narrows time-of-check/time-of-use swaps
    and keeps imported datasets from relying on mutable indirection.
    """

    root = os.path.abspath(root)
    candidate = os.path.abspath(path)
    if not _contains(root, candidate):
        raise DatasetPathError(f"{label} escapes its approved root")

    if os.path.lexists(root) and os.path.islink(root):
        raise DatasetPathError(f"{label} root must not be a symlink")

    relative = os.path.relpath(candidate, root)
    current = root
    if relative == os.curdir:
        return
    for part in Path(relative).parts:
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            raise DatasetPathError(f"{label} contains a symlink component: {current}")


def resolve_dataset_audio_root(
    manifest_path: str,
    *,
    explicit_root: Optional[str] = None,
) -> str:
    """Resolve the administrator-approved audio root for a manifest.

    Precedence is: an explicit trusted caller value, the
    ``ACESTEP_DATASET_AUDIO_ROOT`` process setting, then the manifest's own
    directory. A value inside the JSON document is intentionally not trusted
    to expand this boundary.
    """

    manifest = safe_path(manifest_path)
    selected = explicit_root or os.getenv("ACESTEP_DATASET_AUDIO_ROOT")
    if selected:
        try:
            root = safe_path(selected)
        except ValueError as exc:
            raise DatasetPathError(
                f"Dataset audio root is outside the application safe root: {exc}"
            ) from exc
    else:
        root = os.path.dirname(manifest)

    root = os.path.normcase(os.path.normpath(os.path.realpath(root)))
    if not os.path.isdir(root):
        raise DatasetPathError(f"Dataset audio root is not an existing directory: {root}")
    return root


def resolve_dataset_audio_path(
    value: Any,
    approved_root: str,
    *,
    require_exists: bool = True,
) -> str:
    """Resolve one manifest audio path beneath *approved_root*.

    Both relative and absolute paths are accepted only when their canonical
    destination remains under the separately approved root. Existing symlink
    components and unsupported/non-regular files are rejected before decode.
    """

    if not isinstance(value, str):
        raise DatasetPathError("Dataset audio_path must be a string")
    _reject_controls(value, label="Dataset audio_path")

    try:
        root = safe_path(approved_root)
    except ValueError as exc:
        raise DatasetPathError(
            f"Dataset audio root is outside the application safe root: {exc}"
        ) from exc
    root = os.path.normcase(os.path.normpath(os.path.realpath(root)))

    if os.path.isabs(value):
        lexical = os.path.abspath(os.path.normpath(value))
    else:
        lexical = os.path.abspath(os.path.normpath(os.path.join(root, value)))

    _reject_symlink_components(lexical, root, label="Dataset audio_path")
    resolved = os.path.normcase(os.path.normpath(os.path.realpath(lexical)))
    if not _contains(root, resolved):
        raise DatasetPathError("Dataset audio_path escapes its approved root")

    extension = os.path.splitext(resolved)[1].lower()
    if extension not in SUPPORTED_DATASET_AUDIO_FORMATS:
        raise DatasetPathError(f"Unsupported dataset audio format: {extension or '(none)'}")

    if require_exists:
        if not os.path.exists(resolved):
            raise DatasetPathError(f"Dataset audio file does not exist: {resolved}")
        if os.path.islink(resolved):
            raise DatasetPathError("Dataset audio file must not be a symlink")
        try:
            mode = os.stat(resolved, follow_symlinks=False).st_mode
        except OSError as exc:
            raise DatasetPathError(f"Dataset audio file could not be inspected: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise DatasetPathError(f"Dataset audio path is not a regular file: {resolved}")

    return resolved


def resolve_tensor_output_dir(output_dir: str) -> str:
    """Return a canonical tensor output directory under the application root."""

    if not isinstance(output_dir, str):
        raise DatasetPathError("Tensor output directory must be a string")
    _reject_controls(output_dir, label="Tensor output directory")
    try:
        resolved = safe_path(output_dir)
    except ValueError as exc:
        raise DatasetPathError(f"Tensor output directory is unsafe: {exc}") from exc
    return os.path.normcase(os.path.normpath(os.path.realpath(resolved)))


def resolve_tensor_output_path(output_dir: str, sample_id: Any) -> str:
    """Resolve ``<sample_id>.pt`` under a canonical output directory."""

    root = resolve_tensor_output_dir(output_dir)
    identifier = validate_sample_id(sample_id)
    candidate = os.path.join(root, f"{identifier}.pt")
    if os.path.lexists(candidate) and os.path.islink(candidate):
        raise DatasetPathError(f"Tensor destination must not be a symlink: {candidate}")
    if not _contains(root, os.path.normcase(os.path.normpath(os.path.abspath(candidate)))):
        raise DatasetPathError("Tensor destination escapes its output directory")
    return candidate


def atomic_write_with(
    destination: str,
    writer: Callable[[str], _T],
) -> _T:
    """Write through a same-directory temporary path and atomically replace.

    The writer receives a private temporary filename. A pre-existing symlink
    destination is refused; a concurrent symlink swap is replaced as a
    directory entry rather than followed by ``os.replace``.
    """

    directory = os.path.dirname(destination) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".dataset_tensor_", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        result = writer(temporary)
        if os.path.lexists(destination) and os.path.islink(destination):
            raise DatasetPathError(f"Tensor destination must not be a symlink: {destination}")
        os.replace(temporary, destination)
        return result
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
