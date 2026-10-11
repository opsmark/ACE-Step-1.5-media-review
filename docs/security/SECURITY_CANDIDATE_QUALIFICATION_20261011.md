# Security candidate qualification — 2026-10-11

This receipt belongs to the isolated review repository. It is not a deployment, merge approval, scanner-status change, fleet-health claim, or evidence that the installed runtime uses any candidate branch.

## Scope

The workflow `.github/workflows/security-candidate-qualification.yml` checks the existing security candidate branches with read-only repository permissions. It uses supported Python 3.11, Node 22 where applicable, focused dependencies, pinned GitHub Action commit identities, and no production models, credentials, services, listeners, customer data, GPU jobs or fleet mutation.

## Preserved failed qualification history

The first workflow run, `38144828646`, was not relabeled as a clean pass.

- TensorBoard's four candidate tests passed, but the job was marked failed afterward because the old `setup-python` pip-cache configuration expected a cache directory in a no-dependency job.
- Training export and LoKr resume failed during test-module import because `acestep.training.__init__` eagerly imported the full dataset/audio/trainer stack. The failures exposed a real package import-coupling defect; adding more dependencies solely to hide it was rejected.
- The first run also used moving major-version Action tags.

Corrections:

- GitHub Actions are pinned to the exact current release commits inspected on 2026-10-11.
- Empty pip caching was removed.
- The training package now preserves its public API through lazy exports, so lightweight path-safety and checkpoint-state modules do not import TorchAudio, dataset decoding or the trainer stack unless those public symbols are actually requested.
- Isolated subprocess regressions verify that path-safety and configuration imports remain lightweight and backward compatible.

## Clean supported-runtime run

Workflow run `38145254098` completed successfully across all nine jobs then configured:

- API authentication boundary — Python 3.11
- queue admission atomicity — Python 3.11
- training export containment plus lazy-import regressions — Python 3.11
- model selector containment — Python 3.11
- TensorBoard loopback — Python 3.11
- authentication before body parsing — Python 3.11
- official launcher boundaries plus compile, shell syntax and Compose parsing — Python 3.11
- LoKr data-only resume plus lazy-import regressions — Python 3.11 / CPU PyTorch
- SimpleMV no-shell execution — Node 22

After that run started, the model-selector branch was expanded to preserve the complete maintained downloadable model set plus built-in local-only variants. This file update triggers another full workflow run so the final receipt does not silently reuse the earlier 15-test model-registry result for the newer 17-test branch.

## Promotion boundary

A green focused workflow means only that the specified candidate tests passed in the declared hosted environment. Before merge or deployment, each PR still requires its own stated compatibility, composition, installed-source, target-OS, service rollback and actual behavior checks. Provider findings remain open until the deployed receiving owner verifies the corresponding result.
