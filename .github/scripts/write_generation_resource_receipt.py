from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    test_path = Path(sys.argv[1])
    test_output = test_path.read_text(encoding="utf-8")
    receipt = f"""# Generation resource boundary qualification — 2026-10-12

Status: SOURCE_TESTED / STACKED_ON_PR_1 / DRAFT / UNMERGED / UNDEPLOYED

Base revision: {os.environ['BASE_SHA']}
GitHub Actions run: {os.environ['RUN_ID']}
Python: {sys.version.split()[0]}

The candidate bounds generation bodies while streaming them, rejects over-budget text/base64 before temporary files or model work, intersects duration and batch size with the active GPU tier and absolute ceilings, caps inference steps and seed fan-out, constrains the custom Gradio generation payload, adds core tensor/seed defense in depth, and gives streaming and non-streaming OpenRouter jobs the same deadline. Timeout and disconnect cancellation are sticky in the job store, skip work that has not started, and are checked cooperatively from generation progress callbacks.

This candidate is stacked on the authentication branch from draft PR 1. It does not merge or deploy either branch, close the scanner finding, load a model, exercise a GPU, prove hard interruption of a hung native kernel that never reports progress, impose per-principal rate quotas, or qualify every proxy/client compatibility case. Audio metadata/decompression-bomb handling and media retention remain separate findings.

## Focused test output

```text
{test_output}```

## Receiving gate

1. Rebase after PR 1 authentication lands and rerun the full suite on the declared Windows/Python environment.
2. Exercise JSON, urlencoded and multipart ingress with content-length and chunked bodies immediately below/above each limit.
3. Generate a normal short track, a supported long track, cover/repaint inputs, streaming output and a disconnected stream with real local weights.
4. Confirm over-limit requests fail before temp-file creation, audio decode, queue admission, model switching or GPU allocation.
5. Confirm timed-out running work stops at the next cooperative progress boundary and cannot later overwrite the failed terminal state.
6. Inventory legitimate clients that rely on more than two input audio parts, very long lyrics/audio codes, batch >8 or inference steps >200 before merge.
7. Preserve the prior installed source and do not close the finding until both embedded OpenRouter and custom Gradio routes are deployed and retested.
"""
    out = Path("docs/evidence/SECURITY_GENERATION_RESOURCE_BOUNDS_QUALIFICATION_20261012.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(receipt, encoding="utf-8")


if __name__ == "__main__":
    main()
