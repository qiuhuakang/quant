from __future__ import annotations
"""独立实现：二板涨停N型战法 — 不依赖项目现有代码"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import akshare as ak
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

TODAY = '2026-05-15'
CALENDAR_DAYS = 200

def to_sina(code):
    code = str(code).strip()
    if code.startswith(('0','3')): return f'sz{code}'
    elif code.startswith('6'): return f'sh{code}'
    return ''

def fetch_kline(code):
    """获取个股日线"""
    sym = to_sina(code)
    if not sym:
        return None
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=CALENDAR_DAYS)).strftime('%Y%m%d')
    try:
        df = ak.stock_zh_a_daily(symbol=sym, start_date=start, end_date=end, adjust='qfq')
        if df is None or df.empty:
            return None
        df = df.rename(columns={'date':'trade_date','open':'open','high':'high',
                                'low':'low','close':'close','volume':'volume'})
        df['pct_chg'] = round(df['close'].pct_change() * 100, 2)
        df = df.reset_index(drop=True)
        return df
    except Exception as e:
        return None

def find_two_boards(df):
    """找到最近一次连续2个涨停的位置"""
    if df is None or len(df) < 2:
        return None
    df = df.reset_index(drop=True)
    limit_flags = (df['pct_chg'] >= 9.8) & (df['close'] >= df['high'] * 0.98)
    for i in range(len(limit_flags)-2, -1, -1):
        if limit_flags.iloc[i] and limit_flags.iloc[i+1]:
            return {'start_idx': i, 'end_idx': i+1,
                    'start_date': str(df.iloc[i]['trade_date']),
                    'end_date': str(df.iloc[i+1]['trade_date'])}
    return None

def calc_fib(df, start_idx, end_idx):
    """黄金分割位"""
    seg = df.iloc[start_idx:end_idx+1]
    hi, lo = seg['high'].max(), seg['low'].min()
    rng = hi - lo
    return {'high': hi, 'low': lo, 'fib_618': round(lo + rng * 0.618, 2)}

def is_ladder(volumes):
    """阶梯量判定"""
    if len(volumes) < 3:
        return False
    ma = volumes.rolling(3).mean().dropna()
    if len(ma) < 2:
        return False
    dec = sum(ma.iloc[i] < ma.iloc[i-1] * 0.95 for i in range(1, len(ma)))
    return dec >= len(ma) * 0.6

def judge_stage(df, start_idx):
    """拉升阶段判定（基于最新交易日）"""
    last = len(df) - 1
    pre = df.iloc[max(0, last-20):last]
    if len(pre) < 10:
        return 'unknown', False
    rise = (pre['close'].iloc[-1] - pre['close'].iloc[0]) / pre['close'].iloc[0] * 100
    lb60 = df.iloc[max(0, last-59):last+1]
    lb120 = df.iloc[max(0, last-119):last+1]
    ma60 = lb60['close'].mean()
    ma120 = lb120['close'].mean()
    cur = df.iloc[last]['close']
    if ma60 > ma120 and cur > ma60:
        if rise < 25: stage = 'early'
        elif rise < 50: stage = 'mid'
        else: stage = 'late'
        return stage, stage in ('early', 'mid')
    return 'unqualified', False

print('='*70)
print(f'  二板涨停N型战法 — 独立实现 ({TODAY})')
print('='*70)

# ── Step 1: 涨停池 ──
print(f'\n[Step 1] 获取涨停池...')
zt = ak.stock_zt_pool_em(date=TODAY.replace('-', ''))
print(f'  涨停 {len(zt)} 只')

# 当日连板数==2
two_today = zt[zt['连板数'] == 2]
gt2_today = set(zt[zt['连板数'] > 2]['代码'].tolist())
print(f'  2连板: {len(two_today)} 只 | 连板>2: {len(gt2_today)} 只')

# ── Step 2: 回溯近期所有2连板候选 ──
print(f'\n[Step 2] 回溯近15交易日2连板...')
cal = ak.tool_trade_date_hist_sina()
trade_dates = sorted([str(d) if not isinstance(d,str) else d for d in cal['trade_date'].tolist()])

# 找today在交易日历中的位置
if TODAY in trade_dates:
    today_idx = trade_dates.index(TODAY)
else:
    today_idx = max(i for i,d in enumerate(trade_dates) if d < TODAY)
    TODAY = trade_dates[today_idx]
    print(f'  修正选股日: {TODAY}')

window_start_idx = max(0, today_idx - 15)
window_start = trade_dates[window_start_idx]

# 从旧到新扫描，排除连板>2的
print(f'  扫描范围: {window_start} ~ {TODAY}')
exclude_set = set()
candidates = {}  # code -> {'date': xxx, 'name': xxx}

for d in reversed(trade_dates[window_start_idx:today_idx+1]):
    try:
        pool = ak.stock_zt_pool_em(date=d.replace('-', ''))
        if pool is None or pool.empty:
            continue
        gt2 = pool[pool['连板数'] > 2]
        for _, r in gt2.iterrows():
            exclude_set.add(r['代码'])
        two = pool[(pool['连板数'] == 2) & (~pool['代码'].isin(exclude_set))]
        for _, r in two.iterrows():
            if r['代码'] not in candidates:
                candidates[r['代码']] = {'date': d, 'name': r['名称']}
    except:
        continue
    time.sleep(0.3)

print(f'  候选池: {len(candidates)} 只')

# ── Step 3: 逐个获取日线 + 分析 ──
print(f'\n[Step 3] 逐个分析...')
results = []
done = 0
for code, info in candidates.items():
    done += 1
    if done % 20 == 0:
        print(f'  进度: {done}/{len(candidates)}')

    df = fetch_kline(code)
    if df is None:
        continue

    # 找2连板
    boards = find_two_boards(df)
    if boards is None:
        continue

    lu_start, lu_end = boards['start_idx'], boards['end_idx']

    # 调整数据
    adj_start = lu_end + 1
    if adj_start >= len(df):
        continue
    adj_df = df.iloc[adj_start:].copy()
    adj_days = len(adj_df)
    if adj_days == 0:
        continue

    # 黄金分割
    fib = calc_fib(df, lu_start, lu_end)

    # 缩量：二板后首日成交量 / 第二板成交量
    second_board_vol = df.iloc[lu_end]['volume']
    first_adj_vol = adj_df['volume'].iloc[0]
    vol_ratio = round(first_adj_vol / second_board_vol, 3) if second_board_vol > 0 else 1.0
    vol_shrink = vol_ratio < 1.0

    # 阶梯量
    ladder = is_ladder(adj_df['volume'])

    # 阳线
    true_yang = int((adj_df['close'] > adj_df['close'].shift(1)).sum())
    false_yang = int(((adj_df['close'] > adj_df['open']) & (adj_df['close'] < adj_df['close'].shift(1))).sum())
    yang_ratio = round((true_yang + false_yang) / len(adj_df), 3)

    # 拉升阶段
    stage, stage_ok = judge_stage(df, lu_start)

    # 不破618
    adj_min = adj_df['close'].min()
    above_fib = adj_min >= fib['fib_618']

    # 板上调整
    second_close = df.iloc[lu_end]['close']
    above_board = adj_df['low'].min() >= second_close * 0.98

    # 夹板震荡
    adj_high = adj_df['high'].max()
    sandwich = above_board and (adj_high <= fib['high'] * 1.02)

    # 基础条件
    meets = all([vol_shrink, adj_days <= 5, stage_ok, above_fib])

    # 评分
    score = 0.0
    score += max(0, 15 - (adj_days - 1) * 2.5)
    score += max(5, 20 - (vol_ratio - 0.2) * 18.75)
    score += {'early': 20, 'mid': 15}.get(stage, 0)
    score += 15 if above_fib else 5
    if ladder: score += 10
    score += min(8, yang_ratio * 8)
    if above_board: score += 6
    if sandwich: score += 6
    score = round(min(score, 100), 1)

    buy_price = round(df.iloc[-1]['close'], 2)
    if buy_price > second_close:
        protect_price, protect_type = second_close, '板上保护'
    else:
        protect_price, protect_type = fib['fib_618'], '板内(618)'

    results.append({
        'code': code, 'name': info['name'], 'score': score,
        'board_end': boards['end_date'], 'adj_days': adj_days,
        'vol_ratio': vol_ratio, 'yang_ratio': yang_ratio,
        'fib_618': fib['fib_618'], 'adj_min': adj_min,
        'ladder': ladder, 'stage': stage, 'above_board': above_board,
        'sandwich': sandwich, 'meets': meets,
        'buy': buy_price, 'protect': protect_price, 'protect_type': protect_type,
        'sell_3': round(buy_price*1.03,2), 'sell_5': round(buy_price*1.05,2)
    })

# ── Step 4: 输出 ──
passed = [r for r in results if r['meets']]
passed.sort(key=lambda x: x['score'], reverse=True)
excluded = [r for r in results if not r['meets']]

print(f'\n{"="*70}')
print(f'  结果: 通过 {len(passed)} 只 / 未达标 {len(excluded)} 只')
print(f'{"="*70}')

if passed:
    print(f'\n【入选标的】')
    print(f'{"排名":<5} {"代码":<10} {"名称":<8} {"评分":<6} {"连板结束":<12} {"调整":<5} {"量比":<7} {"阳线%":<7} {"买入价":<8} {"保护位":<8} {"保护类型":<10}')
    print('-'*85)
    for i, r in enumerate(passed):
        print(f'{i+1:<5} {r["code"]:<10} {r["name"]:<8} {r["score"]:<6} '
              f'{r["board_end"]:<12} {r["adj_days"]:<5} {r["vol_ratio"]:<7} '
              f'{r["yang_ratio"]:<7} {r["buy"]:<8} {r["protect"]:<8} {r["protect_type"]:<10}')

    print(f'\n【买卖点】')
    for r in passed:
        print(f'  {r["code"]} {r["name"]}: 买入{r["buy"]}, +3%={r["sell_3"]}, +5%={r["sell_5"]}, 保护={r["protect"]}({r["protect_type"]})')

if excluded:
    print(f'\n【未达标】({len(excluded)}只) 按原因分组:')
    from collections import defaultdict
    groups = defaultdict(list)
    for r in excluded:
        reasons = []
        if r['adj_days'] > 5: reasons.append('调整超5天')
        if r['vol_ratio'] >= 1.0: reasons.append('未缩量')
        if r['adj_min'] < r['fib_618']: reasons.append('破618')
        if not reasons: reasons.append('阶段不达标')
        groups[' + '.join(reasons)].append(f"{r['code']} {r['name']}")
    for key, stocks in sorted(groups.items()):
        print(f'  [{key}] ({len(stocks)}只):')
        for s in stocks:
            print(f'    {s}')
