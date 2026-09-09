from dataclasses import replace
import unittest
from fulfilment.model import Config, overlap, simulate
from fulfilment.experiment import experiment, interval


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(warmup=20, horizon=200)

    def test_overlap_at_both_boundaries(self):
        self.assertEqual(overlap(5, 25, 10, 20), 10)
        self.assertEqual(overlap(1, 5, 10, 20), 0)
        self.assertEqual(overlap(15, 25, 10, 20), 5)

    def test_reproducible(self):
        self.assertEqual(simulate(self.config, 7), simulate(self.config, 7))

    def test_common_inputs_survive_staffing_change(self):
        a = simulate(self.config, 7)["orders"]
        b = simulate(replace(self.config, pickers=4), 7)["orders"]
        for x,y in zip(a,b):
            for key in ["arrival", "express", "pick_service", "pack_service"]:
                self.assertEqual(x[key], y[key])
        self.assertEqual(len(a), len(b))

    def test_every_order_collected_in_correct_sequence(self):
        result = simulate(self.config)
        for o in result["orders"]:
            self.assertLessEqual(o["arrival"], o["pick_start"])
            self.assertLessEqual(o["pick_end"], o["pack_start"])
            self.assertLessEqual(o["pack_end"], o["collected"])
            self.assertAlmostEqual(o["collected"] % self.config.courier_interval, 0)

    def test_total_time_includes_courier(self):
        m = simulate(self.config)["metrics"]
        self.assertAlmostEqual(m["mean_total_time"], m["mean_processing_time"]+m["mean_courier_wait"])

    def test_utilisation_and_probabilities_bounded(self):
        for seed in range(5):
            m = simulate(self.config,seed)["metrics"]
            for key in ["picker_utilisation", "packer_utilisation", "express_wait_over_6", "empty_courier_fraction"]:
                self.assertLessEqual(m[key], 1)
                self.assertGreaterEqual(m[key], 0)

    def test_missing_express_is_missing_not_zero(self):
        self.assertIsNone(simulate(replace(self.config,express_share=0))["metrics"]["express_wait_over_6"])

    def test_invalid_configuration(self):
        for kw in [{"pickers":0}, {"pickers":1.5}, {"warmup":6000}, {"arrival_rate":float('nan')}, {"express_share":2}]:
            with self.assertRaises(ValueError):
                Config(**kw)

    def test_overloaded_system_drains_without_dropping_orders(self):
        r = simulate(replace(self.config, pickers=1))
        self.assertGreater(r["offered_load"]["picking"],1)
        self.assertGreater(r["metrics"]["drain_duration"],0)
        self.assertTrue(all("collected" in o for o in r["orders"]))

    def test_utilisation_matches_summed_service_when_window_covers_it(self):
        r = simulate(Config(warmup=0,horizon=1000,arrival_rate=.01), 2)
        expected = sum(overlap(o["pick_start"],o["pick_end"],0,1000) for o in r["orders"])/3000
        self.assertAlmostEqual(r["metrics"]["picker_utilisation"],expected)

    def test_confidence_interval(self):
        ci = interval([1,2,3,4,5])
        self.assertAlmostEqual(ci["mean"],3)
        self.assertAlmostEqual(ci["low"],1.03675684,places=6)
        self.assertIsNone(interval([1])["low"])

    def test_paired_comparisons_and_faster_collection(self):
        report = experiment(3,2025,self.config)
        self.assertEqual(len(report["runs"]),15)
        d = report["paired_differences_from_baseline"]["faster_courier"]["mean_total_time"]
        self.assertLess(d["mean"],0)
        self.assertEqual(d["n"],3)


if __name__ == '__main__':
    unittest.main()
