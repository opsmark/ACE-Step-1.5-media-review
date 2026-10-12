from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    output = Path(sys.argv[1]).read_text(encoding="utf-8")
    receipt = f"""# Generation resource boundary qualification — 2026-10-12

Status: SOURCE_TESTED / RED_TEAM_REQUALIFIED / ADMISSION_REQUALIFIED / STACKED_ON_PR_1 / DRAFT / UNMERGED / UNDEPLOYED

Base revision: 1bb0cf9d1356c9153459e4572210c6a6b2d8d963
First green qualification: GitHub Actions run 38218516390
Framing/cancellation red-team requalification: GitHub Actions run 38218899974
OpenRouter admission requalification: GitHub Actions run {os.environ['RUN_ID']}
Python: {sys.version.split()[0]}

## Candidate boundary

The candidate bounds declared and chunked generation bodies before FastAPI/Pydantic route parsing; rejects conflicting Content-Length framing and trailing-slash bypasses; constrains text, base64 audio, custom timesteps, track classes, duration, batch size, inference steps and seed fan-out; and intersects absolute ceilings with the active hardware tier. The documented `-1` automatic-duration sentinel remains compatible while zero and every other explicit non-positive duration are rejected.

OpenRouter preprocessing is serialized per process before decode/file creation and cover-code conversion, then published atomically to the existing shared queue under the maintained pending/temp lock order. Full/racing queues, deadline setup errors, parser failures and cancellation before admission remove request-owned files, pending metadata and the exact unsubmitted job record. A started cover-conversion thread is shielded from request cancellation and awaited before cancellation propagates, preventing repeated disconnects from escaping the prequeue concurrency bound.

Streaming and non-streaming jobs share the same bounded deadline. Timeout/disconnect cancellation is terminal in the store, cannot be overwritten by later exception/progress paths, skips work cancelled before model initialization, and is rechecked after initialization and from progress callbacks. Core duration and batch-size checks remain defense in depth.

## Preserved negative evidence and corrections

- Run 38217731578: invalid workflow YAML; no source candidate promoted.
- Run 38217812125: incomplete parser-transform count.
- Run 38217948420: focused checks passed but parent worker tests exposed an assumption about minimal stores.
- Run 38218075738: faulty repair-script target.
- Run 38218439703: 56/57; a test harness accidentally protected its supposed unrelated path.
- Run 38218516390: 57/57 first green candidate.
- Post-green review found cancellation ordering/state and request-framing gaps; run 38218899974 requalified those repairs at 63/63.
- Post-PR review then found an explicit `-1` duration compatibility regression plus pre-admission temp-file/job leakage and unbounded concurrent cover conversion. This run qualifies those corrections rather than treating the earlier green state as final.

## Focused and parent test output

```text
{output}```

## Important limits

This remains an isolated source candidate. It does not merge or deploy this branch or PR 1, close the scanner finding, load a real model, exercise a GPU, prove Windows/ASGI/proxy behavior, impose per-principal rate quotas, or hard-stop a native kernel that never returns or invokes a progress callback. Cooperative cancellation prevents late success publication and stops at the next checked boundary; it is not an operating-system process kill.

The OpenRouter prequeue lock deliberately serializes cover-code conversion before admission. If that conversion itself hangs indefinitely, later OpenRouter preprocessing waits rather than creating unbounded conversion threads. Native/model-specific cancellation and timeout require target-runtime qualification. Audio decompression-bomb handling, media retention/session isolation, authentication-before-body-read and downstream proxy ceilings remain separately owned layers or findings.

The branch duplicates only the identity/state-guarded `discard_unsubmitted` primitive already proposed by PR 2 so OpenRouter can roll back its own unpublished jobs. Rebase after PR 2 should keep one identical primitive and its broader `/release_task` admission treatment.

## Receiving gate

1. Land/rebase after PR 1 authentication and reconcile the identical store primitive plus `/release_task` behavior from PR 2.
2. Run the full suite on the declared Windows/Python target, including actual ASGI server and proxy framing behavior.
3. Exercise JSON, urlencoded and multipart ingress immediately below/at/above limits, with conflicting lengths, chunked transfer and trailing slashes.
4. Generate normal short/long tracks, cover/repaint inputs, streaming output, client disconnects, a queue-full race, queued deadlines and a deadline during model initialization using trusted local weights.
5. Confirm every pre-admission failure leaves no request temp file, pending ID, temp registry entry or job record, and that admitted files survive until worker cleanup.
6. Confirm a cancelled cover conversion does not permit a second conversion to escape the one-at-a-time prequeue bound.
7. Inventory legitimate clients affected by the tightened contract, preserve installed-source rollback, and close the finding only after deployed runtime retest with actual receipts.
"""
    path = Path("docs/evidence/SECURITY_GENERATION_RESOURCE_BOUNDS_QUALIFICATION_20261012.md")
    path.write_text(receipt, encoding="utf-8")


if __name__ == "__main__":
    main()
