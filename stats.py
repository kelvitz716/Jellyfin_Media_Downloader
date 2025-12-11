from collections import deque
from datetime import datetime
from tinydb import where
from database import stats_tbl


class BotStats:
    # Maximum samples to keep in memory for rolling averages
    MAX_SAMPLES = 1000
    
    def __init__(self):
        self.start_time = datetime.now()
        self.files_handled = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.total_data = 0
        self.peak_concurrent = 0
        # Bounded deques for rolling averages (prevents memory growth)
        self.download_times = deque(maxlen=self.MAX_SAMPLES)
        self.download_speeds = deque(maxlen=self.MAX_SAMPLES)
        # Running totals for accurate lifetime averages
        self._total_time = 0.0
        self._total_speed_sum = 0.0
        self._samples_count = 0


    global_stats = None
    user_stats = {}

    @classmethod
    def load_all(cls):
        """Load stats from TinyDB into memory."""
        # Global
        gs = stats_tbl.get(where('type') == 'global')
        if gs:
            for k, v in gs.items():
                if k != 'type': setattr(cls.global_stats, k, v)
        # Per-user
        for row in stats_tbl.search(where('type').matches(r'^user_\d+$')):
            uid = int(row['type'].split('_',1)[1])
            bs = BotStats()
            for k, v in row.items():
                if k not in ('type',): setattr(bs, k, v)
            cls.user_stats[uid] = bs

    @classmethod
    def save_all(cls):
        """Persist stats from memory to TinyDB."""
        # Global
        gs = vars(cls.global_stats).copy()
        gs['type'] = 'global'
        gs.pop('start_time', None)
        stats_tbl.upsert(gs, where('type') == 'global')
        # Per-user
        for uid, bs in cls.user_stats.items():
            doc = vars(bs).copy()
            doc['type'] = f'user_{uid}'
            doc.pop('start_time', None)
            stats_tbl.upsert(doc, where('type') == f'user_{uid}')

    @classmethod
    def record_download(cls, user_id, size, duration, success=True):
        """Update in-memory and persist."""
        cls.global_stats.add_download(size, duration, success)
        if user_id not in cls.user_stats:
            cls.user_stats[user_id] = BotStats()
        cls.user_stats[user_id].add_download(size, duration, success)
        cls.save_all()

    def add_download(self, size, duration, success=True):
        self.files_handled += 1
        if success:
            self.successful_downloads += 1
            self.total_data += size
            self.download_times.append(duration)
            speed = size / duration if duration > 0 else 0
            self.download_speeds.append(speed)
            # Track running totals for accurate lifetime averages
            self._total_time += duration
            self._total_speed_sum += speed
            self._samples_count += 1
        else:
            self.failed_downloads += 1

    def update_peak_concurrent(self, current):
        if current > self.peak_concurrent:
            self.peak_concurrent = current

    def get_uptime(self):
        return datetime.now() - self.start_time

    def get_average_speed(self):
        """Get lifetime average download speed."""
        return (self._total_speed_sum / self._samples_count) if self._samples_count > 0 else 0

    def get_average_time(self):
        """Get lifetime average download time."""
        return (self._total_time / self._samples_count) if self._samples_count > 0 else 0
    
    def get_rolling_average_speed(self):
        """Get rolling average speed (last MAX_SAMPLES downloads)."""
        return (sum(self.download_speeds) / len(self.download_speeds)) if self.download_speeds else 0
    
    def get_rolling_average_time(self):
        """Get rolling average time (last MAX_SAMPLES downloads)."""
        return (sum(self.download_times) / len(self.download_times)) if self.download_times else 0

# Initialize global stats
stats = BotStats()
BotStats.global_stats = stats
BotStats.load_all()
