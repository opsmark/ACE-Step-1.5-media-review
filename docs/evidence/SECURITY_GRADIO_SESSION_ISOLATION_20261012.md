# Gradio session artifact isolation — source qualification

- Observed: 2026-10-12T09:09:50Z
- Scanner finding: csf_8001dc958463ac7625456278
- Frozen source base: ca1e85fe9430179831e6bc6be790c332190a3866
- Reviewed carrier head: ca6d8a2d8b134436a28930fa86753a1089ef9a75
- Reconstructed patch SHA-256: 173c1a7f336059bedc86667d293ce756eba6e37e1e389c9185e1fac70d0483a7
- Focused checks: 47 passed; compileall and git diff --check passed.

## Qualified source behavior

Generated audio, sidecars, repaint latents and automatic subtitle files are placed beneath one opaque server-side Gradio session scope. Foreground and AutoGen background generation retain the same scope. Training scan, preview, load, save and preprocessing reject generated artifacts owned by another session. The application no longer publishes the complete generated-output tree through Gradio allowed_paths, and administrator-provided allowed paths may not overlap that tree.

## Limits and receiving gate

This is source-only evidence. The branch is not merged, installed or deployed; the scanner finding remains open. No real GPU generation, full Gradio server, browser pair, Windows filesystem, uploaded production media, authentication deployment, retention policy or user outcome was exercised here. Before adoption, run two authenticated browser sessions against the target supported environment; verify each can generate, preview and train from its own output but cannot enumerate or fetch the other session's media; exercise AutoGen, automatic LRC, page refresh, normal external datasets, explicit allowed paths, cleanup/retention and rollback; then compare the installed revision and preserve the prior files.

## Framework and Windows requalification

The failed runs remain evidence rather than being relabeled. Run 38228229421 exposed Windows path-spelling assumptions, a candidate link escape, and a missing import path in the disposable Gradio probe. Runs 38228695767 and 38228757246 passed the Gradio integration but still failed the Windows link case. Diagnostic run 38228853043 established the cause: Windows supplied the configured temporary root through an 8.3 alias while generated paths used the long alias, so managed-path recognition returned early even though the final entry was a real symlink/reparse point. Run 38229091003 then proved the alias/link repair while exposing two remaining path-string assertions in the training access tests; those tests now compare actual file identity.

The candidate now compares both lexical and resolved path candidates against both lexical and canonical generated-root aliases before applying session containment and link/reparse-point rejection. GitHub Actions run 38229324770 completed the focused suites and compile checks on CPython 3.11 for both Ubuntu and Windows. Path-equivalence tests compare actual files rather than platform-specific slash spelling.

A separate exact Gradio 6.2.0 loopback probe created two independent clients. Repeated calls by one client retained one server-side opaque scope; the second client received a different scope. Each client generated and received a valid audio file while global generated-output allowed_paths remained disabled. The first client authorized its own raw artifact path, while the second client was denied that same path. This is a disposable framework integration check, not the target full ACE-Step UI, authentication deployment, GPU generation, Internet exposure, retention policy or production outcome.
