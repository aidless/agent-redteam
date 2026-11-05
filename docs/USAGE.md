# Agent Red Team Platform — Usage Guide

## Offline and live

Install from this repo. There is no PyPI package. CI installs `requirements.txt`, not `requirements.lock`.

```bash
pip install -r requirements.txt
```

**Offline (no API key).** `make check` runs the pytest suite, the demo contract tests, and `scripts/ci_regression.py --strict`. Counts are the inventory block in the README. The commands below do not spend money:

```bash
make check
python demo/cli.py
python scripts/run_redteam.py --target mock --rounds 5 --no-record
```

The mock runner prints a block rate. That number is the orchestrator plus a canned reply on this harness's prompts. It is not an attack-success rate. This page does not quote one. `SingleAgentOrchestrator` does not call the tool-whitelist layer, and a `MODIFY` or `FLAG` still counts as the attack succeeding. See `FAILURE_MODES.md`.

**Live API (not part of CI or the inventory).** Requires a key or a local server. Still not a measurement of a real attacker.

```bash
python scripts/run_redteam.py --target openai --model gpt-4o-mini --rounds 20 --max-cost-usd 5
python scripts/run_redteam.py --target anthropic --rounds 20 --max-cost-usd 5
python scripts/run_redteam.py --target local --rounds 20
```

Keys are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `LOCAL_LLM_API_KEY`. Copy `.env.example` to `.env` if you want them in a file. Do not commit `.env`.

### 3. Launch the Streamlit dashboard

```bash
# From Git Bash on Windows:
scripts/dashboard.sh

# Or from cmd.exe:
scripts\dashboard.cmd

# Or directly:
streamlit run scripts/dashboard.py
```

Then open http://localhost:8501 in your browser.

## Configuration

Defense behavior can be customized via `configs/default.yaml`. Example:

```yaml
input_separation:
  quarantine_threshold: 0.3
  instruction_patterns:
    - "ignore.*previous.*instructions"
    - "system.*prompt.*:"
    # add custom patterns

tool_whitelist:
  agent_tool_whitelist:
    default: ["search", "read_file", "summarize"]
    code_executor: ["execute_python", "execute_bash"]
  dangerous_arg_patterns:
    - "\\.\\./\\.\\./"
    - "rm\\s+-rf"
    # add custom dangerous patterns

output_filter:
  max_output_length: 8000
  enable_pii_redaction: true
  enable_secret_redaction: true

behavior_audit:
  max_actions_per_minute: 30
  max_memory_writes_per_turn: 5
  voting_outlier_threshold: 0.3

constitutional:
  enable_llm_classifier: false  # set true in production
```

## Adding New Attack Vectors

1. Add a new sample to `data/attack_vectors.json` (see existing format).
2. Optionally implement a class in `attacks/<vector_name>.py` (see base.py).
3. Register the attack in `scripts/run_redteam.py:ATTACK_REGISTRY`.
4. Re-run the simulation and verify block rate.

## Adding New Defense Layers

1. Create `defenses/<layer_name>.py` inheriting from `Defense`.
2. Implement `check(event) -> DefenseResult`.
3. Add to the `defenses = [...]` list in `scripts/run_redteam.py`.
4. Update `scripts/dashboard.py` sidebar `DEFENSE_INFO`.
5. Update `README.md` defense stack documentation.

## Interpreting results

The CLI fields are counts inside this run, not a security claim.

| Field | What it is |
|---|---|
| Block rate | Share of rounds where some layer returned `BLOCK` |
| Block rate by layer | How often that layer was the one that returned `BLOCK` |
| Attacks succeeded | Rounds where nothing returned `BLOCK`, including rounds that were only modified or flagged |
| Defense latency | Time spent inside `Defense.check` on this machine |

This harness does not define a pass threshold on those rates. A number from the mock target does not transfer to a live model.

## Extending the Platform

### Adding a real LLM target

Replace mock attack/defense stubs with real LLM API calls. The interface
contracts in `attacks/base.py` and `defenses/base.py` are designed to be
LLM-agnostic.

### Adding telemetry / logging

Modify `Defense.check()` to write structured logs to `outputs/telemetry.jsonl`.
Each log entry should include timestamp, defense_name, action, confidence,
and any matched patterns.

### CI/CD integration

The platform can be run in CI as a regression test. The first command below is
real (`scripts/run_redteam.py` is in the tree); the second is a **sketch of a
gate you would have to write yourself** -- `scripts/check_block_rate.py` does not
exist in this repository, so copying the snippet verbatim fails at that step.

```yaml
- name: Red team regression
  run: python scripts/run_redteam.py --rounds 500 --output outputs/ci_regression.json
# You must supply this. Parse ci_regression.json, compute blocked/total, and
# exit non-zero below your threshold. Do not expect it in the tree.
- name: Fail if block rate drops below 80%
  run: python scripts/check_block_rate.py --threshold 0.80
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError: streamlit` | `pip install streamlit` |
| `re.error: global flags not at the start` | Each regex pattern should have its own `(?i)` prefix or wrap the join in `(?i:...)` |
| `ImportError: cannot import name 'X'` | Check that `__init__.py` exports the right symbols; restart Python |
| Dashboard not loading | Ensure `outputs/` directory exists; run `python scripts/run_redteam.py` first |
| High attack success rate | Tune defense config in `configs/default.yaml`; consider adding LLM-based constitutional classifier |

## License

Apache 2.0. See `LICENSE` file.

## References

- `README.md`
- `FAILURE_MODES.md`
- `data/attack_vectors.json`