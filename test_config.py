"""
Tests for configuration: the defaults the documentation promises, and how the
environment changes them.

``config.py`` reads the environment when it is imported, so each case imports
a copy of it in a fresh interpreter, from a directory with no ``.env`` file.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))

# Variables that are documented without a default worth comparing.
NOT_COMPARED = {"TOKEN", "STOCKFISH_PATH"}

DUMP = """
import json, config
values = {name: getattr(config, name) for name in dir(config) if name.isupper()}
print(json.dumps(values, default=str))
"""


def load_config(**env):
    """Import config.py in a clean interpreter and return its upper-case names."""
    directory = tempfile.mkdtemp()
    try:
        for module in MODULES_WITH_SETTINGS:
            shutil.copy(os.path.join(ROOT, module), directory)
        engine = os.path.join(directory, "engine")
        with open(engine, "w") as f:
            f.write("#!/bin/sh\n")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "TOKEN": "test-token",
            "STOCKFISH_PATH": engine,       # any existing file: config only looks for it
            **{key: str(value) for key, value in env.items()},
        }
        result = subprocess.run([sys.executable, "-c", DUMP], cwd=directory, env=environment,
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip().splitlines()[-1])
        return json.loads(result.stdout)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def documented_defaults():
    """Variables in .env.example with the value each commented-out example shows."""
    documented = {}
    with open(os.path.join(ROOT, ".env.example")) as f:
        for line in f:
            match = re.match(r'^#?\s*([A-Z][A-Z0-9_]+)=(.*)$', line.strip())
            if match:
                documented[match.group(1)] = match.group(2).strip().strip('"')
    return documented


# Every module that takes settings from the environment.
MODULES_WITH_SETTINGS = ("config.py",)


def variables_read_by_config():
    names = set()
    for module in MODULES_WITH_SETTINGS:
        with open(os.path.join(ROOT, module)) as f:
            names |= set(re.findall(r'os\.getenv\("([A-Z0-9_]+)"', f.read()))
    return names


class TestDocumentedDefaults(unittest.TestCase):
    """.env.example is the reference for every setting, so it has to match the code."""

    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.documented = documented_defaults()

    def actual(self, name):
        engine_options = {"SF_THREADS": "Threads", "SF_HASH": "Hash", "SF_MOVE_OVERHEAD": "Move Overhead"}
        if name in engine_options:
            return self.config["UCI_OPTIONS"][engine_options[name]]
        if name == "SF_SYZYGY_PATH":
            return "./syzygy"       # read and used at import time, not kept under that name
        return self.config[name]

    def test_every_variable_the_code_reads_is_documented(self):
        missing = variables_read_by_config() - set(self.documented)
        self.assertEqual(missing, set(), "read by the code but absent from .env.example")

    def test_nothing_is_documented_that_the_code_does_not_read(self):
        extra = set(self.documented) - variables_read_by_config()
        self.assertEqual(extra, set(), "in .env.example but never read by the code")

    def test_every_documented_default_is_the_real_default(self):
        for name, shown in sorted(self.documented.items()):
            if name in NOT_COMPARED:
                continue
            with self.subTest(variable=name):
                actual = self.actual(name)
                if isinstance(actual, bool):
                    self.assertEqual(shown, str(actual).lower())
                elif isinstance(actual, float):
                    self.assertEqual(float(shown), actual)
                else:
                    self.assertEqual(shown, str(actual))

    def test_the_default_challenge_rate_stays_under_the_daily_limit_lichess_enforces(self):
        self.assertLess(self.config["MAX_CHALLENGES_PER_DAY"], 200)
        self.assertLessEqual(self.config["MAX_CHALLENGES_PER_HOUR"] * 24, self.config["MAX_CHALLENGES_PER_DAY"])


class TestEnvironmentOverrides(unittest.TestCase):
    def test_numbers_are_read_from_the_environment(self):
        config = load_config(SF_THREADS=2, SF_HASH=256, MAX_CONCURRENT_GAMES=1, MAX_CHALLENGES_PER_HOUR=7,
                             MAX_CHALLENGES_PER_DAY=150, MOVETIME_CLOCK_SAFETY="0.5")

        self.assertEqual(config["UCI_OPTIONS"]["Threads"], 2)
        self.assertEqual(config["UCI_OPTIONS"]["Hash"], 256)
        self.assertEqual(config["MAX_CONCURRENT_GAMES"], 1)
        self.assertEqual(config["MAX_CHALLENGES_PER_HOUR"], 7)
        self.assertEqual(config["MAX_CHALLENGES_PER_DAY"], 150)
        self.assertEqual(config["MOVETIME_CLOCK_SAFETY"], 0.5)

    def test_switches_accept_the_usual_spellings(self):
        for value, expected in (("false", False), ("0", False), ("no", False), ("true", True), ("1", True), ("YES", True)):
            with self.subTest(value=value):
                config = load_config(ENABLE_AUTO_CHALLENGE=value, DYNAMIC_STRENGTH=value)
                self.assertIs(config["ENABLE_AUTO_CHALLENGE"], expected)
                self.assertIs(config["DYNAMIC_STRENGTH"], expected)

    def test_a_missing_token_stops_the_import(self):
        with self.assertRaises(RuntimeError) as caught:
            load_config(TOKEN="")

        self.assertIn("TOKEN", str(caught.exception))

    def test_the_strength_limit_is_left_to_the_bot(self):
        """UCI_LimitStrength is set per opponent, so the base options keep it off."""
        self.assertIs(load_config()["UCI_OPTIONS"]["UCI_LimitStrength"], False)


class TestTablebaseDetection(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def touch(self, name):
        open(os.path.join(self.directory, name), "w").close()

    def test_a_directory_with_tablebase_files_is_handed_to_the_engine(self):
        self.touch("KQvK.rtbw")
        self.touch("KQvK.rtbz")

        config = load_config(SF_SYZYGY_PATH=self.directory)

        self.assertEqual(config["UCI_OPTIONS"]["SyzygyPath"], self.directory)

    def test_a_directory_without_tablebase_files_is_ignored(self):
        self.touch("README.md")

        self.assertNotIn("SyzygyPath", load_config(SF_SYZYGY_PATH=self.directory)["UCI_OPTIONS"])

    def test_a_missing_directory_is_ignored(self):
        missing = os.path.join(self.directory, "nowhere")

        self.assertNotIn("SyzygyPath", load_config(SF_SYZYGY_PATH=missing)["UCI_OPTIONS"])

    def test_the_default_directory_is_optional(self):
        self.assertNotIn("SyzygyPath", load_config()["UCI_OPTIONS"])


if __name__ == "__main__":
    unittest.main()
