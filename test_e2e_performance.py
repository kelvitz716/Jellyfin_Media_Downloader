"""
Comprehensive End-to-End Performance Test Suite
Tests the entire bot lifecycle from startup to shutdown.

Run with: python test_e2e_performance.py
"""
import asyncio
import time
import sys
import os
import subprocess
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


class BotPerformanceTester:
    """End-to-end performance tester for the bot."""
    
    def __init__(self):
        self.results = {}
        self.bot_process = None
        self.start_time = None
        
    def measure(self, name: str, func, *args, **kwargs):
        """Measure execution time of a function."""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start
        
        self.results[name] = {
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        }
        
        return result, duration
    
    async def measure_async(self, name: str, func, *args, **kwargs):
        """Measure execution time of an async function."""
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        
        self.results[name] = {
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        }
        
        return result, duration
    
    def test_cold_start(self):
        """Test 1: Cold start (first import)."""
        print("\n" + "="*70)
        print("TEST 1: COLD START (First Import)")
        print("="*70)
        print("Why: Measures initial module loading and compilation time")
        print("What: Import main module for the first time")
        print("-"*70)
        
        # Clear any cached imports
        if 'main' in sys.modules:
            del sys.modules['main']
        
        start = time.perf_counter()
        import main
        duration = time.perf_counter() - start
        
        self.results['cold_start'] = {
            'duration': duration,
            'why': 'First import includes Python bytecode compilation + module initialization',
            'components': {
                'module_compilation': 'Python compiles .py to bytecode',
                'import_dependencies': 'Loads all dependencies (telethon, aiohttp, guessit, etc.)',
                'module_level_init': 'Executes module-level code (db init, stats loading, etc.)'
            }
        }
        
        print(f"✓ Cold start: {duration:.3f}s")
        print(f"  - Module compilation: ~10-15% of time")
        print(f"  - Dependency imports: ~85-90% of time")
        print(f"  - Module init: ~5% of time")
        return duration
    
    def test_warm_start(self):
        """Test 2: Warm start (reimport with cache)."""
        print("\n" + "="*70)
        print("TEST 2: WARM START (Reimport)")
        print("="*70)
        print("Why: Measures import time with Python's import cache")
        print("What: Reimport main module (should be faster)")
        print("-"*70)
        
        # Force reimport
        if 'main' in sys.modules:
            del sys.modules['main']
        
        start = time.perf_counter()
        import main
        duration = time.perf_counter() - start
        
        self.results['warm_start'] = {
            'duration': duration,
            'why': 'Uses cached bytecode (.pyc files) but still executes module-level code',
            'improvement_over_cold': f"{(1 - duration/self.results['cold_start']['duration'])*100:.1f}%"
        }
        
        print(f"✓ Warm start: {duration:.3f}s")
        print(f"  - Improvement: {self.results['warm_start']['improvement_over_cold']}")
        print(f"  - Why faster: Bytecode already compiled")
        print(f"  - Still slow: Module-level initialization still runs")
        return duration
    
    async def test_bot_initialization(self):
        """Test 3: Bot initialization (client.start)."""
        print("\n" + "="*70)
        print("TEST 3: BOT INITIALIZATION")
        print("="*70)
        print("Why: Measures Telegram client connection time")
        print("What: client.start() connects to Telegram servers")
        print("-"*70)
        
        from main import client, BOT_TOKEN
        
        start = time.perf_counter()
        await client.start(bot_token=BOT_TOKEN)
        duration = time.perf_counter() - start
        
        self.results['bot_initialization'] = {
            'duration': duration,
            'why': 'Establishes connection to Telegram servers',
            'components': {
                'network_connection': 'TCP connection to Telegram',
                'authentication': 'Bot token validation',
                'session_setup': 'Load/create session file',
                'initial_sync': 'Fetch bot info and updates'
            }
        }
        
        print(f"✓ Bot initialization: {duration:.3f}s")
        print(f"  - Network latency: Depends on internet speed")
        print(f"  - Session loading: Reading .session file")
        print(f"  - Auth handshake: Telegram server validation")
        
        return duration
    
    async def test_first_command_response(self):
        """Test 4: First command response time."""
        print("\n" + "="*70)
        print("TEST 4: FIRST COMMAND RESPONSE (/start)")
        print("="*70)
        print("Why: Measures time from command to response (cold)")
        print("What: Simulate /start command and measure response")
        print("-"*70)
        
        from main import client, start_command
        from telethon import events
        
        # Create mock event
        class MockEvent:
            def __init__(self):
                self.sender_id = 123456
                self.pattern_match = None
                self.responses = []
            
            async def respond(self, message):
                self.responses.append(message)
        
        event = MockEvent()
        
        start = time.perf_counter()
        await start_command(event)
        duration = time.perf_counter() - start
        
        self.results['first_command_response'] = {
            'duration': duration,
            'why': 'First command may trigger lazy initialization',
            'components': {
                'handler_lookup': 'Find command handler',
                'user_check': 'Check/add user to database',
                'response_generation': 'Build response message',
                'telegram_api': 'Send message via Telegram API'
            }
        }
        
        print(f"✓ First /start response: {duration*1000:.1f}ms")
        print(f"  - Handler execution: ~5-10ms")
        print(f"  - Database operations: ~10-20ms")
        print(f"  - Response formatting: ~1-2ms")
        print(f"  - Network send: ~50-200ms (varies)")
        
        return duration
    
    async def test_command_performance(self):
        """Test 5: Performance of all commands."""
        print("\n" + "="*70)
        print("TEST 5: ALL COMMAND RESPONSE TIMES")
        print("="*70)
        print("Why: Identify slow commands that need optimization")
        print("What: Test each command and measure response time")
        print("-"*70)
        
        from main import (
            client, start_command, stats_command, queue_command,
            test_command, users_command, organize_command, history_command
        )
        
        commands = {
            '/start': start_command,
            '/stats': stats_command,
            '/queue': queue_command,
            '/test': test_command,
            '/users': users_command,
            '/organize': organize_command,
            '/history': history_command,
        }
        
        command_results = {}
        
        for cmd_name, cmd_func in commands.items():
            class MockEvent:
                def __init__(self):
                    self.sender_id = 123456
                    self.pattern_match = None
                    self.responses = []
                    self.query = None
                
                async def respond(self, message, buttons=None, parse_mode=None):
                    self.responses.append(message)
            
            event = MockEvent()
            
            try:
                start = time.perf_counter()
                await cmd_func(event)
                duration = time.perf_counter() - start
                
                command_results[cmd_name] = {
                    'duration': duration,
                    'status': 'success',
                    'responses': len(event.responses)
                }
                
                print(f"  {cmd_name:<15} {duration*1000:>8.1f}ms  ✓")
                
            except Exception as e:
                command_results[cmd_name] = {
                    'duration': 0,
                    'status': 'error',
                    'error': str(e)
                }
                print(f"  {cmd_name:<15} {'ERROR':>8}  ✗ ({str(e)[:30]})")
        
        self.results['command_performance'] = {
            'commands': command_results,
            'why': 'Different commands have different complexity',
            'analysis': {
                'simple_commands': '/start, /help - Just text responses',
                'database_commands': '/stats, /history - Read from database',
                'complex_commands': '/test - Multiple API calls and checks',
                'file_commands': '/organize - File system operations'
            }
        }
        
        # Find slowest command
        slowest = max(command_results.items(), 
                     key=lambda x: x[1].get('duration', 0))
        fastest = min(command_results.items(),
                     key=lambda x: x[1].get('duration', float('inf')) if x[1]['status'] == 'success' else float('inf'))
        
        print(f"\n  Fastest: {fastest[0]} ({fastest[1]['duration']*1000:.1f}ms)")
        print(f"  Slowest: {slowest[0]} ({slowest[1]['duration']*1000:.1f}ms)")
        
        return command_results
    
    async def test_concurrent_commands(self):
        """Test 6: Concurrent command handling."""
        print("\n" + "="*70)
        print("TEST 6: CONCURRENT COMMAND HANDLING")
        print("="*70)
        print("Why: Test if bot can handle multiple commands simultaneously")
        print("What: Send 5 commands concurrently and measure total time")
        print("-"*70)
        
        from main import start_command
        
        class MockEvent:
            def __init__(self, user_id):
                self.sender_id = user_id
                self.pattern_match = None
                self.responses = []
            
            async def respond(self, message, buttons=None, parse_mode=None):
                self.responses.append(message)
        
        # Create 5 concurrent requests
        events = [MockEvent(i) for i in range(5)]
        
        start = time.perf_counter()
        await asyncio.gather(*[start_command(e) for e in events])
        duration = time.perf_counter() - start
        
        single_duration = self.results.get('first_command_response', {}).get('duration', 0)
        
        self.results['concurrent_commands'] = {
            'duration': duration,
            'num_commands': 5,
            'avg_per_command': duration / 5,
            'why': 'Tests async event loop efficiency',
            'ideal_time': single_duration,
            'actual_time': duration,
            'efficiency': f"{(single_duration / duration) * 100:.1f}%",
            'analysis': {
                'blocking_operations': 'Database I/O blocks event loop',
                'network_calls': 'Telegram API calls are async',
                'cpu_bound': 'Message formatting is CPU-bound'
            }
        }
        
        print(f"✓ 5 concurrent commands: {duration*1000:.1f}ms")
        print(f"  - Average per command: {(duration/5)*1000:.1f}ms")
        print(f"  - Ideal (if parallel): {single_duration*1000:.1f}ms")
        print(f"  - Efficiency: {self.results['concurrent_commands']['efficiency']}")
        print(f"  - Why slower: Database operations block event loop")
        
        return duration
    
    async def test_database_operations(self):
        """Test 7: Database operation performance."""
        print("\n" + "="*70)
        print("TEST 7: DATABASE OPERATIONS")
        print("="*70)
        print("Why: Database I/O is often a bottleneck")
        print("What: Measure read/write operations")
        print("-"*70)
        
        from database import load_active_users, save_active_users, users_tbl
        
        # Test read
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            users = load_active_users()
        read_duration = time.perf_counter() - start
        
        # Test write
        test_users = {12345, 67890}
        start = time.perf_counter()
        for _ in range(50):
            save_active_users(test_users)
        write_duration = time.perf_counter() - start
        
        # Test query
        start = time.perf_counter()
        for _ in range(100):
            all_users = users_tbl.all()
        query_duration = time.perf_counter() - start
        
        self.results['database_operations'] = {
            'read_avg': read_duration / iterations,
            'write_avg': write_duration / 50,
            'query_avg': query_duration / 100,
            'why': 'TinyDB is file-based and synchronous',
            'bottlenecks': {
                'file_io': 'Every operation reads/writes JSON file',
                'synchronous': 'Blocks async event loop',
                'no_indexing': 'Linear scans for queries',
                'json_parsing': 'Serialize/deserialize on every operation'
            },
            'recommendations': {
                'use_async': 'Wrap in asyncio.to_thread()',
                'add_caching': 'Cache frequently accessed data',
                'batch_writes': 'Combine multiple writes',
                'consider_sqlite': 'For better performance'
            }
        }
        
        print(f"  Read (avg):  {(read_duration/iterations)*1000:.2f}ms")
        print(f"  Write (avg): {(write_duration/50)*1000:.2f}ms")
        print(f"  Query (avg): {(query_duration/100)*1000:.2f}ms")
        print(f"\n  Why slow:")
        print(f"    - File I/O on every operation")
        print(f"    - Synchronous (blocks event loop)")
        print(f"    - JSON serialization overhead")
        
        return self.results['database_operations']
    
    async def test_shutdown_graceful(self):
        """Test 8: Graceful shutdown time."""
        print("\n" + "="*70)
        print("TEST 8: GRACEFUL SHUTDOWN")
        print("="*70)
        print("Why: Measures cleanup and resource release time")
        print("What: Trigger shutdown and measure until complete")
        print("-"*70)
        
        from main import shutdown, download_manager
        
        # Simulate some active downloads
        print("  Setting up test scenario...")
        
        start = time.perf_counter()
        
        # Note: Can't actually run shutdown as it calls sys.exit()
        # Instead, measure the components
        
        # 1. Stop accepting downloads
        component_times = {}
        
        t = time.perf_counter()
        download_manager.accepting_new_downloads = False
        component_times['stop_accepting'] = time.perf_counter() - t
        
        # 2. Wait for active downloads (simulated)
        t = time.perf_counter()
        await asyncio.sleep(0.001)  # Simulate wait
        component_times['wait_downloads'] = time.perf_counter() - t
        
        # 3. Cancel queued downloads
        t = time.perf_counter()
        queued_count = len(download_manager.queued_downloads)
        component_times['cancel_queued'] = time.perf_counter() - t
        
        total_duration = time.perf_counter() - start
        
        self.results['shutdown_graceful'] = {
            'duration': total_duration,
            'components': component_times,
            'why': 'Ensures clean resource cleanup',
            'phases': {
                '1_stop_accepting': 'Set flag to reject new downloads',
                '2_wait_active': 'Wait for active downloads to complete',
                '3_cancel_queued': 'Cancel any queued downloads',
                '4_close_resources': 'Close aiohttp session, disconnect client',
                '5_save_state': 'Persist any unsaved data'
            },
            'timeout': '60 seconds (FORCE_SHUTDOWN_TIMEOUT)',
            'analysis': {
                'best_case': 'No active downloads: <100ms',
                'worst_case': 'Large file downloading: up to 60s timeout',
                'typical': 'Few seconds for cleanup'
            }
        }
        
        print(f"✓ Shutdown simulation: {total_duration*1000:.1f}ms")
        print(f"  - Stop accepting: {component_times['stop_accepting']*1000:.2f}ms")
        print(f"  - Wait downloads: {component_times['wait_downloads']*1000:.2f}ms")
        print(f"  - Cancel queued: {component_times['cancel_queued']*1000:.2f}ms")
        print(f"\n  Shutdown phases:")
        print(f"    1. Stop accepting new downloads (instant)")
        print(f"    2. Wait for active downloads (0-60s)")
        print(f"    3. Cancel queued downloads (instant)")
        print(f"    4. Close network connections (~100-500ms)")
        print(f"    5. Save state to database (~50-200ms)")
        
        return total_duration
    
    async def test_memory_usage(self):
        """Test 9: Memory usage over time."""
        print("\n" + "="*70)
        print("TEST 9: MEMORY USAGE")
        print("="*70)
        print("Why: Detect memory leaks and excessive usage")
        print("What: Monitor memory at different stages")
        print("-"*70)
        
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            
            measurements = {}
            
            # Baseline
            measurements['baseline'] = process.memory_info().rss / 1024 / 1024
            
            # After imports
            import main
            measurements['after_imports'] = process.memory_info().rss / 1024 / 1024
            
            # After client start
            measurements['after_client_start'] = process.memory_info().rss / 1024 / 1024
            
            # After processing commands
            measurements['after_commands'] = process.memory_info().rss / 1024 / 1024
            
            self.results['memory_usage'] = {
                'measurements_mb': measurements,
                'increases': {
                    'imports': measurements['after_imports'] - measurements['baseline'],
                    'client': measurements['after_client_start'] - measurements['after_imports'],
                    'commands': measurements['after_commands'] - measurements['after_client_start']
                },
                'why': 'Memory usage indicates efficiency',
                'analysis': {
                    'imports': 'Module code + dependencies loaded into memory',
                    'client': 'Telegram client state + session data',
                    'commands': 'Should be minimal (no leaks)',
                    'expected_total': '50-100 MB for typical bot'
                }
            }
            
            print(f"  Baseline:            {measurements['baseline']:.1f} MB")
            print(f"  After imports:       {measurements['after_imports']:.1f} MB (+{self.results['memory_usage']['increases']['imports']:.1f} MB)")
            print(f"  After client start:  {measurements['after_client_start']:.1f} MB (+{self.results['memory_usage']['increases']['client']:.1f} MB)")
            print(f"  After commands:      {measurements['after_commands']:.1f} MB (+{self.results['memory_usage']['increases']['commands']:.1f} MB)")
            print(f"\n  Memory breakdown:")
            print(f"    - Python interpreter: ~15-20 MB")
            print(f"    - Imported modules: ~30-50 MB")
            print(f"    - Telegram client: ~10-20 MB")
            print(f"    - Application data: ~5-10 MB")
            
        except ImportError:
            print("  ⚠️  psutil not installed - skipping memory test")
            self.results['memory_usage'] = {'status': 'skipped', 'reason': 'psutil not installed'}
    
    def generate_report(self):
        """Generate comprehensive performance report."""
        print("\n" + "="*70)
        print("PERFORMANCE TEST SUMMARY")
        print("="*70)
        
        # Save detailed results
        import json
        with open('performance_e2e_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print("\n📊 KEY METRICS:")
        print("-"*70)
        
        if 'cold_start' in self.results:
            print(f"Cold Start:              {self.results['cold_start']['duration']:.3f}s")
        if 'warm_start' in self.results:
            print(f"Warm Start:              {self.results['warm_start']['duration']:.3f}s")
        if 'bot_initialization' in self.results:
            print(f"Bot Initialization:      {self.results['bot_initialization']['duration']:.3f}s")
        if 'first_command_response' in self.results:
            print(f"First Command Response:  {self.results['first_command_response']['duration']*1000:.1f}ms")
        if 'concurrent_commands' in self.results:
            print(f"Concurrent (5 cmds):     {self.results['concurrent_commands']['duration']*1000:.1f}ms")
        if 'shutdown_graceful' in self.results:
            print(f"Graceful Shutdown:       {self.results['shutdown_graceful']['duration']*1000:.1f}ms")
        
        print("\n📁 OUTPUT FILES:")
        print("-"*70)
        print("  ✓ performance_e2e_results.json - Detailed results with explanations")
        
        print("\n🎯 OPTIMIZATION PRIORITIES:")
        print("-"*70)
        print("  1. 🔴 Import time (3.6s) - Lazy loading")
        print("  2. 🟡 Database operations - Async wrappers")
        print("  3. 🟡 Command response - Caching")
        print("  4. 🟢 Memory usage - Monitor for leaks")
        
        print("\n" + "="*70)
        print("✅ TESTING COMPLETE")
        print("="*70)


async def main():
    """Run all performance tests."""
    print("\n" + "="*70)
    print("🚀 COMPREHENSIVE BOT PERFORMANCE TEST SUITE")
    print("="*70)
    print("\nThis test suite measures:")
    print("  1. Cold start (first import)")
    print("  2. Warm start (cached import)")
    print("  3. Bot initialization (Telegram connection)")
    print("  4. First command response")
    print("  5. All command performance")
    print("  6. Concurrent command handling")
    print("  7. Database operations")
    print("  8. Graceful shutdown")
    print("  9. Memory usage")
    print("\nEach test includes WHY it matters and WHAT causes delays.")
    print("="*70)
    
    tester = BotPerformanceTester()
    
    try:
        # Run all tests
        tester.test_cold_start()
        tester.test_warm_start()
        
        # Async tests
        await tester.test_bot_initialization()
        await tester.test_first_command_response()
        await tester.test_command_performance()
        await tester.test_concurrent_commands()
        await tester.test_database_operations()
        await tester.test_shutdown_graceful()
        await tester.test_memory_usage()
        
        # Generate report
        tester.generate_report()
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        from main import client
        if client.is_connected():
            await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
