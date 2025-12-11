#!/usr/bin/env python3
"""
Test runner script for Jellyfin Media Downloader.

This script sets up an isolated test environment BEFORE any project
modules are imported, preventing the .env file from being loaded
and avoiding file system operations on production paths.

Usage:
    python run_tests.py [pytest args]
    
Examples:
    python run_tests.py                    # Run all tests
    python run_tests.py -v                 # Verbose output
    python run_tests.py tests/test_utils.py  # Run specific test file
    python run_tests.py --cov=. --cov-report=term-missing  # With coverage
"""
import os
import sys
import tempfile
import shutil
import atexit

# ============================================================================
# STEP 1: Create isolated test environment BEFORE any imports
# ============================================================================

# Create temp directory for all test data
TEST_BASE_DIR = tempfile.mkdtemp(prefix="jellyfin_test_")

# Set ALL environment variables BEFORE dotenv can load .env
os.environ["BASE_DIR"] = TEST_BASE_DIR
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "test_api_hash_for_testing"
os.environ["BOT_TOKEN"] = "123456789:TEST_BOT_TOKEN"
os.environ["ADMIN_IDS"] = "111111111,222222222"
os.environ["TMDB_API_KEY"] = "test_tmdb_key"
os.environ["LOW_CONFIDENCE"] = "0.6"
os.environ["HIGH_CONFIDENCE"] = "0.8"
os.environ["SESSION_NAME"] = os.path.join(TEST_BASE_DIR, "sessions", "jellyfin")

# Set directory paths
os.environ["DOWNLOAD_DIR"] = os.path.join(TEST_BASE_DIR, "Downloads")
os.environ["MOVIES_DIR"] = os.path.join(TEST_BASE_DIR, "Movies")
os.environ["TV_DIR"] = os.path.join(TEST_BASE_DIR, "TV")
os.environ["ANIME_DIR"] = os.path.join(TEST_BASE_DIR, "Anime")
os.environ["MUSIC_DIR"] = os.path.join(TEST_BASE_DIR, "Music")
os.environ["OTHER_DIR"] = os.path.join(TEST_BASE_DIR, "Other")
os.environ["LOG_DIR"] = os.path.join(TEST_BASE_DIR, "logs")

# Prevent dotenv from loading .env file
os.environ["DOTENV_LOADED"] = "true"

# Create all required directories
for subdir in ["Downloads", "Movies", "TV", "Anime", "Music", "Other", "logs", "sessions"]:
    os.makedirs(os.path.join(TEST_BASE_DIR, subdir), exist_ok=True)

print(f"🧪 Test environment created at: {TEST_BASE_DIR}")

# Cleanup function
def cleanup_test_dir():
    if os.path.exists(TEST_BASE_DIR):
        shutil.rmtree(TEST_BASE_DIR, ignore_errors=True)
        print(f"🧹 Cleaned up: {TEST_BASE_DIR}")

atexit.register(cleanup_test_dir)

# ============================================================================
# STEP 2: Patch dotenv before it can be imported by config.py
# ============================================================================

# Create a mock dotenv module that does nothing
class MockDotenv:
    @staticmethod
    def load_dotenv(*args, **kwargs):
        return True

sys.modules['dotenv'] = MockDotenv()

# ============================================================================
# STEP 3: Mock tmdbv3api to prevent network calls during import
# ============================================================================

class MockTMDb:
    api_key = None
    language = 'en'

class MockMovie:
    def search(self, query):
        return []

class MockTV:
    def search(self, query):
        return []
    def tv_episode(self, *args):
        return {}

class MockTmdbv3api:
    TMDb = MockTMDb
    Movie = MockMovie
    TV = MockTV

sys.modules['tmdbv3api'] = MockTmdbv3api()

# ============================================================================
# STEP 4: Now we can safely import and run pytest
# ============================================================================

if __name__ == "__main__":
    import pytest
    import time
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.join(script_dir, "tests")
    
    # Build pytest arguments
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    # Default to running tests directory if no specific path given
    if not any(arg.startswith("tests") or arg.startswith("test_") for arg in args):
        args.insert(0, tests_dir)
    
    # Add verbose flag if not present
    if "-v" not in args and "--verbose" not in args:
        args.insert(0, "-v")
    
    print(f"📁 Running: pytest {' '.join(args)}")
    print("-" * 60)
    
    start_time = time.time()
    
    # Run pytest
    exit_code = pytest.main(args)
    
    elapsed = time.time() - start_time
    
    # Play completion chime (terminal bell)
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("✅ All tests PASSED!")
    else:
        print(f"❌ Tests finished with exit code: {exit_code}")
    print(f"⏱️  Total time: {elapsed:.1f}s")
    print("=" * 60)
    
    # Terminal bell for audio notification
    print("\a")  # Terminal bell character
    
    # Try to play a more audible sound on Linux
    try:
        os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null &")
    except:
        pass
    
    sys.exit(exit_code)

