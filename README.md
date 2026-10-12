# BX OSS Build Lab

Public, isolated build experiments for **HanbeonBuild BX PRO**.

## Scope
- Build **public upstream projects** (initial targets: ripgrep and Godot) in disposable GitHub-hosted Ubuntu runners.
- Workflows are **manual only** and require the repository owner's typed approval.
- Keep the commercial HanbeonBuild / AFO Release Factory source code, private evidence, secrets, credentials, and customer files in **private** repositories. Never upload the all-in-one development ZIP here.
- A passed GitHub job is an upstream Linux compilation/smoke result, **not** a release certification or physical Windows compatibility result.

## Verified first native build (October 12, 2026)
- **ripgrep 14.1.1: real Linux source build and functional smoke PASS.**
- Run: https://github.com/nineeye/bx-oss-build-lab/actions/runs/38211034556
- Recorded job `114685031267`: completed/success; actual Cargo release compilation, version output, fixed-string search test, SHA256SUMS validation, and artifact upload passed.
- Recorded artifact `11728949528`: `bx-c0260-success-ripgrep-38211034556`, 7,274,500 bytes, archive SHA-256 `82923a75ca1183e469ce4d36ade29da605e98ac24e07c313afcff1eeaffc1ac9`.
- **Godot build is NOT RUN / NOT VERIFIED.** Windows native customer gate is NOT APPROVED.
- A Node.js 20 deprecation warning in the first run was nonfatal; upload-artifact is now pinned to v7.0.2 (Node 24) for future runs.

## Next manual experiment: Godot
Use the same manual workflow, set `project=godot` and enter the approval phrase. The official Godot source tag `4.5.1-stable` is pinned to `f62fdbde15035c5576dad93e586201f4d41ef0cb`; SCons wheel `4.9.1` is SHA-256 pinned. This is a significantly larger compilation, so check the completed GitHub job and saved logs before declaring success.

## First experiment (repeat ripgrep if needed)
1. Open the [Actions tab](https://github.com/nineeye/bx-oss-build-lab/actions).
2. Select **BX C0260 Pinned Upstream OSS Build (Manual)**, then **Run workflow**.
3. Choose `ripgrep` for the first experiment, and enter the workflow approval phrase exactly.
4. Examine the actual GitHub job result, logs, and artifacts. Do not accept a run merely from a locally fabricated manifest.

## Cost and security
Standard GitHub-hosted runners are free for public repositories under GitHub's published billing policy; larger runners and storage can carry charges. Job details/artifacts are visible publicly. Do not put sensitive information into workflow inputs or source files. Third-party upstream build commands should be reviewed before manual approval.

## Status
**Status:** ripgrep real Linux build PASSED (run 38211034556); Godot real build PENDING; Windows customer release NOT APPROVED.
