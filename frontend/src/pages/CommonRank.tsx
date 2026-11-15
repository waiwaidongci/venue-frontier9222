import {useEffect,useMemo,useState} from 'react';
import {useLocation} from '../router';
import {researchStore,loadResearch} from '../stores/research';
import {exportCommonWeight} from '../api/runs';
import {useTask} from '../hooks/useTask';
import {usePolling} from '../hooks/usePolling';
import {number} from '../utils/format';
import {fields} from '../constants/enums';
import type {CommonWeightResult,CommonWeightVenue,Run} from '../types/domain';
import PageHeading from '../components/common/PageHeading';
import ErrorNotice from '../components/common/ErrorNotice';
import EmptyState from '../components/common/EmptyState';
import StatusBadge from '../components/common/StatusBadge';

function isCommon(run?:Run):run is Run&{result:CommonWeightResult}{return run?.kind==='common_weight';}

function RankBound({value,bound,proven}:{value:number|null;bound:[number,number];proven:boolean}){
  if(proven&&value!==null)return <b>{value}</b>;
  return <span className="bound-pill" title="未证明的名次界限">{bound[0]}–{bound[1]}<small>界限</small></span>;
}

export default function CommonRank(){
  const {query}=useLocation();
  const lab=researchStore.use();
  const {error,perform}=useTask();
  const [selected,setSelected]=useState(Number(query.get('run'))||0);
  const [code,setCode]=useState('');

  useEffect(()=>{
    perform(async()=>{
      await loadResearch();
      setSelected(id=>id||researchStore.get().runs.find(r=>r.kind==='common_weight')?.id||researchStore.get().runs[0]?.id||0);
    });
  },[perform]);
  useEffect(()=>{
    const id=Number(query.get('run'));
    if(id)setSelected(id);
  },[query.get('run')]);
  usePolling(async()=>{
    if(researchStore.get().runs.some(r=>r.id===selected&&['queued','running'].includes(r.status)))await loadResearch();
  });

  const run=lab.runs.find(r=>r.id===selected);
  const result=isCommon(run)?run.result:undefined;
  const venues=useMemo(()=>[...(result?.venues||[])].sort((a,b)=>{
    const ab=a.best_rank??a.best_rank_bound[0],bb=b.best_rank??b.best_rank_bound[0];
    return ab-bb||a.venue_code.localeCompare(b.venue_code);
  }),[result]);
  const target=venues.find(v=>v.venue_code===code)||venues[0];

  return <>
    <PageHeading index="04" title="共同权重下的名次边界与依据" text="最好/最差名次均来自同一组可行权重；近乎同分按实际分数与机构编号裁决，不做网格采样。"/>
    <ErrorNotice message={error} retry={()=>perform(loadResearch)}/>
    <div className="run-selector">
      <label>研究档案
        <select value={selected} onChange={e=>{setSelected(Number(e.target.value));setCode('');}}>
          {lab.runs.filter(r=>r.kind==='common_weight').map(r=><option key={r.id} value={r.id}>#{r.id} {r.name}</option>)}
        </select>
      </label>
      {run&&<StatusBadge status={run.status}/>}
      {result&&<span>{result.period} / {result.n}馆 / {result.ratio_columns.length}个比值列</span>}
      {result&&<a className="outline" href="#/common">切换研究</a>}
      {result&&<button className="outline" disabled={!run} onClick={()=>perform(()=>exportCommonWeight(run!.id))}>下载名次CSV ↓</button>}
    </div>

    {result&&target?<>
      {result.status==='degraded'&&(
        <div className="degrade-banner">
          <b>档案未完成：{result.proven_count}/{result.n} 馆的名次界限已证明</b>
          <span>时间预算 {result.time_budget_seconds}s 内未能证明全部最优；下表对未证明场馆展示已证明界限与求解状态。依据：{result.degrade_reasons.slice(0,3).join('；')}</span>
        </div>
      )}
      <div className="rank-layout">
        <section className="rank-table">
          <div className="section-heading"><h2>逐馆名次边界</h2><span>按最好名次排序，同分按机构编号</span></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>机构</th><th>最好名次</th><th>最差名次</th><th>证明</th><th/></tr></thead>
              <tbody>
                {venues.map(v=>(
                  <tr key={v.observation_id} className={v.venue_code===target.venue_code?'selected-row':''}
                      onClick={()=>setCode(v.venue_code)}>
                    <td><b>{v.venue_name}</b><small>{v.venue_code}</small></td>
                    <td><RankBound value={v.best_rank} bound={v.best_rank_bound} proven={v.bounds_proven}/></td>
                    <td><RankBound value={v.worst_rank} bound={v.worst_rank_bound} proven={v.bounds_proven}/></td>
                    <td>{v.bounds_proven?'已证明':<small className="rust">{v.best_solver_status}/{v.worst_solver_status}</small>}</td>
                    <td><button className="text-button" onClick={()=>setCode(v.venue_code)}>核对权重 ↗</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <VenueSheet result={result} target={target} onSelect={setCode}/>
      </div>
      <p className="fingerprint">COMMON-WEIGHT SHA256 / {result.fingerprint}</p>
    </>:<EmptyState title={run&&!isCommon(run)?'该档案是CCR效率研究':'等待共同权重求解'}
        text={run?.error||'请先在“共同权重”页建立研究；运行中状态会自动刷新。'}/>}
  </>;
}

function VenueSheet({result,target,onSelect}:{result:CommonWeightResult;target:CommonWeightVenue;onSelect:(code:string)=>void}){
  const cols=result.ratio_columns;
  const rows=useMemo(()=>[...result.venues].sort((a,b)=>a.venue_code.localeCompare(b.venue_code)),[result.venues]);
  return <section className="target-sheet common-sheet">
    <div className="target-selector">
      <label>目标机构
        <select value={target.venue_code} onChange={e=>onSelect(e.target.value)}>
          {rows.map(v=><option key={v.observation_id} value={v.venue_code}>{v.venue_code} / {v.venue_name}</option>)}
        </select>
      </label>
    </div>
    <div className="target-score">
      <span>最好 / 最差名次</span>
      <strong>{target.best_rank??'—'}<small> / </small>{target.worst_rank??'—'}</strong>
      <small>{target.bounds_proven?'界限已证明':'仅证明部分界限 '+target.best_rank_bound.join('–')+' / '+target.worst_rank_bound.join('–')}</small>
    </div>

    {(['best','worst'] as const).map(kind=>{
      const weights=kind==='best'?target.best_weights:target.worst_weights;
      const scores=kind==='best'?target.best_scores:target.worst_scores;
      const status=kind==='best'?target.best_solver_status:target.worst_solver_status;
      return <div className="weight-card" key={kind}>
        <h3>{kind==='best'?'达到最好名次的权重':'达到最差名次的权重'}<small>求解状态 {status}</small></h3>
        {weights&&<table>
          <thead><tr><th>比值列</th><th>权重</th><th>允许区间</th></tr></thead>
          <tbody>
            {cols.map((c,idx)=>(
              <tr key={c.label}>
                <td>{c.label}<small>{fields[c.output]} ÷ {fields[c.input]}</small></td>
                <td><b>{number(weights[idx],4)}</b></td>
                <td>{number(result.weight_lower[idx],3)} – {number(result.weight_upper[idx],3)}</td>
              </tr>
            ))}
          </tbody>
        </table>}
        {scores&&<div className="score-strip">
          <p className="input-note">该权重下全馆得分（列归一比值的加权和），目标馆 {target.venue_code} 得分 {number(scores[rows.findIndex(v=>v.venue_code===target.venue_code)],4)}</p>
          <div className="score-bars">
            {rows.map((v,i)=>(
              <div key={v.observation_id} className={v.venue_code===target.venue_code?'score-row self':'score-row'}>
                <span>{v.venue_code}</span>
                <i style={{width:`${Math.max(2,scores[i]*100)}%`}}/>
                <b>{number(scores[i],3)}</b>
              </div>
            ))}
          </div>
        </div>}
      </div>;
    })}
    <p className="input-note">{result.tie_policy}；{result.weight_policy}。权重和={number((target.best_weights||[]).reduce((a,b)=>a+b,0),6)}。</p>
  </section>;
}
