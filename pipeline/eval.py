"""Evaluation harness — runs the pipeline against the test corpus.

Reads paired (image, expected-values) records from test_data/ and runs
extract() + compare() on each. Reports per-field accuracy, latency p50/p95,
cost per call, and a failure breakdown. Output written to reports/.

Goal: keep this small. ~100 lines, not 1000. Its job is to answer
questions about pipeline quality, not to be a product.
"""


def main() -> None:
    """Run the eval corpus and write a report. Implementation pending."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
