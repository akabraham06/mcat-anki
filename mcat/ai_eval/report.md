# MCAT AI Card Quality Checker — Gold-set Evaluation

Deterministic, offline evaluation (mock AI provider, no network/key).

- **Checker passing cutoff (set before testing):** 0.7
- **Gold set:** 50 known-correct MCAT Q/A + 50 generated candidates from one source

## Accuracy vs. baseline

| System                        | Correct | Total | Accuracy |
| ----------------------------- | ------- | ----- | -------- |
| Multi-category AI checker     | 99      | 100   | 99.0%    |
| Naive length/keyword baseline | 73      | 100   | 73.0%    |

**Checker beats baseline: 99.0% vs 73.0% (+26.0 pts).**

## Positives (known-correct human cards)

- Checker accepted: 49/50
- Baseline accepted: 48/50

## Generated candidates (labelled)

- Accepted: 20
- Blocked: 30
- Correct & useful (accepted good cards): 20
- Wrong / unsupported caught: 6
- Correct-but-bad-teaching (vague/trivial) caught: 18
- Duplicates detected: 6
- Checker decisions matching label: 50/50
- Baseline decisions matching label: 25/50
