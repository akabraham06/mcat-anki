# MCAT engine benchmark — 2,000-card deck

- Collection: **2,000 cards**, 1,783 graded reviews, coverage 100%
- Iterations per action: **20** (plus 1 warm-up, not counted)
- All times in milliseconds. `worst` is the single slowest observed call.

| Action                 | p50 (ms) | p95 (ms) | worst (ms) | mean (ms) |  n |
| ---------------------- | -------: | -------: | ---------: | --------: | -: |
| `search_all`           |    0.718 |    1.112 |      1.135 |     0.765 | 20 |
| `search_tag`           |    1.643 |    1.998 |      2.279 |     1.713 | 20 |
| `next_card`            |    0.073 |    0.087 |      0.135 |     0.077 | 20 |
| `topic_mastery`        |   14.520 |   15.087 |     16.221 |    14.595 | 20 |
| `exam_readiness`       |   13.297 |   13.565 |     13.579 |    13.246 | 20 |
| `study_recommendation` |   13.323 |   17.201 |     20.167 |    14.019 | 20 |
| `answer_card`          |    0.302 |    0.565 |      1.653 |     0.394 | 20 |
| `undo`                 |    0.182 |    0.624 |      0.857 |     0.241 | 20 |
