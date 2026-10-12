# Bounded audio ingress qualification — 2026-10-12

Status: SOURCE_TESTED / CROSS_PLATFORM_FOCUSED / DRAFT / UNMERGED / UNDEPLOYED

Codex Security finding: `csf_d576fc10819cdf621fcc765a`.
Frozen base: `ca1e85fe9430179831e6bc6be790c332190a3866`.
Reviewed patch SHA-256: `8a317d75cb90d77104f24b1dff188cd6896bf49b899d83dcf0ddd92264cea77b`.
Final Ubuntu qualification and sealing run: `38246185674`.
Windows focused qualification passed in preserved run `38246035522`.

## Qualified behavior

- Gradio rejects uploads above a central 256 MiB ceiling before temporary-file storage.
- Pre-decode policy limits file bytes, duration, sample rate, channels and decoded samples. Environment values may tighten but cannot widen compiled ceilings.
- Metadata uses `soundfile.info` or a shell-free five-second `ffprobe` argv fallback.
- Both native decode paths receive a one-frame-over ceiling; actual decoder output and projected 48 kHz stereo resampling are rechecked before allocation-heavy downstream work.
- Rejected source/reference uploads are cleared with the existing localized warning.
- Nineteen focused checks, compilation and diff checks passed on CPython 3.11 under Ubuntu and Windows.
- A real one-second PCM WAV passed the soundfile metadata path; a real AAC/M4A passed the forced ffprobe path; a tightened half-second duration policy refused the one-second WAV.

## Preserved failures and corrections

The first package-level Base44 test imported optional PyTorch and failed before the focused module because PyTorch was unavailable. The isolated harness later found and corrected a mono-to-stereo resampling undercount. Initial GitHub runs failed before source qualification because manually transported patch segments were incomplete; exact per-segment hashes exposed the transport fault. Three one-byte substitutions in the last affected segment were repaired at documented offsets and the full patch hash was reverified. Run `38246035522` then passed patch reconstruction and all focused checks on Ubuntu and Windows; only its Ubuntu real-media step failed because the runner image did not include ffmpeg/ffprobe. This final run installed that missing test dependency and reran the real-media canary. No failed run was relabeled as a first-pass success.

## Limits and receiving gate

This branch is unmerged and undeployed. It did not run the target Windows installation, real GPU generation, every codec, production proxy limits, concurrent abusive uploads, retention, per-principal quotas or OS-level enforcement. It reduces the reported resource-amplification path but does not certify arbitrary media or eliminate every parser flaw or filesystem race.

Before merge/deployment: inventory legitimate audio and non-audio upload sizes; run target-environment tests; exercise trusted WAV/MP3/AAC/M4A source, reference, cover and repaint generation; verify over-limit refusal precedes full decode, tensor allocation, resampling, model initialization and GPU work; test proxy/body ceilings and concurrency; preserve rollback; close the finding only after deployed runtime readback.
