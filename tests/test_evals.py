import unittest
from political_core.evals import evaluate_records

class EvalTests(unittest.TestCase):
    def test_false_high_confidence_metric(self):
        metrics = evaluate_records([
            {"expected_verdict":"true", "actual_verdict":"false", "confidence":.9, "citation_ids":["E1"], "available_evidence_ids":["E1"]},
            {"expected_verdict":"false", "actual_verdict":"false", "confidence":.85, "citation_ids":["E2"], "available_evidence_ids":["E2"]},
        ])
        self.assertEqual(metrics["false_high_confidence_rate"], .5)
        self.assertEqual(metrics["citation_validity"], 1.0)

if __name__ == "__main__": unittest.main()
