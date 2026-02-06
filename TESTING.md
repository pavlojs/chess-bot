# Testing Guide

## Running Tests

This project includes comprehensive unit tests using pytest.

### Prerequisites

Install test dependencies:
```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest
```

### Run Tests with Verbose Output

```bash
pytest -v
```

### Run Tests with Coverage Report

```bash
pytest --cov=bot --cov=logging_config
```

### Run Specific Test Class

```bash
pytest test_bot.py::TestChallengeAcceptance -v
```

### Run Specific Test

```bash
pytest test_bot.py::TestChallengeAcceptance::test_accept_challenge_valid_rating_and_timecontrol -v
```

### Generate HTML Coverage Report

```bash
pytest --cov=bot --cov=logging_config --cov-report=html
```

Coverage report will be generated in `htmlcov/index.html`

## Test Coverage

Current test coverage includes:

### Challenge Acceptance Tests (9 tests)
- ✅ Valid challenges (correct rating and time control)
- ✅ Challenges with rating too low
- ✅ Challenges with rating too high  
- ✅ Challenges with unsupported time controls
- ✅ Challenges with classical time control
- ✅ Behavior when challenges are disabled
- ✅ Handling of missing rating data
- ✅ Rejection of correspondence challenges
- ✅ Rejection of unlimited time challenges

### Board State Tests (5 tests)
- ✅ Board initialization
- ✅ Single move application
- ✅ Multiple move sequencing
- ✅ Invalid move rejection
- ✅ Game over detection (checkmate)

### Stockfish Initialization Tests (2 tests)
- ✅ Successful initialization
- ✅ UCI_LimitStrength for weak opponents (< 1800 ELO)
- ✅ Full strength for strong opponents (≥ 1800 ELO)

### Move Time Calculation Tests (4 tests)
- ✅ Full thinking time for strong opponents (≥ 2200 ELO)
- ✅ Minimum time for weak opponents (< 1800 ELO, UCI_LimitStrength handles fairness)
- ✅ Scaled time for intermediate opponents (1800-2199 ELO)
- ✅ Consistent time when dynamic strength is disabled

### Stockfish Updater Tests (3 tests)
- ✅ Binary name detection (platform-specific)
- ✅ Version detection from installed binary
- ✅ Latest release info retrieval from GitHub API

### Logging Tests (1 test)
- ✅ Logger configuration and handler setup

**Total: 25 tests, 100% pass rate**

## Continuous Integration

Run the test suite before committing:

```bash
pytest && git add .
```

## Test Structure

Tests are organized in `test_bot.py` with separate test classes for different functionality:

```python
class TestChallengeAcceptance(unittest.TestCase)    # 9 tests
class TestBoardState(unittest.TestCase)              # 5 tests
class TestStockfishInitialization(unittest.TestCase) # 2 tests
class TestMoveTimeCalculation(unittest.TestCase)     # 4 tests (HYBRID)
class TestStockfishUpdater(unittest.TestCase)        # 3 tests
class TestLogging(unittest.TestCase)                 # 1 test
```

## Mocking

Tests use `unittest.mock` to mock external dependencies:
- Lichess API calls
- Stockfish engine
- Configuration values

This allows tests to run without requiring actual API credentials or engine binaries.

## Performance

All tests complete in under 1 second.

## Future Test Improvements

Planned enhancements:
- Integration tests with mock Lichess API
- Async game simulation tests
- Performance benchmarking
- Game state recovery tests
- Error scenario testing
