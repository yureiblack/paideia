"""The offline benchmarks.

- Retrieval and generation (decision record 20): the dataset lives in
  docs/evaluation/: ten lecture documents written for the benchmark, the
  questions with the passages that answer them, and the key facts of each
  document. scripts/evaluate_retrieval.py runs it.
- Maths (decision record 30): ten lectures typeset by TeX, the model's kept
  readings of their pages, and search questions, in docs/evaluation/maths/.
  scripts/evaluate_maths.py runs it.

This package holds what they use, so the tests can check the datasets, the
metrics and the comparisons without running either.
"""
