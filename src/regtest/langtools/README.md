# Langtools mechanical regression suite

This directory preserves detailed linguistic examples for the rule-based
`langtools` implementations. These checks are useful while changing mechanical
conjugation or inflection code, but they are intentionally outside `src/tests`
so the smoke, affected, and all targets do not collect them.

Run them with the `regtest` target when working on mechanical language
generation:

```bash
GREENLAND_TEST_MODE=1 ./run_tests.sh regtest
```

Arguments pass through to pytest, so a single language or behavior can be
selected the usual way:

```bash
GREENLAND_TEST_MODE=1 ./run_tests.sh regtest \
  src/regtest/langtools/test_es_conjugation.py -k ir
```

Keep tests here focused on linguistic output tables and broad sets of examples.
Routing, adapter selection, normalization contracts, optional-dependency
behavior, and small representative smoke cases belong in `src/tests/langtools`.
