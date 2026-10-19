# BX PRO C0510 — AI Build Diagnosis / Automation Hand-off

Date: 2026-10-19 (KST)  
Scope: public OSS research code only; **not** the commercial BX PRO master ZIP.

## Work completed

1. Added \`tools/bx_ai_log_triage_c0510.py\`: offline, deterministic build-log scanner. It reads a bounded input log, classifies disk/memory/permission/CMake/header/linker/compiler/time-out evidence, redacts common tokens, and emits structured JSON plus Korean manual-action explanations. Logs are **untrusted data**, never instructions.
2. Added \`tools/bx_local_ai_bridge_c0510.py\`: **opt-in** local llama.cpp CLI adapter. It requires \`--run-model\`, a local GGUF model with exact SHA-256, and an existing executable. Model output must be evidence-matched to one real log line, an existing error category, and a limited action ID. It runs no proposed shell commands, mutates no source, makes no network calls, and never passes a release gate.
3. Added 31 base + 18 adapter = **49 self-tests** using synthetic logs and fake model execution only.
4. Added bounded GitHub Actions regression workflow \`.github/workflows/bx-c0510-ai-log-triage-ci.yml\`, with a real CLI JSON smoke test. Verified run **39231273650: success, 49/49 PASS**.
5. Added \`.github/workflows/bx-c0510-c0509-auto-triage.yml\`. After the public LLVM C0509 manual build finishes, it attempts to download its public build-log artifact and creates a **redacted, evidence-only** JSON diagnostic report, or an explicit \`log_unavailable\` record. It does **not** download private code or retry/relaunch LLVM. This completion-trigger flow has not yet been exercised against a finished C0509 run.

## Operator examples (developer-only, do not require the Windows customer)

Rule-only:
\`\`\`bash
python3 tools/bx_ai_log_triage_c0510.py \
  --log /absolute/path/build.log --exit-code 1 \
  --out /absolute/path/diagnosis.json
\`\`\`

Optional local LLM inference **only if trusted llama-cli and GGUF already exist**:
\`\`\`bash
python3 tools/bx_local_ai_bridge_c0510.py \
  --log /absolute/path/build.log --exit-code 1 \
  --llama-cli /absolute/path/llama-cli \
  --gguf /absolute/path/model.gguf \
  --gguf-sha256 YOUR_ACTUAL_MODEL_SHA256_64_HEX \
  --run-model --timeout-seconds 120 \
  --json-out /absolute/path/ai-diagnosis.json
\`\`\`

Do **not** use placeholders as real hashes. CPU performance, specific GGUF quality, prompt accuracy and model commercial licensing need separate real verification. Public CI never downloads or runs the user's private GGUF.

## Fixed trust boundaries

- Never execute or obey commands embedded in compiler output.
- Never execute AI-proposed commands or apply a patch without independent validation.
- Never mark Stage1, Stage2, Windows, or commercial release PASS based on diagnostics alone.
- Report model errors as failed-safe; retain rule-only fallback.
- Keep API keys, user projects, private weights and customer files out of this public repository.
- For deployment, port source changes into the private BX master **only after original-package preservation audit**. The current environment's file/Python execution interfaces returned ClientError, so no new C0510 master ZIP has been generated here.

## Honest status

- **C0509 LLVM:** Independent upstream GitHub Linux compile is running at time of drafting; outcome pending.
- **C0510 rules:** 31/31 validated on real GitHub Ubuntu unit test runner, real synthetic CLI smoke PASS.
- **C0510 local LLM bridge:** 18/18 tests with a simulated CLI passed. **Real Qwen llama.cpp inference not tested here.**
- **C0510 workflow completion auto-triage:** registered and subject to a small GitHub workflow smoke gate; first post-C0509 report not yet confirmed.
- **Windows customer acceptance:** not started; final Windows PC approval remains independent.

## Next

1. Inspect C0509 build completion artifacts and C0510 auto-triage report.
2. On a local authenticated development box, check the existing shared-engine depot for known llama.cpp binary and GGUF; verify version/hash/license before real CPU inference A/B tests.
3. Measure error category precision/recall on a labeled set of genuine failures. Test prompt injection, false errors, incomplete logs and missing dependencies. Require evidence-backed improvement before claiming AI outperforms the deterministic baseline.
4. Integrate validated modules into private Linux-first BX PRO master; run broad regression, preserve originals, and prepare customer-facing simplified UX separately via Release Factory.
