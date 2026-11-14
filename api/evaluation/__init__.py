"""The offline evaluation of retrieval and generation (decision record 20).

The dataset lives in docs/evaluation/: ten lecture documents written for the
benchmark, the questions with the passages that answer them, and the key
facts of each document. scripts/evaluate_retrieval.py runs the benchmark;
this package holds what it uses, so the tests can check the dataset and the
metrics without running it.
"""
