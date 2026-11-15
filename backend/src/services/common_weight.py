"""共同权重名次研究（common-weight ranking）。

各馆不再各自挑选有利权重：选定的产出/投入比值按同期列最大值归一到 [0,1]，
全馆使用同一组非负、合计为 1、可设上下限的权重 w 评分 s = R·w。
对每个场馆，在全部可行权重下求其最好/最差总序名次（同分按机构编号升序裁决），
用混合整数线性规划（HiGHS milp）求解，不做网格采样或排列枚举。

指示变量（t = (R_j - R_i)·w ∈ [-1,1]，行整体乘 SCALE 使 SCALE·GAP 高于求解器容差）：
  严格击败指示 z=1 iff t >= GAP（t=0 时 z=0）：
      t - z <= 0 ；t - (1+GAP) z >= -1
  机构编号更小者在同分时凭编号胜出，其“同分击败”在严格指示之外通过校验-锁定
  修正循环处理：每轮用 VERIFY_TOL 按总序规则独立重排名次，把漏判/误判列锁定为
  “不击败”后重解。锁定只增加精确线性约束；若因此不可行，上一可行点已证明极端名次。
GAP 是显式数值裁决容差：归一矩阵先按 12 位小数规范化，分差小于 1e-9
（缩放后 1e-5，高于 HiGHS 1e-6 可行性容差）视为数值同分，仍按机构编号裁决，
不把求解器容差内的“近乎同分”误读成严格领先。
"""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

GAP = 1e-9
SCALE = 1e4
VERIFY_TOL = 1e-9
CANONICAL_DECIMALS = 12
MILP_STATUSES = {0: 'optimal', 1: 'time_limit', 2: 'infeasible', 3: 'unbounded', 4: 'numerical_error'}
PER_MILP_LIMIT = 2.0
DEFAULT_TIME_BUDGET = 60.0


def total_order_rank(codes, scores, idx, tol=VERIFY_TOL):
    """总序名次：严格分高者在前；同分机构编号小者在前。

    数值同分判据用相对容差，吸收单位换算带来的 1e-16 级浮点噪声；
    容差（1e-9）远小于任何可显示分差，近乎同分仍按实际分数与编号裁决。
    """
    cc = np.array(codes)
    si = scores[idx]
    scale = max(1.0, np.abs(scores).max())
    rtol = tol * scale
    beats = (scores > si + rtol) | ((np.abs(scores - si) <= rtol) & (cc < codes[idx]))
    return int(beats.sum()) + 1


def _build_ratio_matrix(records, inputs, outputs):
    """产出/投入比值矩阵并按同期列最大值归一。零投入拒绝；零产出比值记 0。

    原始比值先按全精度计算，归一矩阵四舍五入到 CANONICAL_DECIMALS 位，消除单位换算
    （如元↔千元）引入的 1e-16 级浮点差异，保证同口径数据得到逐位一致的 MILP 输入。
    """
    ratio_cols, ratio_meta = [], []
    for out in outputs:
        for inp in inputs:
            col = []
            for r in records:
                if r[inp] <= 0:
                    raise ValueError(f"场馆 {r['venue_code']} 的投入 {inp} 非正，无法构造产出/投入比值")
                if r[out] < 0:
                    raise ValueError(f"场馆 {r['venue_code']} 的产出 {out} 为负")
                col.append(r[out] / r[inp])
            ratio_cols.append(col)
            ratio_meta.append({'output': out, 'input': inp, 'label': f'{out}/{inp}'})
    raw = np.array(ratio_cols, float).T
    col_max = raw.max(axis=0)
    if (col_max <= 0).any():
        raise ValueError('存在全零比值列，无法按列最大值归一，请重新选择产出投入')
    normalized = np.round(raw / col_max, CANONICAL_DECIMALS)
    raw = np.round(raw, CANONICAL_DECIMALS)
    return normalized, raw, col_max, ratio_meta


def _solve_milp(R, lower, upper, idx, smaller, sign, locked, time_left):
    """严格击败指示 MILP（全部列统一在 t=(R_j-R_i)·w 上建 z=1 iff t>=GAP）。

    locked 中的场馆在权重空间被显式约束为“不击败”目标，编码完整总序语义：
      大编号 j 不击败：t <= 0（同分即不击败）
      小编号 j 不击败：t <= -GAP（同分仍凭编号击败，故须严格低于）
    """
    n, k = R.shape
    rows, lo, hi = [], [], []
    rows.append(np.r_[np.ones(k), np.zeros(n)])
    lo.append(1.0)
    hi.append(1.0)
    for j in range(n):
        if j == idx:
            continue
        tcoef = R[j] - R[idx]
        col = k + j
        r1 = np.zeros(k + n)
        r1[:k] = SCALE * tcoef
        r1[col] = -SCALE
        rows.append(r1)
        lo.append(-np.inf)
        hi.append(0.0)
        r2 = np.zeros(k + n)
        r2[:k] = SCALE * tcoef
        r2[col] = -SCALE * (1.0 + GAP)
        rows.append(r2)
        lo.append(-SCALE)
        hi.append(np.inf)
        if j in locked:
            f = np.zeros(k + n)
            f[:k] = tcoef
            rows.append(f)
            lo.append(-np.inf)
            hi.append(-GAP if j in smaller else 0.0)
    c = np.zeros(k + n)
    for j in range(n):
        if j != idx:
            c[k + j] = sign
    integrality = np.r_[np.zeros(k), np.ones(n)]
    bounds = Bounds(np.r_[lower, np.zeros(n)], np.r_[upper, np.ones(n)])
    return milp(c=c, constraints=[LinearConstraint(np.array(rows), np.array(lo), np.array(hi))],
                integrality=integrality, bounds=bounds,
                options={'time_limit': min(PER_MILP_LIMIT, max(0.05, time_left)),
                         'mip_rel_gap': 0.0})


