.PHONY: check

# Same commands as the push/PR CI job, except the matrix and the secret scan.
check:
	python -m pytest tests/ -q
	python -m unittest demo/test_demo.py
	python scripts/ci_regression.py --strict
