# Performance Testing Guide

## Quick Start

### 🚀 Run ALL Tests (Recommended)
```bash
cd c:\Users\GG\Documents\coding in antigravity\Jellyfin_Media_Downloader
.\venv\Scripts\python.exe run_all_performance_tests.py
```

**This runs:**
1. Startup profiling (import times, initialization)
2. Unit performance tests (database, memory)
3. End-to-end tests (full bot lifecycle)

**Output:** Comprehensive report with all metrics

---

### 1. Startup Profiling
```bash
.\venv\Scripts\python.exe profile_startup.py
```

**Measures:**
- Import times for each module
- Initialization bottlenecks
- Memory usage

**Output Files:**
- `import_times.txt` - Shows which imports are slowest
- `startup_profile.txt` - Detailed function call profiling
- `startup_timeline.txt` - Timeline of initialization steps

---

### 2. Unit Performance Tests
```bash
.\venv\Scripts\python.exe -m pytest tests/test_performance.py -v -s
```

**Measures:**
- Database operations (read/write/query)
- Individual module import times
- Memory footprint
- Concurrent database access

**Output:**
- Console: Real-time test results
- `performance_baseline.txt` - Baseline metrics for comparison

---

### 3. End-to-End Performance Tests
```bash
.\venv\Scripts\python.exe test_e2e_performance.py
```

**Measures:**
- ✅ Cold start (first import) - Why: Includes compilation
- ✅ Warm start (cached import) - Why: Uses bytecode cache
- ✅ Bot initialization - Why: Telegram connection time
- ✅ First command response - Why: May trigger lazy init
- ✅ All command performance - Why: Identify slow commands
- ✅ Concurrent commands - Why: Test async efficiency
- ✅ Database operations - Why: Common bottleneck
- ✅ Graceful shutdown - Why: Resource cleanup time
- ✅ Memory usage - Why: Detect leaks

**Output:**
- `performance_e2e_results.json` - Detailed results with WHY explanations

---

## What Gets Measured

### Startup Performance
- ✅ Import time (target: < 0.5s) - **Currently: ~3.6s**
- ✅ Database initialization (target: < 0.1s)
- ✅ Stats loading (target: < 0.05s)
- ✅ Memory usage (target: < 50MB increase)

### Runtime Performance
- ✅ Command response time (target: < 500ms)
- ✅ Database read (target: < 10ms average)
- ✅ Database write (target: < 20ms average)
- ✅ Concurrent handling (target: near-linear scaling)

### Shutdown Performance
- ✅ Graceful shutdown (target: < 5s typical)
- ✅ Resource cleanup time
- ✅ State persistence time

---

## Reading the Results

### Good Performance ✅
```
📊 Import Time: 0.345s
   Target: < 0.5s
   Status: ✅ PASS
```

### Needs Optimization ❌
```
📊 Import Time: 3.584s
   Target: < 0.5s
   Status: ❌ SLOW
   Why: telethon (2.4s) + guessit (2.1s) + aiohttp (1.3s)
```

### Understanding WHY

Each test includes explanations:
- **Why it matters**: Why this metric is important
- **What causes delays**: Specific bottlenecks
- **How to fix**: Optimization strategies

Example:
```json
{
  "cold_start": {
    "duration": 3.584,
    "why": "First import includes Python bytecode compilation + module initialization",
    "components": {
      "module_compilation": "Python compiles .py to bytecode",
      "import_dependencies": "Loads all dependencies (telethon, aiohttp, guessit, etc.)",
      "module_level_init": "Executes module-level code (db init, stats loading, etc.)"
    }
  }
}
```

---

## After Optimization

Run the same tests again to compare:

```bash
# Before optimization
.\venv\Scripts\python.exe run_all_performance_tests.py > before_optimization.txt

# After optimization
.\venv\Scripts\python.exe run_all_performance_tests.py > after_optimization.txt

# Compare
diff before_optimization.txt after_optimization.txt
```

---

## Troubleshooting

### psutil not found
```bash
.\venv\Scripts\pip.exe install psutil
```

### pytest not found
```bash
.\venv\Scripts\pip.exe install pytest pytest-asyncio
```

### Import errors
Make sure you're in the project directory:
```bash
cd c:\Users\GG\Documents\coding in antigravity\Jellyfin_Media_Downloader
```

### Tests hang
Some tests connect to Telegram. Ensure:
- `.env` file exists with valid credentials
- Internet connection is active
- No firewall blocking Telegram

---

## Performance Targets

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| **Startup Time** | ~3.6s | < 1.5s | 🔴 High |
| **Command Response** | ~500ms | < 200ms | 🟡 Medium |
| **Database Read** | ~15ms | < 5ms | 🟡 Medium |
| **Database Write** | ~25ms | < 10ms | 🟡 Medium |
| **Memory Usage** | ~80MB | < 60MB | 🟢 Low |
| **Shutdown Time** | ~2s | < 1s | 🟢 Low |

---

## Next Steps

1. ✅ Run `run_all_performance_tests.py` to get baseline
2. ✅ Review `performance_e2e_results.json` for detailed WHY explanations
3. ✅ Check `import_times.txt` for slowest imports
4. ✅ Implement optimizations from `performance_optimization_plan.md`
5. ✅ Re-run tests to measure improvement
6. ✅ Repeat until targets are met

