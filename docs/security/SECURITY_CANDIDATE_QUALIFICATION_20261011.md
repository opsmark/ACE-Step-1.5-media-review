# Security candidate qualification — 2026-10-11

This receipt belongs to the isolated review repository. It is not a deployment, merge approval, scanner-status change, fleet-health claim, or evidence that the installed runtime uses any candidate branch.

## Scope

The workflow `.github/workflows/security-candidate-qualification.yml` checks the existing security candidate branches with read-only repository permissions. It uses supported Python 3.11, Node 22 where applicable, focused dependencies, pinned GitHub Action commit identities, and no production models, credentials, services, listeners, customer data, GPU jobs or fleet mutation.

## Preserved failed qualification history

The first central workflow run, `38144828646`, was not relabeled as a clean pass.

- TensorBoard's four candidate tests passed, but the job was marked failed afterward because the old `setup-python` pip-cache configuration expected a cache directory in a no-dependency job.
- Training export and LoKr resume failed during test-module import because `acestep.training.__init__` eagerly imported the full dataset/audio/trainer stack. The failures exposed a real package import-coupling defect; adding more dependencies solely to hide it was rejected.
- The first run also used moving major-version Action tags.

Corrections:

- GitHub Actions are pinned to exact inspected release commits.
- Empty pip caching was removed.
- The training package now preserves its public API through lazy exports, so lightweight path-safety and checkpoint-state modules do not import TorchAudio, dataset decoding or the trainer stack unless those public symbols are actually requested.
- Isolated subprocess regressions verify that path-safety and configuration imports remain lightweight and backward compatible.

The model-code provenance candidate also preserves two unsuccessful construction runs:

- `38146150618` stopped because the bounded transformation expected one scoring loader but the maintained source contained two equivalent sites.
- `38146235888` stopped because the generated replacement had invalid Python indentation.

Neither failure produced a promoted source candidate. The final transformation explicitly required two scoring replacements, generated exact indentation, ran `compileall`, passed 11 focused tests on CPython 3.11.17 and committed the candidate in successful run `38146298233`. Its temporary write-enabled builder workflow was deleted afterward and is not part of the candidate PR.

## Supported-runtime results

Run `38145254098` completed successfully across the original nine configured jobs:

- API authentication boundary — Python 3.11
- queue admission atomicity — Python 3.11
- training export containment plus lazy-import regressions — Python 3.11
- model selector containment — Python 3.11
- TensorBoard loopback — Python 3.11
- authentication before body parsing — Python 3.11
- official launcher boundaries plus compile, shell syntax and Compose parsing — Python 3.11
- LoKr data-only resume plus lazy-import regressions — Python 3.11 / CPU PyTorch
- SimpleMV no-shell execution — Node 22

After the model-selector branch expanded to retain the complete maintained downloadable model set and built-in local-only variants, run `38145465223` also completed successfully. Its model-selector job checked branch head `638ad0181085c3bd4ad2d07442a1d4a1c3c66526` on CPython 3.11.17 and passed all 17 focused tests.

Run `38146396591` added model-code provenance as the tenth job and completed successfully across all ten jobs. The new read-only job separately checked the resulting branch, compiled the changed runtime sources and passed all 11 repository-owned-code/data-only-checkpoint tests on Python 3.11. This is source-level qualification for draft PR #10, not a real checkpoint, GPU or service test.

## Promotion boundary

A green focused workflow means only that the specified candidate tests passed in the declared hosted environment. Before merge or deployment, each PR still requires its own stated compatibility, composition, installed-source, target-OS, service rollback and actual behavior checks. Provider findings remain open until the deployed receiving owner verifies the corresponding result.