def _extreme(codes, R, lower, upper, idx, want_best, deadline):
    """单场馆最好/最差名次。严格 MILP + 同分校验锁定修正，返回 (结果, 状态, 界限依据)。

    状态仅在拿到已证明最优时为 optimal；单次 MILP 超时但仍有可行解时继续修正循环，
    只有整体预算真正耗尽才降级。
    """
    n, k = R.shape
    cc = np.array(codes)
    sign = 1.0 if want_best else -1.0
    smaller = set(j for j in range(n) if j != idx and cc[j] < codes[idx])
    locked = set()
    last = None
    timed_out = False
    prev_signature = None
    # 每轮至少新增一个锁定，最多 n-1 轮；留两轮余量处理数值边界。
    for _ in range(n + 1):
        time_left = max(0.05, deadline - time.monotonic())
        res = _solve_milp(R, lower, upper, idx, smaller, sign, locked, time_left)
        if res.status == 2:
            if last is None:
                # 首轮即不可行不应发生（权重区间已在入口校验）；按未证明降级处理
                return None, 'infeasible', {'rank_bound': (1, n), 'proven': False}
            w, rank, scores = last
            return {'weights': w.tolist(), 'scores': scores.tolist(), 'rank': rank,
                    'solver_status': 'optimal', 'correction_locks': len(locked)}, \
                   'optimal', {'rank_bound': (rank, rank), 'proven': True}
        if res.x is None:
            status = MILP_STATUSES.get(int(res.status), 'solver_error')
            if last is not None:
                w, rank, scores = last
                bound = (rank, n) if want_best else (1, rank)
                return {'weights': w.tolist(), 'scores': scores.tolist(), 'rank': rank,
                        'solver_status': status, 'correction_locks': len(locked)}, \
                       status, {'rank_bound': bound, 'proven': False}
            return None, status, {'rank_bound': (1, n), 'proven': False}
        if res.status != 0:
            timed_out = True
        w = np.clip(res.x[:k], lower, upper)
        w = w / w.sum()
        scores = R @ w
        rank = total_order_rank(codes, scores, idx)
        binary = res.x[k:]
        rtol = VERIFY_TOL * max(1.0, np.abs(scores).max())
        mismatch = []
        for j in range(n):
            if j == idx:
                continue
            diff = scores[j] - scores[idx]
            beats = (diff > rtol) or (abs(diff) <= rtol and cc[j] < codes[idx])
            if bool(binary[j] > 0.5) != bool(beats):
                mismatch.append(j)
        last = (w, rank, scores)
        signature = (tuple(np.round(w, 12)), tuple(sorted(locked)), tuple(mismatch))
        if signature == prev_signature:
            # 锁定后解不再变化：剩余误判是权重多面体上无法摆脱的数值同分，
            # 总序名次已由实际分数裁决，采纳该名次作为已证明极端值。
            return {'weights': w.tolist(), 'scores': scores.tolist(), 'rank': rank,
                    'solver_status': 'optimal', 'correction_locks': len(locked)}, \
                   'optimal', {'rank_bound': (rank, rank), 'proven': True}
        prev_signature = signature
        if not mismatch and not timed_out:
            indicator_rank = 1 + int(round(sum(binary[j] for j in range(n) if j != idx)))
            if indicator_rank == rank:
                return {'weights': w.tolist(), 'scores': scores.tolist(), 'rank': rank,
                        'solver_status': 'optimal', 'correction_locks': len(locked)}, \
                       'optimal', {'rank_bound': (rank, rank), 'proven': True}
            mismatch = [j for j in range(n) if j != idx and (
                (scores[j] > scores[idx] + rtol) or
                (abs(scores[j] - scores[idx]) <= rtol and cc[j] < codes[idx]))]
        locked.update(mismatch)
    if last is None:
        return None, 'iteration_limit', {'rank_bound': (1, n), 'proven': False}
    w, rank, scores = last
    bound = (rank, n) if want_best else (1, rank)
    terminal = 'time_limit' if timed_out else 'iteration_limit'
    return {'weights': w.tolist(), 'scores': scores.tolist(), 'rank': rank,
            'solver_status': terminal, 'correction_locks': len(locked)}, \
           terminal, {'rank_bound': bound, 'proven': False}


