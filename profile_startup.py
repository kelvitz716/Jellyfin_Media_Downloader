"""
Detailed startup profiler for Jellyfin Media Downloader Bot.

Usage:
    python profile_startup.py

This will generate:
- startup_profile.txt: Detailed cProfile output
- import_times.txt: Import time breakdown
- startup_timeline.txt: Timeline of initialization steps
"""
import sys
import time
import cProfile
import pstats
from io import StringIO
from pathlib import Path


def profile_imports():
    """Profile import times using -X importtime."""
    print("📊 Profiling Import Times...")
    print("="*60)
    
    import subprocess
    result = subprocess.run(
        [sys.executable, '-X', 'importtime', '-c', 'import main'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    # Parse and save import times
    with open('import_times.txt', 'w') as f:
        f.write(result.stderr)
    
    # Extract slowest imports
    lines = result.stderr.split('\n')
    import_times = []
    
    for line in lines:
        if 'import' in line and '|' in line:
            parts = line.split('|')
            if len(parts) >= 2:
                try:
                    # Extract cumulative time (in microseconds)
                    time_str = parts[0].strip().split()[0]
                    time_us = int(time_str)
                    module = parts[-1].strip()
                    import_times.append((time_us, module))
                except (ValueError, IndexError):
                    continue
    
    # Sort by time and show top 10
    import_times.sort(reverse=True)
    
    print("\n🐌 Slowest Imports (Top 10):")
    print(f"{'Time (ms)':<12} {'Module'}")
    print("-" * 60)
    
    for time_us, module in import_times[:10]:
        time_ms = time_us / 1000
        print(f"{time_ms:>10.1f}ms  {module}")
    
    total_time = sum(t for t, _ in import_times) / 1000
    print(f"\n{'TOTAL':<12} {total_time:.1f}ms")
    print("="*60)


def profile_startup_detailed():
    """Profile startup with cProfile."""
    print("\n📊 Profiling Detailed Startup...")
    print("="*60)
    
    profiler = cProfile.Profile()
    
    # Profile the import
    profiler.enable()
    import main
    profiler.disable()
    
    # Save detailed stats
    with open('startup_profile.txt', 'w') as f:
        stats = pstats.Stats(profiler, stream=f)
        stats.strip_dirs()
        stats.sort_stats('cumulative')
        stats.print_stats(50)  # Top 50 functions
    
    # Print summary to console
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs()
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 to console
    
    print("\n🔝 Top 20 Functions by Cumulative Time:")
    print(stream.getvalue())
    
    print("\n✅ Detailed profile saved to: startup_profile.txt")
    print("="*60)


def profile_initialization_timeline():
    """Create a timeline of initialization steps."""
    print("\n📊 Creating Initialization Timeline...")
    print("="*60)
    
    timeline = []
    start_time = time.perf_counter()
    
    def log_step(step_name):
        elapsed = (time.perf_counter() - start_time) * 1000
        timeline.append((elapsed, step_name))
        print(f"{elapsed:>8.1f}ms  {step_name}")
    
    print(f"{'Time (ms)':<12} {'Step'}")
    print("-" * 60)
    
    # Simulate startup steps
    log_step("START")
    
    import asyncio
    log_step("Import asyncio")
    
    import logging
    log_step("Import logging")
    
    import aiohttp
    log_step("Import aiohttp")
    
    from telethon import TelegramClient
    log_step("Import telethon")
    
    from guessit import guessit
    log_step("Import guessit")
    
    import humanize
    log_step("Import humanize")
    
    from config import API_ID, API_HASH, BOT_TOKEN
    log_step("Import config")
    
    from database import load_active_users, users_tbl
    log_step("Import database (+ init)")
    
    from stats import BotStats
    log_step("Import stats (+ load)")
    
    from downloader import DownloadManager
    log_step("Import downloader")
    
    from organizer import InteractiveOrganizer
    log_step("Import organizer")
    
    # Save timeline
    with open('startup_timeline.txt', 'w') as f:
        f.write(f"{'Time (ms)':<12} {'Cumulative (ms)':<18} {'Step'}\n")
        f.write("-" * 70 + "\n")
        
        prev_time = 0
        for elapsed, step in timeline:
            delta = elapsed - prev_time
            f.write(f"{delta:>10.1f}ms  {elapsed:>15.1f}ms  {step}\n")
            prev_time = elapsed
    
    total_time = timeline[-1][0] if timeline else 0
    print(f"\n{'TOTAL':<12} {total_time:.1f}ms")
    print("\n✅ Timeline saved to: startup_timeline.txt")
    print("="*60)


def analyze_memory_usage():
    """Analyze memory usage during startup."""
    try:
        import psutil
        import os
        
        print("\n📊 Analyzing Memory Usage...")
        print("="*60)
        
        process = psutil.Process(os.getpid())
        
        mem_before = process.memory_info().rss / 1024 / 1024
        print(f"Memory before imports: {mem_before:.1f} MB")
        
        # Import main
        import main
        
        mem_after = process.memory_info().rss / 1024 / 1024
        mem_increase = mem_after - mem_before
        
        print(f"Memory after imports:  {mem_after:.1f} MB")
        print(f"Memory increase:       {mem_increase:.1f} MB")
        
        # Memory breakdown
        mem_info = process.memory_info()
        print(f"\nMemory Breakdown:")
        print(f"  RSS (Resident):      {mem_info.rss / 1024 / 1024:.1f} MB")
        print(f"  VMS (Virtual):       {mem_info.vms / 1024 / 1024:.1f} MB")
        
        print("="*60)
        
    except ImportError:
        print("\n⚠️  psutil not installed. Skipping memory analysis.")
        print("   Install with: pip install psutil")


def main():
    """Run all profiling tasks."""
    print("\n" + "="*60)
    print("🚀 STARTUP PERFORMANCE PROFILER")
    print("="*60)
    
    # 1. Profile imports
    profile_imports()
    
    # 2. Detailed cProfile
    profile_startup_detailed()
    
    # 3. Timeline
    profile_initialization_timeline()
    
    # 4. Memory
    analyze_memory_usage()
    
    print("\n" + "="*60)
    print("✅ PROFILING COMPLETE")
    print("="*60)
    print("\nGenerated files:")
    print("  📄 import_times.txt       - Detailed import time breakdown")
    print("  📄 startup_profile.txt    - cProfile output (top 50 functions)")
    print("  📄 startup_timeline.txt   - Timeline of initialization steps")
    print("\nNext steps:")
    print("  1. Review the slowest imports in import_times.txt")
    print("  2. Check startup_profile.txt for expensive function calls")
    print("  3. Use timeline to identify bottlenecks")
    print("  4. Run performance tests: python -m pytest tests/test_performance.py -v -s")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
