# Failure modes

What a green run can still get wrong. This is not a list of attacks the harness claims to stop.

## Fake-version traps

A pin to a version PyPI does not serve fails the install before any test runs. The failure looks like a broken checkout. In July 2026 this repo's notes treated `pandas==3.0.5` and `numpy==2.4.6` as that kind of pin. Both version numbers resolve on PyPI as of 2026-11-05, so those notes are not a current claim that the versions are missing. A pin can be fictional on the day it is written and real later, or the reverse. Check the index. Do not copy a version out of an old changelog into `requirements.txt`.

`requirements.lock` is not what CI installs. Its header says it was compiled from `agent-redteam/requirements.txt`, which is not the path of the file in this repo. The lock pins `numpy==2.4.6` and `pandas==2.3.3`. `requirements.txt` allows `numpy>=2.0,<3` and `pandas>=2.2,<3`. Installing one and installing the other are different environments. A green CI job only covers the ranges file.

Hardcoded USD-per-token tables in `targets/openai_target.py` and `configs/default.yaml` are not invoices. They go stale when a vendor changes prices. A cost figure from a run is that table times a token count.

## Judge false greens

The direct runners used to count a pytest skip as a pass, and the gate compared that inflated number to its floor. `pytest` could report 92 passed and 1 skipped while `ci_regression.py` printed 93/93. Those were not two measurements. One of them was booking a test that did not run. The runners now emit `INVENTORY passed= skipped= failed=`, the gate prefers that line over an `N/M tests passed` fraction, and a skip is a regression unless it is one of the two named cases in `scripts/suite_inventory.py` (`test_sentence_transformer_if_available`, and `test_d4_evaluate_regression_detection` only when the reason says the recursion guard fired).

A failure used to be invisible when enough other tests still met the floor: the gate only checked `passed < floor`. One failed test plus a pass count equal to the floor stayed green. `failed > 0` is now a regression even when the floor is met. `tests/test_inventory.py` locks both of these.

`evaluate()` still returns immediately, and reports the floor as passed, when it is re-entered from inside a suite (`_CI_REGRESSION_INVOKED_BY_SUITE`). That return is there to stop a subprocess loop. It is not a run of the suite. The outer gate does not use it. A log from the nested call is not evidence the gate executed.

`.github/workflows/ci_multi_python.yml` still runs `ci_regression.py --strict` with `|| true` and then reads `any_regression` from the JSON. The job's exit code is that field, not the script's own status. A transcript that says the script failed and a JSON file that says `any_regression: false` leaves the job green. The push/PR workflow (`ci.yml`) does not swallow the exit code.

Deleting a registered suite used to be reported as a skip, which made the total smaller and the job greener. A missing file is a regression. The `mutation-control` job in `ci.yml` deletes one registered file and requires both gates to go red, including a negative control that rejects the old `|| true` form of the suite loop.

`scripts/ci_multi_python.py` skips a Python that is not on `PATH` and can exit 0 when the interpreters it did find passed. "3.10 not installed" is not a pass of 3.10. The GitHub matrix fails that cell if `setup-python` cannot provide it. The local script will not.

## Harness blind spots

`SingleAgentOrchestrator.run_attack` calls input separation, the output filter, behavior audit, and constitutional checks. It does not call `tool_whitelist` (layer 2). `success` is true when no layer returned `BLOCK`. `MODIFY` and `FLAG` still count as the attack succeeding. The five `Mock*` classes in `scripts/run_redteam.py` hardcode `success=False` inside `execute()`, and the single-agent loop does not call `execute()`. The CLI score comes from the orchestrator and the canned mock reply, not from those stubs.

`MultiAgentOrchestrator._run_defenses_on_output` calls layer 3 and layer 5 only. Behavior audit is not applied there, even though an older comment said it was.

`MockLLMTarget` returns one fixed string for every call. Output-side defenses see that string, not a model that followed the payload. A block rate printed by `--target mock` is not an attack-success rate and does not transfer to a live model, a new jailbreak, or a production agent. CI does not call OpenAI, Anthropic, or a local server. A live run is a different experiment, on one model, on these prompts, on that day. It is still not a field attacker.

The demo matrix calls the defense classes on synthetic payloads and a scripted stand-in for a target that complies. It does not run the multi-agent orchestrator. `FLAG` is not `BLOCK`. Some expected layers are not exercised; the demo page says so. Those cells are coverage of this code, not a win rate.

`test_sentence_transformer_if_available` does not run unless that package is installed. A green default CI job is not evidence the embedding path works. The calibration numbers in `scripts/calibration_runner.py` are computed on a synthetic score stream, not on labels from a live attack.
