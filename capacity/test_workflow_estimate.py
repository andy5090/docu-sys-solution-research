"""Independent arithmetic and workload boundary tests for the expanded scope."""
import copy
import json
import unittest
from fractions import Fraction as F
from pathlib import Path

from workflow_estimate import calculate


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads(Path(__file__).with_name("workflow_inputs.json").read_text())

    def test_baseline_hand_arithmetic(self):
        r = calculate(self.d)
        # 5 requests/s: 4 chat + 1 draft; file attachments overlap these.
        self.assertEqual(r["daily_requests"], 15000)
        self.assertEqual(r["files_per_second"], 3)
        self.assertEqual(r["ocr_pages_per_second"], 45)
        self.assertEqual(r["jobs_per_second"], 1)
        self.assertEqual([w["count"] for w in r["workers"]], [3, 5, 11, 5])
        self.assertEqual((r["total_vcpu"], r["total_ram_gib"]), (354, 804))
        # Exact fractions independent of the float implementation.
        chat_calls = F(4)*F(11, 10)
        draft_calls = (F(3, 5)*4+F(2, 5)*5)*F(11, 10)
        outputs = chat_calls*800+(F(3, 5)*6000+F(2, 5)*8000)*F(11, 10)
        model_work = (chat_calls+draft_calls)*10+outputs/16
        ceil = lambda x: -(-x.numerator//x.denominator)
        self.assertEqual(r["model_concurrency"], ceil(model_work/F(3, 5)))
        self.assertEqual(r["model_rpm"], 924)
        self.assertEqual(r["model_input_tpm"], 5544000)
        self.assertEqual(r["model_output_tpm"], 1100000)
        self.assertEqual(r["model_total_tpm"], 6644000)
        self.assertEqual(r["embedding_tpm"], 21675000)

    def test_each_pool_survives_one_worker_failure(self):
        for qps in (0.1, 3.7037037037, 5, 10):
            for w in calculate(self.d, qps)["workers"]:
                with self.subTest(qps=qps, role=w["name"]):
                    self.assertGreaterEqual((w["count"]-1)*w["vcpu"]+1e-9, w["required_cpu"])
                    self.assertGreaterEqual((w["count"]-1)*w["slots"], w["required_slots"])

    def test_wall_time_can_be_bottleneck_without_cpu_change(self):
        old = calculate(self.d)["workers"][0]
        self.d["attachments"]["dedrm_wall_seconds_per_file"] = 30
        new = calculate(self.d)["workers"][0]
        self.assertEqual(old["required_cpu"], new["required_cpu"])
        self.assertGreater(new["count"], old["count"])

    def test_memory_budget_cannot_be_overbooked(self):
        self.d["workers"]["render"]["ram_gib"] = 8
        with self.assertRaises(ValueError):
            calculate(self.d)

    def test_storage_independent_of_peak_and_covers_all_copies(self):
        r = calculate(self.d)
        # 9000*10MB*2.5*30 + 3000*7.2MB*90 + 15000*50KiB*90
        expected_live = 6_750_000_000_000+1_944_000_000_000+69_120_000_000
        self.assertAlmostEqual(r["live_tib"], expected_live/2**40)
        self.assertAlmostEqual(r["allocated_tib"], expected_live*2/0.7/2**40)
        self.assertEqual(r["allocated_tib"], calculate(self.d, 10)["allocated_tib"])

    def test_no_attachments_no_file_workers_or_file_storage(self):
        self.d["attachments"]["request_share"] = 0
        r = calculate(self.d)
        self.assertEqual([w["count"] for w in r["workers"][:3]], [0, 0, 0])
        self.assertEqual(r["attachment_retained_tib"], 0)
        self.assertEqual(r["embedding_tpm"], 75000)  # Query embeddings remain.

    def test_no_drafts_does_not_remove_chat_or_attachments(self):
        self.d["generation"]["request_share"] = 0
        r = calculate(self.d)
        self.assertEqual(r["workers"][-1]["count"], 0)
        self.assertEqual(r["artifact_retained_tib"], 0)
        self.assertEqual(r["model_rpm"], 550)
        self.assertEqual(r["model_concurrency"], 550)
        self.assertEqual(r["files_per_second"], 3)

    def test_drm_and_ocr_independently_optional(self):
        self.d["attachments"]["dedrm_share"] = 0
        self.d["attachments"]["ocr_page_share"] = 0
        r = calculate(self.d)
        self.assertEqual([w["count"] for w in r["workers"][:3]], [0, 5, 0])

    def test_no_milvus_dependency(self):
        before = calculate(self.d)
        self.d["legacy_milvus"] = {"query_replicas": 100, "ram_gib": 99999}
        self.assertEqual(before, calculate(self.d))

    def test_model_latency_changes_concurrency_not_token_quota(self):
        old = calculate(self.d)
        self.d["model"]["ttft_seconds"] *= 2
        self.d["model"]["output_tokens_per_second"] /= 2
        new = calculate(self.d)
        self.assertAlmostEqual(new["model_seconds_per_job"], old["model_seconds_per_job"]*2)
        self.assertEqual(new["model_total_tpm"], old["model_total_tpm"])
        self.assertGreater(new["model_concurrency"], old["model_concurrency"])

    def test_invalid_inputs_rejected(self):
        for section, key, val in (("traffic", "service_hours", 0), ("attachments", "request_share", 1.5), ("attachments", "pages_per_file", -1), ("model", "output_tokens_per_second", 0), ("generation", "retry_factor", 0.5), ("model", "ttft_seconds", float("nan"))):
            d = copy.deepcopy(self.d)
            d[section][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                calculate(d)
        for qps in (-1, float("inf"), True):
            with self.assertRaises(ValueError):
                calculate(self.d, qps)

    def test_zero_traffic_keeps_fixed_service_floor(self):
        self.d["traffic"]["daily_users"] = 0
        r = calculate(self.d, 0)
        self.assertEqual(r["model_concurrency"], 0)
        self.assertEqual(r["allocated_tib"], 0)
        self.assertTrue(all(w["count"] == 0 for w in r["workers"]))
        self.assertEqual((r["total_vcpu"], r["total_ram_gib"]), (46, 108))


if __name__ == "__main__":
    unittest.main()
