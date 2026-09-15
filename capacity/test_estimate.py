"""Check sizing invariants and independently calculated boundary cases."""
import copy
import json
import unittest
from pathlib import Path

from estimate import calculate


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path(__file__).with_name("inputs.json").read_text())

    def test_baseline_hand_calculation(self):
        result = calculate(self.data)
        baseline = result["online"][1]
        self.assertEqual(baseline["daily_questions"], 7500)
        self.assertAlmostEqual(baseline["peak_qpm"], 62.5)
        self.assertEqual(baseline["required_concurrent_calls"], 36)
        self.assertEqual(baseline["required_total_tpm"], 309375)
        self.assertEqual(result["storage"][1]["chunks"], 3660000)
        self.assertAlmostEqual(result["storage"][1]["raw_vector_gib"], 13.9617919921875)

    def test_unknown_quota_is_not_zero_or_success(self):
        item = calculate(self.data)["online"][1]
        self.assertIsNone(item["known_limits_supported_qps_ceiling"])
        self.assertEqual(item["quota_status"], "미확인")

    def test_zero_quota_prevents_generation(self):
        self.data["online"]["allocated_limits"]["rpm"] = 0
        self.assertEqual(calculate(self.data)["online"][1]["known_limits_supported_qps_ceiling"], 0)

    def test_output_token_limit_can_dominate_concurrency(self):
        self.data["online"]["allocated_limits"].update(concurrent_calls=100, rpm=600, output_tpm=1200)
        item = calculate(self.data)["online"][1]
        self.assertEqual(item["known_limit_bottleneck"], "output_tpm")
        # 1200/400=3 calls/min; 70% utilization / 0.7875 calls/query.
        self.assertAlmostEqual(item["known_limits_supported_qps_ceiling"], 2.1 / 60 / 0.7875)

    def test_query_replicas_duplicate_ram_not_object_storage(self):
        before = calculate(self.data)["storage"][1]
        self.data["storage"]["query_replicas"] = 4
        after = calculate(self.data)["storage"][1]
        self.assertEqual(before["live_gib"], after["live_gib"])
        self.assertEqual(before["query_ram_gib_all_replicas"] * 2, after["query_ram_gib_all_replicas"])

    def test_embedding_token_quota_limits_batch(self):
        self.data["ingestion"]["embedding_tpm"] = 24000
        item = calculate(self.data)["ingestion"][1]
        self.assertEqual(item["bottleneck"], "임베딩")
        # 24000 TPM /400 tokens =60 chunks/min =1/s.
        self.assertAlmostEqual(item["stage_hours"]["임베딩"], 3660000 / 0.7 / 3600)

    def test_zero_work_and_no_generation(self):
        self.data["facts"].update(daily_users=0, documents=0, source_gb=0)
        result = calculate(self.data)
        self.assertEqual(result["online"][1]["required_concurrent_calls"], 0)
        self.assertEqual(result["storage"][1]["raw_vector_gib"], 0)
        self.assertEqual(result["ingestion"][1]["ideal_overlapped_nights"], 0)

    def test_invalid_units_and_nonfinite_inputs_rejected(self):
        for section, key, value in [("facts", "service_hours", 0), ("online", "target_utilization", 1), ("facts", "source_gb", float("nan")), ("ingestion", "embedding_chunks_per_second", -1)]:
            candidate = copy.deepcopy(self.data)
            candidate[section][key] = value
            with self.assertRaises(ValueError):
                calculate(candidate)


if __name__ == "__main__":
    unittest.main()
