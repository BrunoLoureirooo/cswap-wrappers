import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "bin", "cswap-priority")
FAKE = os.path.join(HERE, "fake_cswap")

# account number -> [5h pct, 7d pct, fable pct]
OK = {"1": [5, 5, 0], "2": [5, 5, 0]}
TWO_SPENT = {"1": [5, 20, 0], "2": [100, 5, 4]}
BOTH_SPENT = {"1": [100, 20, 33], "2": [100, 5, 4]}


def payload(session):
    return json.dumps({"hook_event_name": "StopFailure", "session_id": session, "error": "rate_limit"})


class Harness(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.home = os.path.join(self.dir, "home")
        os.makedirs(os.path.join(self.home, ".cache"))
        os.makedirs(os.path.join(self.dir, "bin"))
        os.symlink(FAKE, os.path.join(self.dir, "bin", "cswap"))

    def run_script(self, active, usage, *args, stdin=""):
        with open(os.path.join(self.dir, "active"), "w") as f:
            f.write(str(active))
        with open(os.path.join(self.dir, "scen.json"), "w") as f:
            json.dump(usage, f)
        env = dict(os.environ, HOME=self.home, FX=self.dir, PATH=os.path.join(self.dir, "bin") + os.pathsep + os.environ["PATH"])
        start = time.time()
        p = subprocess.run([sys.executable, "-I", SCRIPT, *args], input=stdin, env=env, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stderr, time.time() - start

    def calls(self):
        try:
            with open(os.path.join(self.dir, "calls")) as f:
                return f.read().split()
        except OSError:
            return []

    def set_swap(self, age):
        with open(os.path.join(self.home, ".cache", "cswap-priority.swap"), "w") as f:
            json.dump({"ts": time.time() - age, "from": 2, "to": 1}, f)


class SingleTick(Harness):
    def test_5h_below_the_90_line_stays(self):
        self.run_script(1, {"1": [89, 5, 0], "2": [5, 5, 0]})
        self.assertEqual(self.calls(), [])

    def test_5h_at_the_90_line_leaves(self):
        self.run_script(1, {"1": [90, 5, 0], "2": [5, 5, 0]})
        self.assertEqual(self.calls(), ["2"])

    def test_stays_when_the_other_account_becomes_eligible_again(self):
        self.run_script(2, {"1": [88, 15, 11], "2": [0, 0, 0]})
        self.assertEqual(self.calls(), [])

    def test_no_hop_to_account_1_when_both_are_fresh(self):
        self.run_script(2, OK)
        self.assertEqual(self.calls(), [])


class Revive(Harness):
    ARGS = ("--revive", "--settle", "2", "--budget", "5")

    def test_swaps_and_wakes_with_a_resume_instruction(self):
        rc, err, _ = self.run_script(2, TWO_SPENT, *self.ARGS, stdin=payload("a"))
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls(), ["1"])
        self.assertIn("switched (2 -> 1)", err)
        self.assertIn("SendMessage", err)

    def test_cooldown_blocks_a_second_wake_of_the_same_session(self):
        self.run_script(2, TWO_SPENT, *self.ARGS, stdin=payload("a"))
        rc, _, _ = self.run_script(1, TWO_SPENT, *self.ARGS, stdin=payload("a"))
        self.assertEqual(rc, 0)

    def test_other_session_failing_just_after_the_swap_is_woken(self):
        self.set_swap(3)
        rc, _, _ = self.run_script(1, TWO_SPENT, "--revive", "--settle", "8", "--budget", "5", stdin=payload("b"))
        self.assertEqual(rc, 2)

    def test_both_spent_does_not_wake(self):
        rc, _, _ = self.run_script(2, BOTH_SPENT, "--revive", "--settle", "2", "--budget", "3", stdin=payload("c"))
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls(), [])

    def test_failure_without_a_swap_on_record_does_not_wake(self):
        with open(os.path.join(self.home, ".cache", "cswap-priority.swap"), "w") as f:
            json.dump({"ts": 1, "from": 2, "to": 1}, f)
        rc, _, _ = self.run_script(1, OK, *self.ARGS, stdin=payload("d"))
        self.assertEqual(rc, 0)

    def test_swap_older_than_the_keychain_cache_does_not_explain_the_failure(self):
        self.set_swap(40)
        rc, _, _ = self.run_script(1, TWO_SPENT, *self.ARGS, stdin=payload("e"))
        self.assertEqual(rc, 0)

    def test_empty_payload_still_wakes(self):
        rc, _, _ = self.run_script(2, TWO_SPENT, "--revive", "--settle", "1", "--budget", "5", stdin="")
        self.assertEqual(rc, 2)

    def test_wait_counts_from_the_swap_when_the_swap_came_first(self):
        self.set_swap(2)
        rc, _, elapsed = self.run_script(1, TWO_SPENT, "--revive", "--settle", "5", "--budget", "5", stdin=payload("f"))
        self.assertEqual(rc, 2)
        self.assertTrue(2.0 <= elapsed <= 4.5, elapsed)

    def test_wait_counts_from_the_failure_when_the_hook_does_the_swap(self):
        rc, _, elapsed = self.run_script(2, TWO_SPENT, "--revive", "--settle", "4", "--budget", "5", stdin=payload("g"))
        self.assertEqual(rc, 2)
        self.assertTrue(3.5 <= elapsed <= 6.0, elapsed)


if __name__ == "__main__":
    unittest.main()
