# Changelog

All notable changes to Axiom Chess Bot are documented in this file.

## [2.1.2] - 2026-02-18

### New Features

#### ⚡ Bullet Game Support
- **Added**: Full support for bullet time controls (1+0, 1+1, 2+1)
- **Added**: Bullet games to `CHALLENGE_TIME_CONTROLS` for auto-challenging
- **Improved**: Bot now handles ultra-fast games professionally

#### ⏱️ Intelligent Time Management
- **Added**: Dynamic time management to prevent losses on time
- **Added**: Emergency mode for critical time situations (≤20 seconds remaining)
- **Added**: Moderate time pressure handling (20-60 seconds remaining)
- **Smart**: Automatically adjusts thinking time based on remaining clock
- **Balanced**: Maintains minimum 300ms move quality even in time pressure
- **Optimal**: Uses 60% of available time budget in emergency situations

**Time Management Thresholds:**
- **Critical (≤20s)**: Emergency mode - very fast moves (min 300ms)
- **Moderate (20-60s)**: Conservative time usage (min 500ms)
- **Normal (>60s)**: Standard opponent-based calculation

**Technical Details:**
- Tracks `wtime`/`btime` and `winc`/`binc` from game state
- Estimates ~20 moves remaining for time budgeting
- Accounts for increment in time pressure calculations
- Minimal impact on playing strength (smart minimums)

## [2.1.1] - 2026-02-13

### Bug Fixes & Improvements

#### 🔧 Auto-Challenge System Fixes
- **Fixed**: Auto-challenge now runs in separate background thread, no longer blocks event stream
- **Fixed**: Challenge checking now works reliably every `CHALLENGE_CHECK_INTERVAL` seconds
- **Fixed**: Bot correctly distinguishes between incoming and outgoing challenges
- **Fixed**: Graceful handling of 404 errors when challenges are canceled
- **Improved**: Uses berserk's built-in `client.bots.get_online_bots()` method

#### 🛑 Graceful Shutdown Improvements
- **Fixed**: Ctrl+C now properly shuts down the bot within 2 seconds
- **Added**: Press Ctrl+C twice for immediate force exit
- **Improved**: Better cleanup of background threads on shutdown

#### 📝 Documentation Updates
- **Updated**: README with background thread information for auto-challenging
- **Updated**: README with graceful shutdown instructions
- **Added**: Environment variable examples for aggressive challenging strategies

**Example Configuration for Active Play:**
```bash
MAX_CHALLENGES_PER_HOUR=40      # Up from default 3
CHALLENGE_CHECK_INTERVAL=90     # Check every 90 seconds instead of 5 minutes
```

## [2.1.0] - 2026-02-10

### Strength Balance Improvements

#### 🎯 Rebalanced ELO Thresholds for Better Challenge

**Changes:**
- **LIMIT_STRENGTH_THRESHOLD**: Raised from 1700 → **1800 ELO**
  - Below 1800: Bot uses UCI_LimitStrength for fair games
  
- **FULL_STRENGTH_THRESHOLD**: Raised from 2300 → **2800 ELO**
  - Full power now only activated at 2800+ (elite/super-GM level)
  - Previously activated at 2300+ (too strong for most advanced players)

- **Intermediate Scaling (1800-2799 ELO)**: Improved progression
  - Time scaling now 40% → 95% (was 50% → 99%)
  - Wider rating range (1000 points vs 600 points) for smoother difficulty curve
  - Example: 2500 ELO opponent now gets 79% time instead of full power

**Why These Changes:**
- Bot was too dominant against 2300-2799 rated players
- More balanced and enjoyable games across all skill levels
- Only true elite players (2800+) face maximum bot strength
- Better progression from intermediate to advanced levels

**New Effective Strength:**
- **< 1800 ELO**: Opponent rating + 100 ELO (fair learning games)
- **1800-2799 ELO**: ~2000-2900 ELO (challenging but beatable)
- **2800+ ELO**: ~3200-3500 ELO (maximum power for elite players)

## [2.0.0] - 2026-02-06

### Major Changes - Intelligence & Quality Improvements

#### 🎯 Hybrid Dynamic Strength System (Best of Both Worlds!)

**Problem with Pure Time-Based System:**
- Time-only approach was too strong for beginners (even 450ms = ~2200 ELO)
- Players below 1800 ELO had almost no chance to win

**Solution: HYBRID APPROACH**

**Three-Tier System:**

1. **Beginners & Intermediates (< 1800 ELO):**
   - Uses `UCI_LimitStrength` set to opponent_rating + 100
   - Bot plays at fair, balanced level
   - Example: 1500-rated player faces ~1600 strength
   - **Result: Winnable, educational games** ✅

2. **Advanced Players (1800-2199 ELO):**
   - **Full-strength Stockfish** (no intentional mistakes)
   - Thinking time scaled 50-99% based on rating
   - Example: 2000-rated gets 75% time = ~2400 ELO strength
   - **Result: Challenging, high-quality chess** ✅

3. **Expert & Master (2200+ ELO):**
   - **MAXIMUM POWER**: Full strength + Full time (3 seconds)
   - No compromises, no handicaps
   - Effective strength: ~3200-3500 ELO
   - **Result: Ultimate challenge** 🔥

**Benefits:**
- ✅ Fair games for beginners (UCI_LimitStrength ensures balance)
- ✅ No blunders for advanced players (full engine quality)
- ✅ Maximum challenge for strong players (full power unlocked)
- ✅ Smooth difficulty curve across all levels

