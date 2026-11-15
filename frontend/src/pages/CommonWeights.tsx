import {useEffect,useMemo,useState} from 'react';
import {researchStore,loadResearch} from '../stores/research';
import {createRun} from '../api/runs';
import {useTask} from '../hooks/useTask';
import {usePolling} from '../hooks/usePolling';
import {fields,inputKeys,outputKeys} from '../constants/enums';
import PageHeading from '../components/common/PageHeading';
import ErrorNotice from '../components/common/ErrorNotice';
import BenchmarkSelect from '../components/BenchmarkSelect';

interface BandRow{label:string;lower:string;upper:string}

export default function CommonWeights(){
  const lab=researchStore.use();
  const {busy,error,perform}=useTask();
  const [name,setName]=useState('Q3 · 共同权重名次边界');
  const [benchmarkId,setBenchmarkId]=useState(0);
  const [inputs,setInputs]=useState<string[]>([inputKeys[0]]);
  const [outputs,setOutputs]=useState<string[]>([...outputKeys]);
  const [bands,setBands]=useState<BandRow[]>([]);
  const [budget,setBudget]=useState(60);
  const [message,setMessage]=useState('');

  useEffect(()=>{
    perform(async()=>{
      await loadResearch();
      setBenchmarkId(id=>id||researchStore.get().benchmarks.at(-1)?.id||0);
    });
  },[perform]);
  usePolling(async()=>{
    if(researchStore.get().runs.some(r=>['queued','running'].includes(r.status)))await loadResearch();
  });

  const ratioCount=inputs.length*outputs.length;
  const ratioLabels=useMemo(()=>{
    const labels:string[]=[];
    outputs.forEach(o=>inputs.forEach(i=>labels.push(`${o}/${i}`)));
    return labels;
  },[inputs,outputs]);

  useEffect(()=>{
    setBands(prev=>{
      const next=ratioLabels.map((label,idx)=>({
        label,
        lower:prev[idx]&&prev[idx].label===label?prev[idx].lower:'0',
        upper:prev[idx]&&prev[idx].label===label?prev[idx].upper:'1',
      }));
      return next.length===prev.length&&next.every((r,i)=>r.label===prev[i]?.label)?prev:next;
    });
  },[ratioLabels.join('|')]);

  function toggle(kind:'inputs'|'outputs',key:string){
    const current=kind==='inputs'?inputs:outputs;
    const next=current.includes(key)?current.filter(x=>x!==key):[...current,key];
    if(kind==='inputs')setInputs(next);else setOutputs(next);
  }

  const bandValid=bands.every(b=>{
    const lo=Number(b.lower),hi=Number(b.upper);
    return Number.isFinite(lo)&&Number.isFinite(hi)&&lo>=0&&hi<=1&&hi>=lo;
  });
  const lowerSum=bands.reduce((s,b)=>s+Number(b.lower||0),0);
  const upperSum=bands.reduce((s,b)=>s+Number(b.upper||0),0);
  const feasible=bandValid&&lowerSum<=1+1e-9&&upperSum>=1-1e-9;

  async function submit(){
    const payload={
      name,benchmark_id:benchmarkId,kind:'common_weight',inputs,outputs,
      sensitivity_count:3,
      weight_lower:bands.map(b=>Number(b.lower)),
      weight_upper:bands.map(b=>Number(b.upper)),
      time_budget:budget,
    };
    const run=await createRun(payload);
    setMessage(`共同权重研究 #${run.id} 已进入求解队列。完成后在名次页查看每馆最好/最差名次与对应权重。`);
    await loadResearch();
  }

  return <>
    <PageHeading index="04" title="共同权重：让所有馆接受同一把尺子" text="比值按同期最大值归一，全馆共用一组非负、合计为一的权重；逐馆求可行权重下的最好与最差名次。"><a className="outline" href="#/common-rank">查看名次边界 ↗</a></PageHeading>
    <ErrorNotice message={error} retry={()=>perform(loadResearch)}/>
    <div className="solver-layout">
      <form className="research-form" onSubmit={e=>{e.preventDefault();perform(submit);}}>
        <h2>建立共同权重名次研究</h2>
        <label>研究名称<input value={name} onChange={e=>setName(e.target.value)} required minLength={2}/></label>
        <BenchmarkSelect value={benchmarkId} onChange={setBenchmarkId} benchmarks={lab.benchmarks}/>
        {(['inputs','outputs'] as const).map(kind=>(
          <fieldset key={kind}>
            <legend>{kind==='inputs'?'投入维度（至少1项）':'产出维度（至少1项）'}<small>比值=每项产出/每项投入，共{ratioCount}列</small></legend>
            {(kind==='inputs'?inputKeys:outputKeys).map(key=>(
              <label className="checkbox" key={key}>
                <input type="checkbox" checked={(kind==='inputs'?inputs:outputs).includes(key)} onChange={()=>toggle(kind,key)}/>
                {fields[key]}
              </label>
            ))}
          </fieldset>
        ))}
        <fieldset>
          <legend>权重上下限<small>{ratioCount}列，非负且须与合计为一相容</small></legend>
          <div className="table-wrap">
            <table className="band-table">
              <thead><tr><th>比值列</th><th>下限</th><th>上限</th></tr></thead>
              <tbody>
                {bands.map((b,idx)=>(
                  <tr key={b.label}>
                    <td><b>{b.label}</b><small>{fields[b.label.split('/')[0]]} ÷ {fields[b.label.split('/')[1]]}</small></td>
                    <td><input aria-label={`${b.label}下限`} inputMode="decimal" value={b.lower}
                      onChange={e=>setBands(bs=>bs.map((row,j)=>j===idx?{...row,lower:e.target.value}:row))}/></td>
                    <td><input aria-label={`${b.label}上限`} inputMode="decimal" value={b.upper}
                      onChange={e=>setBands(bs=>bs.map((row,j)=>j===idx?{...row,upper:e.target.value}:row))}/></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={'input-note'+(feasible?'':' rust')}>
            下限合计 {lowerSum.toFixed(3)} ≤ 1 ≤ 上限合计 {upperSum.toFixed(3)}；{feasible?'可行权重集合非空':'当前区间与合计为一不相容，无法求解'}
          </p>
        </fieldset>
        <label>求解时间预算（秒，超时降级并保留已证明名次界限）
          <input type="number" min={1} max={180} value={budget} onChange={e=>setBudget(Number(e.target.value))}/>
        </label>
        <button className="primary" disabled={busy||!inputs.length||!outputs.length||!feasible||bands.length!==ratioCount}>
          提交共同权重新求解 →
        </button>
        {message&&<p className="success" role="status">{message}</p>}
      </form>
      <aside className="model-sheet">
        <p className="eyebrow">COMMON WEIGHT / SHARED RANK</p>
        <h2>各馆不再各挑<br/>有利权重。</h2>
        <div className="model-formula">
          <b>s = R·w</b>
          <span>w ≥ 0，Σw = 1，l ≤ w ≤ u<br/>R 为列最大值归一后的产出/投入比值<br/>全馆同一组 w，同分按机构编号排序</span>
        </div>
        <ol>
          <li><b>同期归一，可核对</b><p>每个产出/投入比值除以该列同期最大值，原始比值、列最大值与归一矩阵都随档案保存，单位换算不改变归一结果。</p></li>
          <li><b>MILP 求名次边界</b><p>对每馆用混合整数规划求全部可行权重下的最好/最差名次，附实现该名次的权重向量与全馆得分；不做网格采样或排列枚举，支持百馆。</p></li>
          <li><b>超时降级，不填假名次</b><p>预算到期的档案标记“未完成/已降级”，逐馆给出已证明的名次界限与求解依据，剩余场馆保留 1..n 平凡界限。</p></li>
        </ol>
      </aside>
    </div>
  </>;
}
