# Contributing

Thanks for your interest in improving this repository.

## Getting set up

```bash
git clone https://github.com/aidless/agent-redteam.git
cd agent-redteam
pip install -r requirements.txt   # if present
```

## Verifying your change

```bash
make check
```

`make check` runs `pytest tests/`, `python -m unittest demo/test_demo.py`, and
`python scripts/ci_regression.py --strict`. That is the push/PR test job
without the secret scan and the mutation-control job.

## Pull requests

- One logical change per pull request.
- Explain what breaks or is missing without the change.
- State how you verified it, and paste the command output.
- Keep unrelated reformatting out of the diff.

## Security

Do not open a public issue for a security problem. Use the private channel described
in [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
