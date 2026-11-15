import json,csv,io
from fastapi import HTTPException
from src.models import EfficiencyRun
from src.constants.enums import RunKind
def export_common_weight(run:EfficiencyRun):
    if run.kind!=RunKind.COMMON_WEIGHT:raise HTTPException(422,'该研究不是共同权重名次研究')
    result=run.result
    cols=[m['label'] for m in result['ratio_columns']]
    def safe(value):
        text=str(value)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    out=io.StringIO();out.write('﻿');w=csv.writer(out)
    header=['venue_code','venue_name','best_rank','worst_rank','best_rank_bound','worst_rank_bound','bounds_proven',
            'best_weights_'+ '|'.join(cols),'worst_weights_'+'|'.join(cols),
            'best_scores_'+'|'.join(cols),'worst_scores_'+'|'.join(cols),
            'best_solver_status','worst_solver_status','run_status','fingerprint']
    w.writerow(header)
    for v in result['venues']:
        w.writerow([
            safe(v['venue_code']),safe(v['venue_name']),
            v['best_rank'],v['worst_rank'],
            '-'.join(map(str,v['best_rank_bound'])),'-'.join(map(str,v['worst_rank_bound'])),
            v['bounds_proven'],
            '|'.join('' if x is None else f'{x:.6g}' for x in (v['best_weights'] or [])),
            '|'.join('' if x is None else f'{x:.6g}' for x in (v['worst_weights'] or [])),
            '|'.join('' if x is None else f'{x:.6g}' for x in (v['best_scores'] or [])),
            '|'.join('' if x is None else f'{x:.6g}' for x in (v['worst_scores'] or [])),
            v['best_solver_status'],v['worst_solver_status'],result['status'],result.get('fingerprint',''),
        ])
    return out.getvalue()