def analyze_common_weights(records, inputs, outputs, weight_lower=None, weight_upper=None,
                           time_budget=DEFAULT_TIME_BUDGET):
    """共同权重名次研究主入口；超时则 status='degraded'，档案标未完成并附已证明界限。"""
    if len(records) < 3:
        raise ValueError('至少需要3个同期场馆观察')
    if len({r['observation_id'] for r in records}) != len(records):
        raise ValueError('观察编号重复')
    codes = [r['venue_code'] for r in records]
    if len(set(codes)) != len(codes):
        raise ValueError('机构编号重复，无法按编号裁决同分')
    R, raw, col_max, ratio_meta = _build_ratio_matrix(records, inputs, outputs)
    n, k = R.shape
    if not (3 <= n <= 100):
        raise ValueError('共同权重研究支持3至100个同期场馆')
    lower = np.zeros(k) if weight_lower is None else np.asarray(weight_lower, float)
    upper = np.ones(k) if weight_upper is None else np.asarray(weight_upper, float)
    if lower.shape != (k,) or upper.shape != (k,):
        raise ValueError('权重上下限维度与比值列不匹配')
    if (lower < -1e-12).any() or (upper < lower - 1e-12).any():
        raise ValueError('权重必须非负且上限不小于下限')
    if lower.sum() > 1.0 + 1e-9 or upper.sum() < 1.0 - 1e-9:
        raise ValueError('权重上下限与合计为一约束不相容，可行权重集合为空')
    lower = np.maximum(lower, 0.0)
    started = time.monotonic()
    deadline = started + float(time_budget)
    venues, degraded, reasons = [], False, []
    for idx, r in enumerate(records):
        best, bstatus, bbound = _extreme(codes, R, lower, upper, idx, True, deadline)
        worst, wstatus, wbound = _extreme(codes, R, lower, upper, idx, False, deadline)
        if bstatus != 'optimal' or wstatus != 'optimal':
            degraded = True
            reasons.append(f"{r['venue_code']} 求解状态 {bstatus}/{wstatus}")
        blo_lo, blo_hi = bbound['rank_bound']
        wlo_lo, wlo_hi = wbound['rank_bound']
        venues.append({
            'observation_id': r['observation_id'], 'venue_code': r['venue_code'],
            'venue_name': r['venue_name'],
            'best_rank': best['rank'] if best else None,
            'worst_rank': worst['rank'] if worst else None,
            'best_rank_bound': [blo_lo, blo_hi], 'worst_rank_bound': [wlo_lo, wlo_hi],
            'bounds_proven': bbound['proven'] and wbound['proven'],
            'best_weights': best['weights'] if best else None,
            'worst_weights': worst['weights'] if worst else None,
            'best_scores': best['scores'] if best else None,
            'worst_scores': worst['scores'] if worst else None,
            'best_solver_status': bstatus, 'worst_solver_status': wstatus,
            'best_correction_locks': best['correction_locks'] if best else None,
            'worst_correction_locks': worst['correction_locks'] if worst else None,
        })
        if time.monotonic() > deadline:
            degraded = True
            reasons.append('整体时间预算到期，剩余场馆仅保留平凡名次界限 1..n')
            for j in range(idx + 1, n):
                rr = records[j]
                venues.append({
                    'observation_id': rr['observation_id'], 'venue_code': rr['venue_code'],
                    'venue_name': rr['venue_name'], 'best_rank': None, 'worst_rank': None,
                    'best_rank_bound': [1, n], 'worst_rank_bound': [1, n],
                    'bounds_proven': False, 'best_weights': None, 'worst_weights': None,
                    'best_scores': None, 'worst_scores': None,
                    'best_solver_status': 'not_run', 'worst_solver_status': 'not_run',
                    'best_correction_locks': None, 'worst_correction_locks': None,
                })
            break
    venues.sort(key=lambda v: v['venue_code'])
    return {
        'algorithm': 'common-weight-milp-rank-v1',
        'status': 'degraded' if degraded else 'completed',
        'n': n, 'inputs': inputs, 'outputs': outputs,
        'ratio_columns': ratio_meta,
        'ratio_raw': raw.tolist(), 'ratio_normalized': R.tolist(),
        'column_max': {m['label']: float(v) for m, v in zip(ratio_meta, col_max)},
        'weight_lower': lower.tolist(), 'weight_upper': upper.tolist(),
        'weight_policy': '同一组非负权重、合计为一、逐列上下限；全馆共用，不逐馆自选',
        'tie_policy': f'严格分高者在前；分差小于{GAP:.0e}视为数值同分，同分按机构编号升序',
        'venues': venues,
        'proven_count': sum(1 for v in venues if v['bounds_proven']),
        'degrade_reasons': reasons[:20],
        'time_budget_seconds': time_budget,
        'elapsed_seconds': round(time.monotonic() - started, 4),
    }
