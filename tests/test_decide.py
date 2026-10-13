import importlib.machinery
import importlib.util
import os
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    loader = importlib.machinery.SourceFileLoader("cswap_priority", os.path.join(ROOT, "bin", "cswap-priority"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("cswap_priority", loader))
    loader.exec_module(mod)
    return mod


def acct(n, five, seven, fable, status="ok", disabled=False, age=0):
    scoped = [] if fable is None else [{"name": "Fable", "pct": fable}]
    a = {
        "number": n,
        "usageStatus": status,
        "usageAgeSeconds": age,
        "usage": {"fiveHour": {"pct": five}, "sevenDay": {"pct": seven}, "scoped": scoped},
    }
    if disabled:
        a["disabled"] = True
    return a


NONE = (None, "no account has headroom")

# (name, accounts, decide() kwargs, expected)
CASES = [
    ("both fresh -> 1 fable", [acct(1, 5, 5, 0), acct(2, 5, 5, 0)], {}, (1, "fable")),
    (
        "stale reading is skipped",
        [acct(1, 25, 53, 64, age=4283), acct(2, 4, 75, 0)],
        {"max_age": 900, "active": 2},
        (2, "fable"),
    ),
    (
        "stale reading ignored while the active account carries on in opus",
        [acct(1, 25, 53, 64, age=4283), acct(2, 4, 75, 100)],
        {"max_age": 900, "active": 2},
        (2, "opus"),
    ),
    ("reading at the age limit still counts", [acct(1, 5, 5, 0, age=900), acct(2, 5, 5, 0)], {"max_age": 900}, (1, "fable")),
    ("missing age is stale when a limit is set", [{**acct(1, 5, 5, 0), "usageAgeSeconds": None}, acct(2, 5, 5, 0)], {"max_age": 900}, (2, "fable")),
    ("1 fable spent -> 2 fable", [acct(1, 20, 60, 100), acct(2, 5, 5, 0)], {}, (2, "fable")),
    ("both fable spent -> 1 opus", [acct(1, 20, 60, 100), acct(2, 5, 5, 100)], {}, (1, "opus")),
    ("1 opus dry on 7d -> 2 opus", [acct(1, 20, 96, 100), acct(2, 5, 5, 100)], {}, (2, "opus")),
    ("1 opus dry on 5h -> 2 opus", [acct(1, 97, 60, 100), acct(2, 5, 5, 100)], {}, (2, "opus")),
    ("all dry -> none", [acct(1, 97, 60, 100), acct(2, 99, 5, 100)], {}, NONE),
    ("1 fable reset -> back to 1", [acct(1, 5, 5, 0), acct(2, 5, 5, 40)], {}, (1, "fable")),
    ("1 5h full, fable ok -> 2", [acct(1, 96, 30, 10), acct(2, 5, 5, 0)], {}, (2, "fable")),
    ("token expired is skipped", [acct(1, 5, 5, 0, status="token_expired"), acct(2, 5, 5, 0)], {}, (2, "fable")),
    ("disabled is skipped", [acct(1, 5, 5, 0, disabled=True), acct(2, 5, 5, 0)], {}, (2, "fable")),
    ("no fable window -> opus", [acct(1, 5, 5, None), acct(2, 5, 5, None)], {}, (1, "opus")),
    ("5h 89 stays under a 90 line", [acct(1, 89, 5, 0), acct(2, 5, 5, 0)], {"threshold_5h": 90, "active": 1}, (1, "fable")),
    ("5h 90 leaves", [acct(1, 90, 5, 0), acct(2, 5, 5, 0)], {"threshold_5h": 90, "active": 1}, (2, "fable")),
    ("5h 91 leaves", [acct(1, 91, 5, 0), acct(2, 5, 5, 0)], {"threshold_5h": 90, "active": 1}, (2, "fable")),
    (
        "on 2, account 1 became eligible again -> stay on 2",
        [acct(1, 88, 15, 11), acct(2, 0, 0, 0)],
        {"threshold_5h": 90, "active": 2},
        (2, "fable"),
    ),
    ("both fresh, on 2 -> stay on 2", [acct(1, 5, 5, 0), acct(2, 5, 5, 0)], {"active": 2}, (2, "fable")),
    (
        "active fable spent but the other has fable room -> move",
        [acct(1, 5, 5, 0), acct(2, 5, 5, 100)],
        {"active": 2},
        (1, "fable"),
    ),
    ("opus phase, on 1 -> stay on 1", [acct(1, 5, 5, 100), acct(2, 5, 5, 100)], {"active": 1}, (1, "opus")),
    ("opus phase, on 2 -> stay on 2", [acct(1, 5, 5, 100), acct(2, 5, 5, 100)], {"active": 2}, (2, "opus")),
    ("active ineligible and nothing else -> none", [acct(1, 95, 5, 0), acct(2, 99, 5, 0)], {"active": 1}, NONE),
    ("explicit order decides when forced to move", [acct(1, 95, 5, 0), acct(2, 5, 5, 0)], {"order": [2, 1], "active": 1}, (2, "fable")),
]


class DecideTest(unittest.TestCase):
    def test_cases(self):
        m = load()
        for name, accounts, kwargs, want in CASES:
            with self.subTest(name):
                self.assertEqual(m.decide(accounts, 95, **kwargs), want)


if __name__ == "__main__":
    unittest.main()
