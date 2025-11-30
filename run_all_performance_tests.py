"""
Master Performance Test Runner
Runs all performance tests and generates comprehensive reports.

Usage:
    python run_all_performance_tests.py
"""
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


def run_test(name, command, description):
    """Run a test and return results."""
    print("\n" + "="*80)
    print(f"🧪 {name}")
    print("="*80)
    print(f"Description: {description}")
    print(f"Command: {' '.join(command) if isinstance(command, list) else command}")
    print("-"*80)
    
    start = time.time()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=Path(__file__).parent  # Set working directory
        )
        duration = time.time() - start
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        status = "✅ PASS" if result.returncode == 0 else "❌ FAIL"
        print(f"\n{status} - Completed in {duration:.2f}s")
        
        return {
            'name': name,
            'status': 'pass' if result.returncode == 0 else 'fail',
            'duration': duration,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        print(f"\n⏱️ TIMEOUT - Exceeded 5 minutes")
        return {
            'name': name,
            'status': 'timeout',
            'duration': duration
        }
    except Exception as e:
        duration = time.time() - start
        print(f"\n❌ ERROR - {str(e)}")
        return {
            'name': name,
            'status': 'error',
            'duration': duration,
            'error': str(e)
        }


def main():
    """Run all performance tests."""
    print("\n" + "="*80)
    print("🚀 MASTER PERFORMANCE TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = []
    
    # Test 1: Startup Profiling
    results.append(run_test(
        "Startup Profiling",
        [sys.executable, "profile_startup.py"],
        "Profiles import times, initialization, and memory usage"
    ))
    
    # Test 2: Unit Performance Tests
    results.append(run_test(
        "Unit Performance Tests",
        [sys.executable, "-m", "pytest", "tests/test_performance.py", "-v", "-s"],
        "Tests individual components (database, imports, memory)"
    ))
    
    # Test 3: End-to-End Performance
    results.append(run_test(
        "End-to-End Performance",
        [sys.executable, "test_e2e_performance.py"],
        "Tests complete bot lifecycle from startup to shutdown"
    ))
    
    # Generate Summary Report
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r['status'] == 'pass')
    failed = sum(1 for r in results if r['status'] == 'fail')
    errors = sum(1 for r in results if r['status'] == 'error')
    timeouts = sum(1 for r in results if r['status'] == 'timeout')
    
    print(f"\nResults:")
    print(f"  ✅ Passed:  {passed}")
    print(f"  ❌ Failed:  {failed}")
    print(f"  ⚠️  Errors:  {errors}")
    print(f"  ⏱️  Timeout: {timeouts}")
    
    print(f"\nTest Details:")
    for r in results:
        status_icon = {
            'pass': '✅',
            'fail': '❌',
            'error': '⚠️',
            'timeout': '⏱️'
        }.get(r['status'], '❓')
        
        print(f"  {status_icon} {r['name']:<30} {r['duration']:>8.2f}s")
    
    total_duration = sum(r['duration'] for r in results)
    print(f"\n  Total test time: {total_duration:.2f}s")
    
    # Save results
    import json
    with open('performance_test_summary.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'timeouts': timeouts,
                'total_duration': total_duration
            },
            'results': results
        }, f, indent=2)
    
    print("\n📁 Generated Files:")
    print("  ✓ performance_test_summary.json - Overall test results")
    print("  ✓ performance_e2e_results.json - E2E test details")
    print("  ✓ performance_baseline.txt - Baseline metrics")
    print("  ✓ import_times.txt - Import profiling")
    print("  ✓ startup_profile.txt - Startup profiling")
    print("  ✓ startup_timeline.txt - Initialization timeline")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS COMPLETE")
    print("="*80)
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Exit with appropriate code
    if failed > 0 or errors > 0 or timeouts > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