#### 🤝 Intelligent Draw Offer Handling

**Old Logic:**
- Accepted draws when losing badly (< -300 centipawns)
- Gave up in difficult positions

**New Logic:**
- **Accepts** draws only in balanced positions (±200 centipawns)
- **Declines** draws when winning (let the advantage play out)
- **Declines** draws when losing (trust engine to find counterplay)
- **Declines** all draws in mate positions (engine knows best)
- Philosophy: Utilize superior calculation power, don't surrender easily

#### ⚙️ Configuration Updates

**Performance Improvements:**
- `STOCKFISH_TIME`: 1100ms → **3000ms** (3 seconds per move)
  - Depth increased from ~15-20 ply to ~25-30 ply
  - More accurate position evaluation
- `Hash`: 1024 MB → **2048 MB**
  - Better position caching
  - Faster repeat position detection

**New Configuration Options:**
- `LIMIT_STRENGTH_THRESHOLD`: Below this rating, use UCI_LimitStrength (default: 1800)
- `FULL_STRENGTH_THRESHOLD`: At or above this rating, use full power (default: 2200)
- `STRENGTH_ADVANTAGE`: ELO bonus for weak opponents (default: 100, restored with new purpose)

### Technical Changes

#### Hybrid System Implementation
- Added `LIMIT_STRENGTH_THRESHOLD` configuration parameter
- Restored `STRENGTH_ADVANTAGE` with new meaning (for weak opponents only)
- `init_stockfish()` now conditionally applies UCI_LimitStrength based on opponent rating
- `calculate_move_time()` uses three-tier time scaling (40% / 50-99% / 100%)

#### API Fixes
- Fixed draw response error: `'dict' object has no attribute 'raise_for_status'`
- Now uses proper Berserk API methods: `client.bots.accept_draw()` / `decline_draw()`

#### Code Improvements
- Better logging for draw decisions and strength adjustments
- Clear separation between fairness mode (UCI_LimitStrength) and challenge mode (time control)

#### Test Suite Updates
- Updated test count: 21 → **25 tests**
- Modified Stockfish initialization tests for hybrid approach
- Updated `TestMoveTimeCalculation` class with 4 tests:
  - Full time for strong opponents (≥ 2200)
  - Minimum time for weak opponents (< 1800, UCI_LimitStrength handles fairness)
  - Scaled time for intermediate opponents (1800-2199)
  - Dynamic strength disable functionality
- All tests passing ✅

### Documentation Updates

- ✅ [README.md](README.md) - Complete rewrite of dynamic strength section
- ✅ [TESTING.md](TESTING.md) - Updated test counts and descriptions
- ✅ [config.py](config.py) - Detailed comments explaining new parameters
- ✅ [CHANGELOG.md](CHANGELOG.md) - This file

### Breaking Changes

⚠️ **Configuration Changes:**
- `STRENGTH_ADVANTAGE` restored but with NEW meaning:
  - Old: Bot plays at opponent_elo + advantage (all opponents)
  - New: Bot plays at opponent_elo + advantage (only for opponents < 1800)
- `DYNAMIC_STRENGTH` now controls hybrid system (UCI_LimitStrength + time control)
- New threshold: `LIMIT_STRENGTH_THRESHOLD` determines when to switch from fairness to challenge mode

### Migration Guide

**No action needed for most users** - the hybrid system automatically provides better balance!

If you were using custom settings:

**Before (Time-Only):**
```python
DYNAMIC_STRENGTH = True
FULL_STRENGTH_THRESHOLD = 2200
STRENGTH_ADVANTAGE = 0  # Unused
```

**After (Hybrid - Recommended):**
```python
DYNAMIC_STRENGTH = True
LIMIT_STRENGTH_THRESHOLD = 1800  # Use UCI_LimitStrength below this
FULL_STRENGTH_THRESHOLD = 2200   # Full power at or above this
STRENGTH_ADVANTAGE = 100         # For opponents < 1800
```

To disable hybrid system (not recommended):
```python
DYNAMIC_STRENGTH = False  # Same time and strength for all opponents
```

### Performance Comparison

| Opponent ELO | Old System | Hybrid System | Method | Fairness |
|--------------|-----------|---------------|---------|----------|
| **1200** | ~1300 (UCI_Elo) | ~1300 (UCI_Elo) | UCI_LimitStrength | ✅ Fair |
| **1500** | ~1600 (UCI_Elo) | ~1600 (UCI_Elo) | UCI_LimitStrength | ✅ Fair |
| **1800** | ~1900 (UCI_Elo) | ~2000 (50% time) | Time Control | ✅ Challenging |
| **2000** | ~2100 (UCI_Elo) | ~2400 (75% time) | Time Control | ✅ Hard |
| **2200** | ~2300 (UCI_Elo) | **~3200 (100% time)** | **FULL POWER** | 🔥 Maximum |
| **2500** | 2600 (UCI_Elo) | **~3400 (100% time)** | **FULL POWER** | 🔥 Maximum |

**Key Improvement:** Strong opponents (2200+) now face ~1000 ELO stronger bot!

### Contributors

- Core changes by @whiteravens20
- Inspired by feedback from real-game analysis

---

## [1.0.0] - 2025-01-XX

Initial release with basic functionality.
