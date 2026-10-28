import time
import functools
import logging
import json
from collections import defaultdict
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | ⏱️ %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class TimingStats:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.data = defaultdict(lambda: {"times": [], "count": 0})
        return cls._instance
    
    def add_measurement(self, name, duration_ms):
        self.data[name]["times"].append(duration_ms)
        self.data[name]["count"] += 1
        # Храним только последние 100 замеров
        if len(self.data[name]["times"]) > 100:
            self.data[name]["times"].pop(0)
    
    def get_stats(self, name):
        if name not in self.data or not self.data[name]["times"]:
            return None
        times = self.data[name]["times"]
        return {
            "count": len(times),
            "avg_ms": round(sum(times) / len(times), 1),
            "min_ms": round(min(times), 1),
            "max_ms": round(max(times), 1)
        }
    
    def print_all_stats(self):
        logger.info("=" * 60)
        logger.info("📊 СТАТИСТИКА ВРЕМЕНИ ВЫПОЛНЕНИЯ")
        logger.info("=" * 60)
        for name in sorted(self.data.keys()):
            stats = self.get_stats(name)
            if stats:
                logger.info(f"  {name}:")
                logger.info(f"    ├─ вызовов: {stats['count']}")
                logger.info(f"    ├─ среднее: {stats['avg_ms']} мс")
                logger.info(f"    ├─ минимум: {stats['min_ms']} мс")
                logger.info(f"    └─ максимум: {stats['max_ms']} мс")
        logger.info("=" * 60)
    
    def save_to_file(self, filename="timing_stats.json"):
        data = {}
        for name in self.data.keys():
            stats = self.get_stats(name)
            if stats:
                data[name] = stats
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"📁 Статистика сохранена в {filename}")
    
    def reset(self):
        self.data.clear()
        logger.info("🔄 Статистика сброшена")


stats = TimingStats()


# Декоратор для синхронных функций
def timeit_sync(name=None, log_level=logging.INFO):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = name or func.__name__
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                stats.add_measurement(func_name, duration_ms)
                logger.log(log_level, f"{func_name}: {duration_ms:.1f} мс")
        return wrapper
    return decorator


# Декоратор для асинхронных функций
def timeit_async(name=None, log_level=logging.INFO):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = name or func.__name__
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                stats.add_measurement(func_name, duration_ms)
                logger.log(log_level, f"{func_name}: {duration_ms:.1f} мс")
        return wrapper
    return decorator


# Контекстный менеджер для замера блоков кода
class timing_block:
    def __init__(self, name, log_level=logging.INFO):
        self.name = name
        self.log_level = log_level
    
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        duration_ms = (time.perf_counter() - self.start) * 1000
        stats.add_measurement(self.name, duration_ms)
        logger.log(self.log_level, f"{self.name}: {duration_ms:.1f} мс")