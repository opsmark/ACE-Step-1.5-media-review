from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    output = Path(sys.argv[1]).read_text(encoding="utf-8")
    receipt = f"""# Generation resource boundary qualification — 2026-10-12

Status: SOURCE_TESTED / RED_TEAM_REQUALIFIED / STACKED_ON_PR_1 / DRAFT / UNMERGED / UNDEPLOYED

Base revision: 1bb0cf9d1356c9153459e4572210c6a6b2d8d963
Initial green qualification: GitHub Actions run 38218516390
Red-team requalification: GitHub Actions run {os.environ['RUN_ID']}
Python: {sys.version.split()[0]}

## Candidate boundary

The candidate bounds declared and chunked generation bodies before FastAPI/Pydantic route parsing, rejects conflicting Content-Length framing, normalizes a single trailing slash for protected generation routes, rejects over-budget text/base64 before temporary files or model work, intersects duration and batch size with the active GPU tier and absolute ceilings, caps inference steps, seed fan-out, custom timesteps and track-class collections, and constrains the custom Gradio generation payload.

Streaming and non-streaming OpenRouter jobs receive the same bounded deadline. Timeout and disconnect cancellation are terminal in the job store, cannot be overwritten by later exception/progress paths, skip work that has not reached model initialization, and are rechecked after initialization and from generation progress callbacks. Core duration and batch-size checks remain as defense in depth.

## Preserved negative evidence and corrections

- Run 38217731578 exposed invalid workflow YAML before any source candidate was promoted.
- Run 38217812125 exposed an incomplete parser-transform count.
- Run 38217948420 passed the new focused policy tests but failed two parent worker-loop tests because the first integration assumed every test store implemented cancellation.
- Run 38218075738 exposed a faulty repair-script target before source transformation.
- Run 38218439703 passed 56 of 57 checks; its sole failure was a test-harness error that accidentally configured the supposedly unrelated path as protected.
- Run 38218516390 passed 57 of 57 checks and sealed the first source candidate.
- Post-seal red-team review found that cancellation was checked after model initialization, a later failure could overwrite the cancellation reason, duplicate Content-Length values were collapsed, and a trailing slash could miss the exact-path body limit. This requalification repairs and tests those cases rather than relabeling the first candidate as final.

## Focused and parent test output

```text
{output}```

## Important limits

This is an isolated source candidate. It does not merge or deploy either this branch or PR 1, close the scanner finding, load a real model, exercise a GPU, prove Windows/ASGI-server behavior, impose per-principal rate quotas, or hard-stop a native kernel that never returns or invokes a progress callback. Cooperative cancellation prevents late success publication and stops at the next checked boundary; it is not an operating-system process kill. Audio decompression-bomb handling, media retention/session isolation, authentication-before-body-read and downstream proxy limits remain separately owned findings or layers.

The 64 MiB request ceiling is a hard maximum; environment configuration may only tighten it. Compatibility should be reviewed for clients that require more than two input audio parts, unusually long lyrics/audio codes/custom timesteps, more than 64 track classes, batch size above 8, or more than 200 inference steps.

## Receiving gate

1. Land/rebase after PR 1 authentication and rerun the full suite on the declared Windows/Python environment.
2. Exercise JSON, urlencoded and multipart ingress with Content-Length, duplicate/conflicting headers, trailing slashes and chunked bodies immediately below/above each limit.
3. Generate a normal short track, a supported long track, cover/repaint inputs, streaming output, a disconnected stream, a queued deadline and a deadline during model initialization using real local weights.
4. Confirm over-limit requests fail before temp-file creation, audio decode, queue admission, model selection or GPU allocation.
5. Confirm timed-out running work stops at the next cooperative progress boundary and cannot overwrite the failed terminal state even when the executor later returns.
6. Inventory legitimate clients affected by the tightened factors before merge and document any reviewed migration; do not widen a hard cap merely to preserve an unknown caller.
7. Preserve the prior installed source and do not close the finding until both embedded OpenRouter and custom Gradio routes are deployed and retested on the target host.
"""
    path = Path("docs/evidence/SECURITY_GENERATION_RESOURCE_BOUNDS_QUALIFICATION_20261012.md")
    path.write_text(receipt, encoding="utf-8")


if __name__ == "__main__":
    main()
