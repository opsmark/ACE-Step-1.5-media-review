"""Model auto-download helpers extracted from API server runtime."""

from __future__ import annotations

import os

from acestep.api.model_registry import (
    DEFAULT_REPO_ID,
    MODEL_REPO_MAPPING,
    ModelSelectionError,
    approved_model_ids,
    normalize_model_identifier,
    resolve_model_directory,
)


def can_access_google(timeout: float = 3.0) -> bool:
    """Check if Google is reachable to select preferred model source."""

    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(("www.google.com", 443))
        return True
    except (socket.timeout, socket.error, OSError):
        return False
    finally:
        sock.close()


def download_from_huggingface(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model snapshot from HuggingFace Hub."""

    from huggingface_hub import snapshot_download

    is_unified_repo = repo_id == DEFAULT_REPO_ID or repo_id == "ACE-Step/Ace-Step1.5"

    if is_unified_repo:
        download_dir = local_dir
        print(f"[Model Download] Downloading unified repo {repo_id} to {download_dir}...")
    else:
        download_dir = os.path.join(local_dir, model_name)
        os.makedirs(download_dir, exist_ok=True)
        print(f"[Model Download] Downloading {model_name} from {repo_id} to {download_dir}...")

    snapshot_download(
        repo_id=repo_id,
        local_dir=download_dir,
        local_dir_use_symlinks=False,
    )

    return os.path.join(local_dir, model_name)


def download_from_modelscope(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model snapshot from ModelScope."""

    from modelscope import snapshot_download

    is_unified_repo = repo_id == DEFAULT_REPO_ID or repo_id == "ACE-Step/Ace-Step1.5"

    if is_unified_repo:
        download_dir = local_dir
        print(f"[Model Download] Downloading unified repo {repo_id} from ModelScope to {download_dir}...")
    else:
        download_dir = os.path.join(local_dir, model_name)
        os.makedirs(download_dir, exist_ok=True)
        print(f"[Model Download] Downloading {model_name} from ModelScope {repo_id} to {download_dir}...")

    try:
        result_path = snapshot_download(
            model_id=repo_id,
            local_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")
    except TypeError:
        print("[Model Download] Retrying with cache_dir parameter...")
        result_path = snapshot_download(
            model_id=repo_id,
            cache_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")

    return os.path.join(local_dir, model_name)


def _existing_nonempty_directory(path: str) -> bool:
    return os.path.isdir(path) and bool(os.listdir(path))


def ensure_model_downloaded(model_name: str, checkpoint_dir: str) -> str:
    """Ensure one registry-approved model exists beneath ``checkpoint_dir``.

    Built-in identifiers may use their pinned repository mapping. Extra IDs
    configured through ``ACESTEP_LOCAL_MODEL_IDS`` must already exist locally;
    they never inherit the historical default remote repository.
    """

    allowed = approved_model_ids()
    model_id = normalize_model_identifier(
        model_name,
        allowed_ids=allowed,
        field_name="model",
    )
    model_path = resolve_model_directory(
        checkpoint_dir,
        model_id,
        allowed_ids=allowed,
    )

    if _existing_nonempty_directory(model_path):
        print(f"[Model Download] Model {model_id} already exists at {model_path}")
        return model_path
    if os.path.lexists(model_path):
        raise ModelSelectionError(
            f"Model destination is not a non-empty directory: {model_path}"
        )

    repo_id = MODEL_REPO_MAPPING.get(model_id)
    if repo_id is None:
        raise ModelSelectionError(
            f"Local-only model {model_id!r} is configured but not present at {model_path}"
        )

    print(f"[Model Download] Model {model_id} not found, checking network...")
    prefer_source = os.environ.get("ACESTEP_DOWNLOAD_SOURCE", "").lower()
    if prefer_source == "huggingface":
        use_huggingface = True
        print("[Model Download] User preference: HuggingFace Hub")
    elif prefer_source == "modelscope":
        use_huggingface = False
        print("[Model Download] User preference: ModelScope")
    else:
        use_huggingface = can_access_google()
        print(f"[Model Download] Auto-detected: {'HuggingFace Hub' if use_huggingface else 'ModelScope'}")

    if use_huggingface:
        print("[Model Download] Using HuggingFace Hub...")
        try:
            download_from_huggingface(repo_id, checkpoint_dir, model_id)
        except Exception as exc:
            print(f"[Model Download] HuggingFace download failed: {exc}")
            print("[Model Download] Falling back to ModelScope...")
            download_from_modelscope(repo_id, checkpoint_dir, model_id)
    else:
        print("[Model Download] Using ModelScope...")
        try:
            download_from_modelscope(repo_id, checkpoint_dir, model_id)
        except Exception as exc:
            print(f"[Model Download] ModelScope download failed: {exc}")
            print("[Model Download] Trying HuggingFace as fallback...")
            download_from_huggingface(repo_id, checkpoint_dir, model_id)

    # Re-resolve after the provider writes files so newly introduced links or
    # path substitutions cannot escape the checkpoint root.
    resolved = resolve_model_directory(
        checkpoint_dir,
        model_id,
        allowed_ids=allowed,
    )
    if not _existing_nonempty_directory(resolved):
        raise RuntimeError(
            f"Model download completed without a non-empty model directory: {resolved}"
        )
    return resolved
