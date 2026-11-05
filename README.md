# Agent Red Team

Multi-agent LLM apps treat retrieved text, tool output, and other agents' messages as instructions, so a payload can cross a boundary a single-prompt check never sees.
This repository is a local harness for that problem: synthetic payloads, five defense layers, and a regression suite around the code that implements them.
A green run here is not a measurement of a real attacker.

## What these scores do not prove

A passing test, a green CI job, or a cell in the demo matrix does not estimate how often an attack would work on a live model, a new jailbreak, or a production agent. The mock target returns one canned reply. Nothing in this repository was scored against a hidden attacker, and a result on these prompts does not transfer to one. The ways the harness can still look green are listed in [FAILURE_MODES.md](FAILURE_MODES.md).

## Offline and live

**Offline. No API key.** This is what CI runs. `make check` is the same three commands.

```bash
pip install -r requirements.txt
make check
python demo/cli.py
python scripts/run_redteam.py --target mock --rounds 5 --no-record
```

`pytest` counts a skip separately from a pass. `scripts/ci_regression.py --strict` does too: a skip is not a pass, and a failure still fails the gate when the pass floor is met. The demo prints what each defense class returned on a synthetic payload. It is not an end-to-end agent and not a live model. The mock runner prints a block rate for these prompts against the canned reply. That number is not an attack-success rate. Do not cite it as one.

**Live API. Not run in CI, and not part of the counts below.** One model's replies on these prompts are still not a field attacker. The process needs a key or a local server and can spend money.

```bash
python scripts/run_redteam.py --target openai --model gpt-4o-mini --rounds 20 --max-cost-usd 5
python scripts/run_redteam.py --target anthropic --rounds 20 --max-cost-usd 5
python scripts/run_redteam.py --target local --rounds 20
```

`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `LOCAL_LLM_API_KEY` are read from the environment (see `.env.example`). There is no PyPI package. Install from this repo with `pip install -r requirements.txt`. CI installs that file. `requirements.lock` is not the CI input; it was compiled from a different relative path and does not match the ranges in `requirements.txt`.

The badges above the fold are the Apache-2.0 license and the GitHub Actions workflows in this repo. They are not a download count, a star count, or an attack-success rate.

[![CI](https://github.com/aidless/agent-redteam/actions/workflows/ci.yml/badge.svg)](https://github.com/aidless/agent-redteam/actions/workflows/ci.yml)
[![CI multi-Python](https://github.com/aidless/agent-redteam/actions/workflows/ci_multi_python.yml/badge.svg)](https://github.com/aidless/agent-redteam/actions/workflows/ci_multi_python.yml)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

## Inventory

<!-- current-claims: start -->
<!-- inventory
collected: 103
suites: 9
pytest_passed_without_sentence_transformers: 102
pytest_skipped_without_sentence_transformers: 1
direct_runner_passes_under_gate: 101
direct_runner_skips_under_gate: 2
demo_contract_tests: 16
-->

`pytest tests/` with sentence-transformers not installed collects 103 tests: 102 passed and 1 skipped. The skipped test is `test_sentence_transformer_if_available`.

`python scripts/ci_regression.py --strict` on that same machine reports 101 passes and 2 skips across 9 suites. The extra skip is `test_d4_evaluate_regression_detection`, which the gate's recursion guard skips and which is not counted as a pass.

`python -m unittest demo/test_demo.py` is 16 contract tests. It is not added into either count above.
<!-- current-claims: end -->

Dated entries in [CHANGELOG.md](CHANGELOG.md) keep the counts those commits reported. If one of them disagrees with the block above, the block is the tree. `tests/test_inventory.py` fails when the block, the CI floor, or the workflow suite list drifts.

## Demo

The page you can actually look at is the layer matrix: 12 synthetic payloads by 5 defense classes. [How to read it](demo/README.md). GitHub Pages publishes `demo/public/` from `main` when that workflow runs. The link is the page, not a measured attack rate.

```bash
python3 demo/cli.py          # terminal, no server
python3 demo/server.py       # http://127.0.0.1:8000/
```

## Layout

`attacks/`, `defenses/`, `orchestrator/`, `targets/` (`mock`, `openai`, `anthropic`, `local`), `demo/`, `tests/`, `scripts/`. Usage notes: [docs/USAGE.md](docs/USAGE.md).

## License

Apache-2.0. Not a published package.
