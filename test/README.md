# Testing and CI Evidence

This folder contains the automated testing materials prepared for the GameBuddy project progress report.

## Current CI/CD Status

- A local automated regression suite is now available under `test/tests/`.
- A GitHub Actions workflow has been prepared at `.github/workflows/testing-ci.yml`.
- CI is therefore **configured in code but not yet confirmed on GitHub** until the workflow file is pushed and runs in the remote repository.

## Test Plan / Overall Testing Strategy

The current testing strategy focuses on the highest-value MVP paths:

1. Route availability and access control
2. Role-based login and dashboard redirection
3. End-to-end order lifecycle in demo-payment mode
4. Chat permission checks and message persistence
5. Merchant store management and administrator governance actions

The suite uses Flask's test client and an isolated copy of the SQLite database so that tests do not modify the main demo data.

## Test Types Implemented So Far

- Integration tests:
  - multi-step order lifecycle
  - merchant/admin operational flows
- System-style smoke tests:
  - route accessibility
  - role login redirects
- Functional route tests:
  - chat permission checks
  - notification/message persistence

## Evidence Produced In This Folder

- `run_test_suite.py`: local runner that writes a machine-readable summary and a text log
- `tests/`: automated test code
- `results/unittest_run.log`: verbose test execution log
- `results/unittest_summary.json`: structured pass/fail summary
- `results/coverage_summary.txt`: text coverage summary
- `results/coverage.xml`: XML coverage export

## Limitations

- No browser automation or screenshot-based UI testing has been added yet
- No performance, load, or security penetration testing has been added yet
- Stripe live/sandbox callback behaviour is not covered in the current suite because the local MVP mainly uses demo-payment mode
- CI is prepared but must still be pushed to GitHub and executed there to produce a real remote pipeline record

## Recommended Next Improvement

1. Push `.github/workflows/testing-ci.yml` to GitHub and capture the first successful run
2. Add more validation tests for illegal state transitions
3. Add browser-level UI checks for the most important pages
4. Add deployment-level acceptance tests after the final hosting target is ready
