"""共同权重名次研究的离线验收脚本（不依赖数据库或网络）。

运行：python -m tests.test_common_weight
覆盖：闭式三馆、同分按编号、被支配场馆、百馆性能与独立复算、窄权重区间、
单位换算不变性、不可行权拒绝、超时降级与已证明界限。
"""
import time
import numpy as np
from src.services.common_weight import analyze_common_weights, total_order_rank


def _rec(i, staff, energy, visits, programs):
    return {'observation_id': i, 'venue_code': f'QY-{i:02d}', 'venue_name': f'馆{i}',
            'staff_hours': staff, 'energy_cost': energy, 'visits': visits, 'programs': programs}


def test_closed_form_three_venues():
    # 1 投入 2 产出 -> 两比值，归一矩阵恰好 [[1,0],[0,1],[.6,.6]]
    records = [_rec(1, 100, 100, 100, 0), _rec(2, 100, 100, 0, 100), _rec(3, 100, 100, 60, 60)]
    res = analyze_common_weights(records, ['staff_hours'], ['visits', 'programs'])
    assert res['status'] == 'completed' and res['proven_count'] == 3
    assert [(v['best_rank'], v['worst_rank']) for v in res['venues']] == [(1, 3), (1, 3), (2, 2)]
    codes = [r['venue_code'] for r in records]
    for v in res['venues']:
        idx = codes.index(v['venue_code'])
        assert total_order_rank(codes, np.array(v['best_scores']), idx) == v['best_rank']
        assert total_order_rank(codes, np.array(v['worst_scores']), idx) == v['worst_rank']
        for key in ('best_weights', 'worst_weights'):
            w = np.array(v[key])
            assert abs(w.sum() - 1) < 1e-9 and np.all(w >= -1e-12) and np.all(w <= 1 + 1e-12)


def test_identical_rows_code_tiebreak():
    records = [_rec(i + 1, 100, 100, 40, 40) for i in range(6)]
    res = analyze_common_weights(records, ['staff_hours'], ['visits', 'programs'])
    assert [(v['best_rank'], v['worst_rank']) for v in res['venues']] == \
        [(i, i) for i in range(1, 7)]


def test_dominated_venue_always_last():
    rng = np.random.default_rng(0)
    records = [_rec(i + 1, 1000, 20000, float(rng.uniform(8e3, 2e4)), float(rng.uniform(40, 90)))
               for i in range(6)]
    records[0] = _rec(1, 5000, 90000, 1000, 5)
    res = analyze_common_weights(records, ['staff_hours', 'energy_cost'], ['visits', 'programs'])
    assert (res['venues'][0]['best_rank'], res['venues'][0]['worst_rank']) == (6, 6)


def test_hundred_venues_performance_and_rerank():
    rng = np.random.default_rng(5)
    records = [_rec(i + 1, rng.uniform(800, 3000), rng.uniform(15000, 60000),
                    rng.uniform(5000, 30000), rng.uniform(20, 120)) for i in range(100)]
    started = time.time()
    res = analyze_common_weights(records, ['staff_hours', 'energy_cost'], ['visits', 'programs'])
    assert res['status'] == 'completed' and res['proven_count'] == 100
    assert time.time() - started < 60
    R = np.array(res['ratio_normalized'])
    codes = [r['venue_code'] for r in records]
    for v in res['venues']:
        idx = codes.index(v['venue_code'])
        assert total_order_rank(codes, np.array(v['best_scores']), idx) == v['best_rank']
        assert total_order_rank(codes, np.array(v['worst_scores']), idx) == v['worst_rank']
        assert v['best_rank'] <= v['worst_rank']


def test_narrow_weight_band_feasible():
    rng = np.random.default_rng(5)
    records = [_rec(i + 1, 1000, 20000, rng.uniform(5e3, 3e4), rng.uniform(20, 120)) for i in range(100)]
    res = analyze_common_weights(records, ['staff_hours'], ['visits', 'programs'],
                                 weight_lower=[.2, .25], weight_upper=[.7, .75])
    assert res['status'] == 'completed'
    for v in res['venues']:
        for key in ('best_weights', 'worst_weights'):
            w = np.array(v[key])
            assert .2 - 1e-9 <= w[0] <= .7 + 1e-9 and .25 - 1e-9 <= w[1] <= .75 + 1e-9
            assert abs(w.sum() - 1) < 1e-9


def test_unit_conversion_invariance():
    rng = np.random.default_rng(5)
    records = [_rec(i + 1, rng.uniform(800, 3000), rng.uniform(15000, 60000),
                    rng.uniform(5000, 30000), rng.uniform(20, 120)) for i in range(100)]
    scaled = [{**r, 'energy_cost': r['energy_cost'] * 1000} for r in records]
    a = analyze_common_weights(records, ['staff_hours', 'energy_cost'], ['visits', 'programs'])
    b = analyze_common_weights(scaled, ['staff_hours', 'energy_cost'], ['visits', 'programs'])
    assert np.array_equal(np.array(a['ratio_normalized']), np.array(b['ratio_normalized']))
    assert [(x['best_rank'], x['worst_rank']) for x in a['venues']] == \
           [(x['best_rank'], x['worst_rank']) for x in b['venues']]


def test_infeasible_band_rejected():
    records = [_rec(i + 1, 1000, 20000, 8000, 50) for i in range(5)]
    try:
        analyze_common_weights(records, ['staff_hours'], ['visits', 'programs'],
                                weight_lower=[.9, .9], weight_upper=[1., 1.])
    except ValueError as exc:
        assert '不相容' in str(exc)
    else:
        raise AssertionError('不可行权区间应被拒绝')


def test_timeout_degradation_keeps_proven_bounds():
    rng = np.random.default_rng(9)
    records = [_rec(i + 1, 1000, 20000, rng.uniform(5e3, 3e4), rng.uniform(20, 120)) for i in range(100)]
    res = analyze_common_weights(records, ['staff_hours'], ['visits', 'programs'], time_budget=0.05)
    assert res['status'] == 'degraded'
    assert res['proven_count'] < 100 and res['degrade_reasons']
    for v in res['venues']:
        assert 1 <= v['best_rank_bound'][0] <= v['best_rank_bound'][1] <= 100
        assert 1 <= v['worst_rank_bound'][0] <= v['worst_rank_bound'][1] <= 100
        if v['bounds_proven']:
            assert v['best_rank'] == v['best_rank_bound'][0] == v['best_rank_bound'][1]


def test_validation_rejects_bad_records():
    good = [_rec(i + 1, 100, 100, 50, 50) for i in range(3)]
    bad = [{**good[0], 'staff_hours': 0}] + good[1:]
    try:
        analyze_common_weights(bad, ['staff_hours'], ['visits', 'programs'])
    except ValueError as exc:
        assert '非正' in str(exc)
    else:
        raise AssertionError('零投入应被拒绝')
    dup = [_rec(1, 100, 100, 50, 50) for _ in range(3)]
    try:
        analyze_common_weights(dup, ['staff_hours'], ['visits', 'programs'])
    except ValueError as exc:
        assert '编号重复' in str(exc)
    else:
        raise AssertionError('重复机构编号应被拒绝')


def run_all():
    tests = [obj for name, obj in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
        print('PASS', test.__name__)
    print(f'common-weight tests: {len(tests)} passed')


if __name__ == '__main__':
    run_all()
