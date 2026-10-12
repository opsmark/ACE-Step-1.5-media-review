# Dataset manifest containment qualification — 2026-10-11/12

Base branch at construction: `main` at `ca1e85fe9430179831e6bc6be790c332190a3866`  
Candidate branch: `security/dataset-manifest-containment-20261011`  
Runtime: CPython 3.11.17 on `ubuntu-latest`

## Preserved execution history

- Initial construction run `38191371120` applied the bounded preprocess transformation and compiled every changed source, then failed because ordinary package import pulled the optional PyTorch dependency into a focused path-only test environment. It did not promote the candidate.
- Construction run `38191434864` isolated the focused modules, passed 17 behavioral/source checks, removed its one-shot builder/workflow, and sealed the first candidate commit.
- Requalification run `38191632738` passed 20 checks after metadata publication was moved behind the successful atomic manifest replacement. Validation failure and synthetic durable-write failure both preserved the builder's complete prior metadata.

## Qualified source boundary

The candidate enforces strict portable sample identifiers, canonical approved audio roots, manifest size/sample ceilings, duplicate-ID rejection, symlink and cross-root refusal, decode-time path revalidation, canonical tensor destinations, and same-directory atomic tensor/manifest replacement. Manifest data cannot declare a broader trusted root. Failed manifest import and failed save preserve the prior in-memory builder state.

## Limits

This is source-tested candidate evidence, not merge, deployment or scanner closure. No real decoder, GPU model, training job, production dataset, Windows junction/reparse-point behavior, filesystem ACL policy, fleet installation or user outcome was exercised. Existing datasets that reference audio outside the manifest directory now require an explicit trusted `audio_root` or administrator `ACESTEP_DATASET_AUDIO_ROOT` configuration.
