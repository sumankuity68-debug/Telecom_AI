"""
Phase C — Comprehensive Agent Intelligence Test Suite:
- TEST 1: Network Diagnostics (get_network_diagnostics)
- TEST 2: Deterministic Health Scoring (calculate_network_health & classify_network_quality)
- TEST 3: Anomaly Detection (detect_network_anomaly under normal & degraded conditions)
- TEST 4: Plan Recommendation (recommend_plans based on usage analytics)
- TEST 5: Bill Analysis (analyze_bill matching actual backend data)
- TEST 6: Outage Correlation (correlate_outage linking subscriber & NOC incidents)
- TEST 7: Agent Integration (ask_telecom_agent routing & grounded intelligence)
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from diagnostics import (
    get_network_diagnostics,
    calculate_network_health,
    classify_network_quality,
)
from anomaly_detection import detect_network_anomaly
from recommendations import recommend_plans
from billing_analysis import analyze_bill
from outage_correlation import correlate_outage
from agent import ask_telecom_agent, detect_intent
from tools import search_plans


class TestPhaseCAgentIntelligence(unittest.TestCase):

    def test_01_network_diagnostics(self):
        """TEST 1: Network diagnostics for CUST001 returns Kolkata network information."""
        diag = get_network_diagnostics(customer_id="CUST001")
        self.assertIsInstance(diag, dict)
        self.assertEqual(diag.get("customer_id"), "CUST001")
        self.assertEqual(diag.get("location"), "Kolkata")
        self.assertIn("tower_id", diag)
        self.assertIn("health_score", diag)
        self.assertIn("download_mbps", diag)
        self.assertIn("latency_ms", diag)
        self.assertIn("packet_loss_percent", diag)
        self.assertIn("quality", diag)

    def test_02_health_score_deterministic(self):
        """TEST 2: Health score is numeric, deterministic, and bounded [0, 100]."""
        # Test 1: Ideal / Healthy metrics
        score_healthy = calculate_network_health(
            download_mbps=95.0,
            upload_mbps=25.0,
            latency_ms=20.0,
            packet_loss_percent=0.2,
            signal_strength_dbm=-68.0,
        )
        self.assertIsInstance(score_healthy, int)
        self.assertEqual(score_healthy, 100)
        self.assertEqual(classify_network_quality(score_healthy), "Excellent")

        # Test 2: Severely Degraded metrics
        score_degraded = calculate_network_health(
            download_mbps=8.0,
            upload_mbps=2.0,
            latency_ms=180.0,
            packet_loss_percent=15.0,
            signal_strength_dbm=-95.0,
        )
        self.assertIsInstance(score_degraded, int)
        self.assertEqual(score_degraded, 10)  # Minimum boundary score
        self.assertEqual(classify_network_quality(score_degraded), "Poor")

        # Test 3: Consistency
        self.assertEqual(
            calculate_network_health(50, 12, 45, 1.5, -78),
            calculate_network_health(50, 12, 45, 1.5, -78),
        )

    def test_03_anomaly_detection_normal_and_degraded(self):
        """TEST 3: Anomaly detection distinguishes normal vs degraded network telemetry."""
        # Case A: Normal network telemetry (Tower T001)
        normal_metrics = {
            "download_mbps": 92.0,
            "upload_mbps": 18.0,
            "latency_ms": 24.0,
            "packet_loss_percent": 0.8,
            "signal_strength_dbm": -72.0,
            "active_users": 420,
        }
        res_normal = detect_network_anomaly(normal_metrics)
        self.assertIsInstance(res_normal, dict)
        self.assertFalse(res_normal["is_anomaly"])
        self.assertGreater(res_normal["anomaly_score"], 0)
        self.assertEqual(res_normal["severity"], "normal")

        # Case B: Degraded network telemetry (Tower T002)
        degraded_metrics = {
            "download_mbps": 18.0,
            "upload_mbps": 5.0,
            "latency_ms": 178.0,
            "packet_loss_percent": 12.4,
            "signal_strength_dbm": -91.0,
            "active_users": 890,
        }
        res_degraded = detect_network_anomaly(degraded_metrics)
        self.assertIsInstance(res_degraded, dict)
        self.assertTrue(res_degraded["is_anomaly"])
        self.assertLess(res_degraded["anomaly_score"], 0)
        self.assertEqual(res_degraded["severity"], "high")
        self.assertGreater(len(res_degraded["reasons"]), 0)
        self.assertIn("Very high latency", res_degraded["reasons"])
        self.assertIn("Severe packet loss", res_degraded["reasons"])

    def test_04_plan_recommendation(self):
        """TEST 4: Recommendations are grounded on customer usage and valid plan catalog."""
        recs = recommend_plans("CUST001")
        self.assertIsInstance(recs, dict)
        self.assertEqual(recs["customer_id"], "CUST001")
        self.assertIn("current_plan", recs)
        self.assertIn("usage_summary", recs)
        self.assertIn("recommendations", recs)
        self.assertGreater(len(recs["recommendations"]), 0)

        # Verify all recommended plans exist in actual catalog
        all_plans = search_plans()
        valid_plan_ids = [p["plan_id"] for p in all_plans]

        for item in recs["recommendations"]:
            self.assertIn(item["plan_id"], valid_plan_ids)
            self.assertNotEqual(item["plan_id"], recs["current_plan"]["plan_id"])
            self.assertIn("reason", item)
            self.assertIn("estimated_monthly_difference", item)
            self.assertIsInstance(item["estimated_monthly_difference"], (int, float))

    def test_05_bill_analysis(self):
        """TEST 5: Bill calculations match backend financial data."""
        bill_data = analyze_bill("CUST001")
        self.assertIsInstance(bill_data, dict)
        self.assertEqual(bill_data["customer_id"], "CUST001")
        self.assertEqual(bill_data["bill_id"], "B001")
        self.assertEqual(bill_data["base_plan"], 799.0)
        self.assertEqual(bill_data["taxes"], 143.82)
        self.assertEqual(bill_data["total_amount"], 942.82)
        self.assertEqual(bill_data["status"], "paid")

        # Verify arithmetic correctness
        computed = round(bill_data["base_plan"] + bill_data["addon_charges"] + bill_data["roaming_charges"] + bill_data["taxes"], 2)
        self.assertEqual(bill_data["total_amount"], computed)
        self.assertGreater(len(bill_data["analysis"]), 0)

    def test_06_outage_correlation(self):
        """TEST 6: Active outage correctly correlates with location and degraded tower."""
        corr = correlate_outage("CUST001")
        self.assertIsInstance(corr, dict)
        self.assertEqual(corr["customer_id"], "CUST001")
        self.assertEqual(corr["location"], "Kolkata")
        self.assertTrue(corr["outage_detected"])
        self.assertEqual(corr["outage_id"], "OUT001")
        self.assertEqual(corr["tower_id"], "T002")
        self.assertEqual(corr["correlation"], "high")
        self.assertIn("Backhaul congestion", corr["reason"])
        self.assertIn("correlated with an active outage", corr["explanation"])

    def test_07_agent_integration_routing(self):
        """TEST 7: Verify agent classifies queries into correct intelligence pipelines."""
        # 1. Slow internet query
        self.assertEqual(detect_intent("My internet is very slow CUST001"), "network_intelligence")
        # 2. Plan inquiry query
        self.assertEqual(detect_intent("Which plan should I use? CUST001"), "recommend_plan")
        # 3. Bill inquiry query
        self.assertEqual(detect_intent("Why is my bill high? CUST001"), "bill_analysis")
        # 4. Outage inquiry query
        self.assertEqual(detect_intent("Is there an outage in my area? CUST001"), "outage")
        # 5. Anomaly inquiry query
        self.assertEqual(detect_intent("Is my network abnormal?"), "anomaly")

        # Verify agent execution with metadata payload
        res = ask_telecom_agent("My internet is slow CUST001", return_metadata=True)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["intent"], "network_intelligence")
        self.assertIn("answer", res)
        self.assertIn("tool_result", res)
        self.assertIn("diagnostics", res["tool_result"])
        self.assertIn("anomaly_analysis", res["tool_result"])
        self.assertIn("outage_correlation", res["tool_result"])


if __name__ == "__main__":
    unittest.main()
