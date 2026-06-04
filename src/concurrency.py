from __future__ import annotations
"""并发调度 + 限流模块"""
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore

from src.data_fetcher import fetch_daily_kline


class RateLimiter:
    """akshare 请求限速器 — 每秒最多 N 次"""

    def __init__(self, max_per_second: int = 10):
        self.semaphore = Semaphore(max_per_second)
        self.min_interval = 1.0 / max_per_second
        self.last_release = time.time()

    def acquire(self):
        self.semaphore.acquire()
        elapsed = time.time() - self.last_release
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def release(self):
        self.last_release = time.time()
        self.semaphore.release()


def fetch_one_with_retry(code: str, rate_limiter: RateLimiter,
                         max_retries: int = 3, calendar_days: int = 200):
    """带限流和重试的单只股票数据获取"""
    for attempt in range(max_retries):
        try:
            rate_limiter.acquire()
            df = fetch_daily_kline(code, calendar_days=calendar_days)
            return df
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  [WARN] {code} 获取失败(重试{max_retries}次): {e}")
                return None
            time.sleep(2 ** attempt + random.uniform(0, 1))
        finally:
            rate_limiter.release()
    return None


def fetch_all_candidates(codes: list[str], max_workers: int = 8,
                         max_per_second: int = 10,
                         calendar_days: int = 200) -> dict[str, dict]:
    """
    并发获取所有候选股日线数据

    返回: {code: df_dict} — df_dict 是 DataFrame.to_dict('records') 的结果
    """
    import pandas as pd
    rate_limiter = RateLimiter(max_per_second)
    results = {}

    print(f"  并发获取 {len(codes)} 只候选股日线 ({max_workers}线程, {max_per_second}次/秒)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for code in codes:
            future = executor.submit(
                fetch_one_with_retry, code, rate_limiter, 3, calendar_days
            )
            futures[future] = code

        done = 0
        for future in as_completed(futures):
            code = futures[future]
            done += 1
            try:
                df = future.result()
                if df is not None and len(df) > 0:
                    results[code] = df
            except Exception as e:
                print(f"  [ERROR] {code}: {e}")

            if done % 10 == 0:
                print(f"    进度: {done}/{len(codes)}")

    print(f"  完成: {len(results)}/{len(codes)} 只获取成功")
    return results
