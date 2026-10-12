# BX OSS Build Lab

Public, isolated build experiments for **HanbeonBuild BX PRO**.

## Scope
- Build **public upstream projects** (initial targets: ripgrep and Godot) in disposable GitHub-hosted Ubuntu runners.
- Workflows are **manual only** and require the repository owner's typed approval.
- Keep the commercial HanbeonBuild / AFO Release Factory source code, private evidence, secrets, credentials, and customer files in **private** repositories. Never upload the all-in-one development ZIP here.
- A passed GitHub job is an upstream Linux compilation/smoke result, **not** a release certification or physical Windows compatibility result.

## First experiment
1. Open the [Actions tab](https://github.com/nineeye/bx-oss-build-lab/actions).
2. Select **BX C0260 Pinned Upstream OSS Build (Manual)**, then **Run workflow**.
3. Choose `ripgrep` for the first experiment, and enter the workflow approval phrase exactly.
4. Examine the actual GitHub job result, logs, and artifacts. Do not accept a run merely from a locally fabricated manifest.

## Cost and security
Standard GitHub-hosted runners are free for public repositories under GitHub's published billing policy; larger runners and storage can carry charges. Job details/artifacts are visible publicly. Do not put sensitive information into workflow inputs or source files. Third-party upstream build commands should be reviewed before manual approval.

## Status
Bootstrap only. **No actual upstream compilation has been verified in this repository yet.**
