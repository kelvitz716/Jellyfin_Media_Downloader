"""
Live Bot Performance Tester
Tests the bot while it's actually running by sending real Telegram messages.

This requires:
1. Bot to be running
2. Your Telegram user account credentials
3. Access to send messages to the bot

Usage:
    python test_live_bot_performance.py
"""
import asyncio
import time
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import User
import json
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Your user account credentials (not the bot)
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot_username')  # Add to .env

class LiveBotTester:
    """Test bot performance by sending real messages."""
    
    def __init__(self):
        self.client = None
        self.bot_peer = None
        self.results = {}
    
    async def connect(self):
        """Connect as user to send messages to bot."""
        print("🔌 Connecting to Telegram as user...")
        self.client = TelegramClient('test_session', API_ID, API_HASH)
        await self.client.start()
        
        # Get bot entity
        print(f"🤖 Finding bot: @{BOT_USERNAME}")
        self.bot_peer = await self.client.get_entity(BOT_USERNAME)
        print(f"✅ Connected! Bot ID: {self.bot_peer.id}")
    
    async def test_command_response(self, command: str, description: str):
        """Send command and measure response time."""
        print(f"\n📤 Testing: {command}")
        print(f"   Description: {description}")
        
        # Send command
        start = time.perf_counter()
        await self.client.send_message(self.bot_peer, command)
        send_time = time.perf_counter() - start
        
        # Wait for response
        response_start = time.perf_counter()
        timeout = 30  # 30 second timeout
        
        async for message in self.client.iter_messages(self.bot_peer, limit=1):
            if message.date.timestamp() > start:
                response_time = time.perf_counter() - response_start
                total_time = time.perf_counter() - start
                
                result = {
                    'command': command,
                    'description': description,
                    'send_time': send_time,
                    'response_time': response_time,
                    'total_time': total_time,
                    'response_text': message.text[:100] if message.text else '[Media/No text]',
                    'timestamp': datetime.now().isoformat()
                }
                
                self.results[command] = result
                
                print(f"   ✅ Response received!")
                print(f"   ⏱️  Send time: {send_time*1000:.1f}ms")
                print(f"   ⏱️  Response time: {response_time*1000:.1f}ms")
                print(f"   ⏱️  Total time: {total_time*1000:.1f}ms")
                print(f"   📝 Response: {result['response_text']}")
                
                return result
        
        # Timeout
        print(f"   ⏱️  TIMEOUT - No response in {timeout}s")
        return None
    
    async def run_all_tests(self):
        """Run all command tests."""
        print("\n" + "="*80)
        print("🚀 LIVE BOT PERFORMANCE TESTING")
        print("="*80)
        print(f"Bot: @{BOT_USERNAME}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        commands = [
            ('/start', 'Welcome message'),
            ('/help', 'Help text'),
            ('/stats', 'Bot statistics'),
            ('/queue', 'Download queue'),
            ('/users', 'Active users (admin only)'),
            ('/test', 'System test'),
        ]
        
        for cmd, desc in commands:
            try:
                await self.test_command_response(cmd, desc)
                await asyncio.sleep(1)  # Wait between commands
            except Exception as e:
                print(f"   ❌ Error: {e}")
                self.results[cmd] = {'error': str(e)}
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate performance report."""
        print("\n" + "="*80)
        print("📊 LIVE BOT PERFORMANCE REPORT")
        print("="*80)
        
        if not self.results:
            print("No results to report")
            return
        
        # Calculate statistics
        successful = [r for r in self.results.values() if 'total_time' in r]
        
        if successful:
            avg_total = sum(r['total_time'] for r in successful) / len(successful)
            avg_response = sum(r['response_time'] for r in successful) / len(successful)
            min_time = min(r['total_time'] for r in successful)
            max_time = max(r['total_time'] for r in successful)
            
            print(f"\n📈 Statistics:")
            print(f"   Commands tested: {len(self.results)}")
            print(f"   Successful: {len(successful)}")
            print(f"   Failed: {len(self.results) - len(successful)}")
            print(f"\n⏱️  Response Times:")
            print(f"   Average: {avg_total*1000:.1f}ms")
            print(f"   Fastest: {min_time*1000:.1f}ms")
            print(f"   Slowest: {max_time*1000:.1f}ms")
            print(f"   Avg bot processing: {avg_response*1000:.1f}ms")
        
        # Detailed results
        print(f"\n📋 Detailed Results:")
        print(f"   {'Command':<15} {'Total Time':<12} {'Status'}")
        print(f"   {'-'*15} {'-'*12} {'-'*10}")
        
        for cmd, result in self.results.items():
            if 'total_time' in result:
                status = '✅'
                time_str = f"{result['total_time']*1000:.1f}ms"
            elif 'error' in result:
                status = '❌'
                time_str = 'ERROR'
            else:
                status = '⏱️'
                time_str = 'TIMEOUT'
            
            print(f"   {cmd:<15} {time_str:<12} {status}")
        
        # Save results
        with open('live_bot_performance.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'bot': BOT_USERNAME,
                'results': self.results,
                'statistics': {
                    'avg_total_time': avg_total if successful else 0,
                    'avg_response_time': avg_response if successful else 0,
                    'min_time': min_time if successful else 0,
                    'max_time': max_time if successful else 0,
                    'successful': len(successful),
                    'total': len(self.results)
                } if successful else {}
            }, f, indent=2)
        
        print(f"\n📁 Results saved to: live_bot_performance.json")
        print("="*80)
    
    async def cleanup(self):
        """Cleanup connections."""
        if self.client:
            await self.client.disconnect()


async def main():
    """Main test runner."""
    tester = LiveBotTester()
    
    try:
        await tester.connect()
        await tester.run_all_tests()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.cleanup()


if __name__ == '__main__':
    print("\n" + "="*80)
    print("⚠️  LIVE BOT TESTING")
    print("="*80)
    print("This will send REAL messages to your bot!")
    print("Make sure:")
    print("  1. Bot is running")
    print("  2. BOT_USERNAME is set in .env")
    print("  3. You have user credentials (API_ID, API_HASH)")
    print("="*80)
    
    response = input("\nContinue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        asyncio.run(main())
    else:
        print("Cancelled.")
