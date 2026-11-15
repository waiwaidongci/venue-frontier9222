from pydantic import BaseModel,Field,model_validator
from src.constants.enums import INPUTS,OUTPUTS,RunKind
class RunInput(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    benchmark_id:int
    kind:str=RunKind.DEA
    inputs:list[str]=Field(default_factory=lambda:list(INPUTS),min_length=1,max_length=2)
    outputs:list[str]=Field(default_factory=lambda:list(OUTPUTS),min_length=1,max_length=2)
    sensitivity_count:int=Field(default=3,ge=1,le=3)
    weight_lower:list[float]|None=None
    weight_upper:list[float]|None=None
    time_budget:float=Field(default=60.0,ge=1.0,le=180.0)
    @model_validator(mode='after')
    def keys_valid(self):
        if len(set(self.inputs))!=len(self.inputs) or len(set(self.outputs))!=len(self.outputs) or any(f not in INPUTS for f in self.inputs) or any(f not in OUTPUTS for f in self.outputs):raise ValueError('投入产出字段非法或重复')
        if self.kind not in (RunKind.DEA,RunKind.COMMON_WEIGHT):raise ValueError('研究类型非法')
        if self.kind==RunKind.COMMON_WEIGHT:
            k=len(self.inputs)*len(self.outputs)
            lo=self.weight_lower or [0.0]*k
            hi=self.weight_upper or [1.0]*k
            if len(lo)!=k or len(hi)!=k:raise ValueError('权重上下限数量须等于投入产出比值列数')
            if any(v<0 or v>1 for v in lo+hi):raise ValueError('权重上下限须落在[0,1]')
            if any(h<l for l,h in zip(lo,hi)):raise ValueError('权重上限不得小于下限')
            if sum(lo)>1+1e-9 or sum(hi)<1-1e-9:raise ValueError('权重上下限与合计为一约束不相容')
        return self
