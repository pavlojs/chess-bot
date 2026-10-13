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
import json, config, logging_config
values = {name: getattr(module, name) for module in (config, logging_config) for name in dir(module) if name.isupper()}
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
MODULES_WITH_SETTINGS = ("config.py", "logging_config.py")


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
                elif isinstance(actual, list):
                    self.assertEqual(shown.split(","), actual)
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

    def test_accepted_ratings_and_speeds_are_read_from_the_environment(self):
        config = load_config(MIN_RATING=1500, MAX_RATING=2400, TIME_CONTROL="blitz, Rapid")

        self.assertEqual((config["MIN_RATING"], config["MAX_RATING"]), (1500, 2400))
        self.assertEqual(config["TIME_CONTROL"], ["blitz", "rapid"])

    def test_the_whole_range_of_lichess_ratings_is_allowed(self):
        config = load_config(MIN_RATING=400, MAX_RATING=4000)

        self.assertEqual((config["MIN_RATING"], config["MAX_RATING"]), (400, 4000))

    def test_a_single_rating_is_a_range(self):
        config = load_config(MIN_RATING=2000, MAX_RATING=2000)

        self.assertEqual((config["MIN_RATING"], config["MAX_RATING"]), (2000, 2000))

    def test_a_rating_range_lichess_ratings_cannot_fall_in_stops_the_import(self):
        for bad in ({"MIN_RATING": 399}, {"MAX_RATING": 4001}, {"MIN_RATING": 2500, "MAX_RATING": 2400}):
            with self.subTest(**bad):
                with self.assertRaises(RuntimeError) as caught:
                    load_config(**bad)
                self.assertIn("MIN_RATING", str(caught.exception))

    def test_every_speed_and_none_at_all_are_both_allowed(self):
        self.assertEqual(load_config(TIME_CONTROL="classical")["TIME_CONTROL"], ["classical"])
        self.assertEqual(load_config(TIME_CONTROL="bullet,blitz,rapid,classical")["TIME_CONTROL"],
                         ["bullet", "blitz", "rapid", "classical"])
        self.assertEqual(load_config(TIME_CONTROL="")["TIME_CONTROL"], [])

    def test_the_speeds_in_the_example_file_are_the_ones_the_bot_names(self):
        """The table of speeds in .env.example has to agree with how the bot classifies a clock."""
        os.environ.setdefault("TOKEN", "test_token_for_testing")
        from bot import determine_time_category
        with open(os.path.join(ROOT, ".env.example")) as f:
            rows = re.findall(r"^#\s+(bullet|blitz|rapid|classical)\s+.*?((?:\d+\+\d+(?:, )?)+)$", f.read(), re.M)
        self.assertEqual([speed for speed, _ in rows], ["bullet", "blitz", "rapid", "classical"])
        for speed, examples in rows:
            for clock in examples.split(", "):
                minutes, increment = map(int, clock.split("+"))
                self.assertEqual(determine_time_category(minutes * 60, increment), speed, clock)

    def test_a_speed_that_does_not_exist_stops_the_import(self):
        with self.assertRaises(RuntimeError) as caught:
            load_config(TIME_CONTROL="blitz,hyperbullet")

        self.assertIn("hyperbullet", str(caught.exception))

    def test_the_engine_is_not_installed_behind_the_users_back(self):
        """The self-updater downloads a binary and may ask for sudo: only when asked for."""
        self.assertIs(load_config()["AUTO_UPDATE_STOCKFISH"], False)
        self.assertIs(load_config(AUTO_UPDATE_STOCKFISH="true")["AUTO_UPDATE_STOCKFISH"], True)

    def test_a_missing_token_stops_the_import(self):
        with self.assertRaises(RuntimeError) as caught:
            load_config(TOKEN="")

        self.assertIn("TOKEN", str(caught.exception))

    def test_the_strength_limit_is_left_to_the_bot(self):
        """UCI_LimitStrength is set per opponent, so the base options keep it off."""
        self.assertIs(load_config()["UCI_OPTIONS"]["UCI_LimitStrength"], False)


class TestLogFile(unittest.TestCase):
    """The log file on the volume has a ceiling."""

    def setUp(self):
        import logging
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.previous = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, self.previous)
        self.logging = logging

    def logger(self, name, max_bytes, backups):
        from unittest.mock import patch
        import logging_config
        with patch.object(logging_config, "LOG_FILE_MAX_BYTES", max_bytes), \
             patch.object(logging_config, "LOG_FILE_BACKUPS", backups):
            logger = logging_config.setup_logger(name)
        for handler in logger.handlers:
            self.addCleanup(handler.close)
            if isinstance(handler, self.logging.StreamHandler) and not hasattr(handler, "baseFilename"):
                handler.setLevel(self.logging.CRITICAL + 1)      # keep the test output quiet
        return logger

    def test_defaults_are_ten_megabytes_and_five_older_files(self):
        config = load_config()

        self.assertEqual(config["LOG_FILE_MAX_BYTES"], 10 * 1024 * 1024)
        self.assertEqual(config["LOG_FILE_BACKUPS"], 5)

    def test_the_limits_can_be_set_from_the_environment(self):
        config = load_config(LOG_FILE_MAX_MB=2, LOG_FILE_BACKUPS=1)

        self.assertEqual(config["LOG_FILE_MAX_BYTES"], 2 * 1024 * 1024)
        self.assertEqual(config["LOG_FILE_BACKUPS"], 1)

    def test_the_directory_never_grows_past_its_ceiling(self):
        max_bytes, backups = 2000, 2
        logger = self.logger("test_log_ceiling", max_bytes, backups)

        for number in range(2000):
            logger.debug("line %05d of a log that keeps growing", number)

        files = sorted(os.listdir("logs"))
        self.assertEqual(files, ["axiom_bot.log", "axiom_bot.log.1", "axiom_bot.log.2"])
        total = sum(os.path.getsize(os.path.join("logs", name)) for name in files)
        self.assertLessEqual(total, max_bytes * (backups + 1))

    def test_the_newest_lines_are_the_ones_kept(self):
        logger = self.logger("test_log_newest", 2000, 1)

        for number in range(500):
            logger.debug("line %05d", number)

        with open(os.path.join("logs", "axiom_bot.log")) as f:
            self.assertIn("line 00499", f.read())

    def test_debug_goes_to_the_file_and_names_where_it_came_from(self):
        logger = self.logger("test_log_detail", 100000, 1)

        logger.debug("a detail")

        with open(os.path.join("logs", "axiom_bot.log")) as f:
            line = f.read()
        self.assertIn("DEBUG", line)
        self.assertIn("test_debug_goes_to_the_file_and_names_where_it_came_from", line)


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
