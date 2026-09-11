import unittest
import tempfile
import os
import app
from app import Factory


class FactoryTest(unittest.TestCase):
    def test_deterministic_generation_and_controls(self):
        left, right = Factory(7), Factory(7)
        left.tick(); right.tick()
        self.assertEqual(left.lines, right.lines)
        left.control("pause"); before = left.sequence; left.tick()
        self.assertEqual(before, left.sequence)
        production=left.streams["production"][-1]["payload"]
        self.assertEqual(production["good_quantity"],production["cumulative_good"])
        self.assertGreater(production["good_quantity"],production["good_increment"])

    def test_incident_and_cursor(self):
        factory = Factory(8); factory.inject("spindle_temperature_failure"); factory.tick()
        self.assertEqual(factory.lines["L01"]["state"], "down")
        self.assertTrue(factory.streams["downtime"])

    def test_explicit_reset_publishes_healthy_recovery_evidence(self):
        factory=Factory(12); factory.inject("spindle_temperature_failure")
        factory.control("reset")
        events=[row["payload"] for row in factory.streams["machine_events"]]
        self.assertEqual(sum(row.get("fault_code")=="RECOVERED" for row in events),2)
        self.assertEqual(sum(row.get("event_type")=="signal.sampled" for row in events),6)

    def test_restart_restores_durable_cursor_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            previous=app.STATE_FILE; app.STATE_FILE=os.path.join(directory,"state.json")
            try:
                factory=Factory(9); factory.tick(); cursor=factory.sequence
                restored=Factory(9)
                self.assertEqual(restored.sequence,cursor)
                self.assertEqual(restored.streams,factory.streams)
                restored.tick()
                self.assertGreater(restored.sequence,cursor)
            finally: app.STATE_FILE=previous

    def test_factory_lab_emits_raw_signals_and_factual_timeline(self):
        factory=Factory(11)
        factory.publish_signals({"asset_id":"asset-ns-01-01","spindle_temperature_c":83.2,
                                 "vibration_mm_s":5.8,"machine_mode":"running"})
        event=factory.streams["machine_events"][-1]
        self.assertEqual(event["payload"]["event_type"],"signal.sampled")
        self.assertNotIn("fault_code",event["payload"])
        factory.start_timeline("bearing_heat_ramp")
        factory.tick()
        self.assertEqual(factory.active_timelines[0]["step"],1)

    def test_accelerated_thirty_minute_soak_has_unique_ordered_events(self):
        factory=Factory(10)
        initial_good=sum(line["good"] for line in factory.lines.values())
        for _ in range(180): factory.tick()
        events=[row for rows in factory.streams.values() for row in rows]
        ids=[row["event_id"] for row in events]
        self.assertEqual(len(ids),len(set(ids)))
        # Output is paced by each line's configured cycle and never fabricated
        # merely because the simulator tick rate is accelerated.
        produced=sum(line["good"] for line in factory.lines.values())-initial_good
        self.assertGreater(produced,0)
        self.assertLessEqual(produced,180*6*2)

    def test_recovery_strategy_emits_source_facts_not_an_outcome_label(self):
        factory=Factory(13)
        factory.inject("spindle_temperature_failure")
        factory.apply_recovery_strategy("repair_asset")
        machine=[row["payload"] for row in factory.streams["machine_events"]]
        maintenance=[row["payload"] for row in factory.streams["maintenance"]]
        self.assertTrue(any(row.get("event_type")=="signal.sampled" for row in machine))
        self.assertTrue(any(row.get("status")=="completed" for row in maintenance))
        self.assertFalse(any("recovered" in row for row in machine))

    def test_versioned_lab_run_is_deterministic_and_keeps_assertions_separate(self):
        factory=Factory(14)
        factory.control("pause")
        run=factory.start_lab_run("gradual_machine_degradation",8124)
        self.assertTrue(factory.running)
        self.assertEqual(run["status"],"running")
        factory.tick()
        self.assertEqual(run["scenario_version"],1)
        self.assertEqual(run["seed"],8124)
        self.assertTrue(run["assertions"])
        self.assertNotIn("assertions",factory.streams["machine_events"][-1])
        self.assertEqual(factory.lab.current()["id"],run["id"])

    def test_step_pauses_and_resume_restores_continuous_mode(self):
        factory=Factory(140)
        factory.start_lab_run("healthy_shift",8124)
        factory.lab_control("step")
        self.assertFalse(factory.running)
        self.assertEqual(factory.lab.current()["status"],"paused")
        before=factory.sequence
        factory.tick()
        self.assertEqual(factory.sequence,before)
        factory.lab_control("resume")
        self.assertTrue(factory.running)
        self.assertEqual(factory.lab.current()["status"],"running")
        factory.tick()
        self.assertGreater(factory.sequence,before)

    def test_lab_fork_preserves_parent_and_chaos_is_bounded(self):
        factory=Factory(15); run=factory.start_lab_run("healthy_shift",99); factory.tick()
        event=factory.lab.current()["events"][-1]
        child=factory.lab.fork(event["id"],factory.scenario_time.isoformat())
        self.assertEqual(child["parent_run_id"],run["id"])
        config=factory.lab.chaos({"event_loss_percent":90,"network_latency_ms":9000})
        self.assertEqual(config["event_loss_percent"],20)
        self.assertEqual(config["network_latency_ms"],5000)

    def test_source_native_contract_fixtures_do_not_contain_product_outcomes(self):
        factory=Factory(16); factory.start_lab_run("source_conflict",8124)
        events=factory.lab.current()["events"]
        self.assertTrue(any(row["source_system"]=="mqtt" for row in events))
        self.assertFalse(any("recommended_strategy" in row["payload"] for row in events))


if __name__ == "__main__": unittest.main()
