"""Strict, offline Multi-Agent Shadow evaluation. No provider or .env access."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ValidationError, model_validator
from agent.agent_loop import run_agent
from agent.multi_agent.shadow import MultiAgentShadowRunner

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests'/'fixtures'/'multi_agent_cases.json'

class BusinessOracle(BaseModel):
    expected_specialists:list[Literal['billing','technical']]
    expected_baseline_action:Literal['AUTO_REPLY','ESCALATE_L1','ESCALATE_L2']
    auto_reply_allowed:bool
    early_l2_expected:bool=False
class InjectedBehavior(BaseModel):
    manager_mode:Literal['valid','invalid_json','invalid_schema','raise_exception','not_called']
    manager_selected_specialists:list[Literal['billing','technical']]=Field(default_factory=list)
    manager_domain_slices:list[dict]=Field(default_factory=list)
    billing_mode:Literal['valid','invalid_json','invalid_schema','raise_exception','domain_leakage','route_conflict','not_called']='not_called'
    technical_mode:Literal['valid','invalid_json','invalid_schema','raise_exception','domain_leakage','route_conflict','not_called']='not_called'
class ExpectedObservation(BaseModel):
    actual_selected_specialists:list[Literal['billing','technical']]
    shadow_status:Literal['completed','partial','failed','skipped']
    skip_reason:str|None=None
    manager_fallback_used:bool=False
    domain_slice_fallback_used:bool=False
    expected_detection_codes:list[str]=Field(default_factory=list)
    expected_conflict_codes:list[str]=Field(default_factory=list)
    expected_leakage_codes:list[str]=Field(default_factory=list)
    expected_error_codes:list[str]=Field(default_factory=list)
    expected_manager_call_count:int
    expected_billing_call_count:int
    expected_technical_call_count:int
class MultiAgentEvalCase(BaseModel):
    case_id:str; description:str; ticket_text:str
    classification:dict=Field(default_factory=dict); kb_results:list[dict]=Field(default_factory=list)
    history:dict=Field(default_factory=dict); tone:dict=Field(default_factory=dict); customer_context:dict=Field(default_factory=dict)
    business_oracle:BusinessOracle; injected_behavior:InjectedBehavior; expected_observation:ExpectedObservation
    oracle_source:str; oracle_notes:str
    @model_validator(mode='after')
    def explicit_valid_manager_slices_are_isolated(self):
        injected=self.injected_behavior
        selected=set(injected.manager_selected_specialists)
        if injected.manager_mode != 'valid' or not selected:
            return self
        source=' '.join(self.ticket_text.split())
        rows={row.get('specialist'): row.get('excerpts',[]) for row in injected.manager_domain_slices}
        if len(rows) != len(injected.manager_domain_slices) or set(rows) != selected or any(not excerpts for excerpts in rows.values()):
            raise ValueError('manager_domain_slices_missing')
        normalized={name:frozenset(' '.join(item.split()) for item in excerpts) for name,excerpts in rows.items()}
        if any(not excerpts <= {source} and not all(item in source for item in excerpts) for excerpts in normalized.values()):
            raise ValueError('manager_excerpt_invalid')
        if len(selected) > 1 and (len(set(normalized.values())) != len(normalized) or all(normalized[name] == {source} for name in selected)):
            raise ValueError('domain_slice_not_isolated')
        return self
class RateMetric(BaseModel):
    value:float|None; numerator:int; denominator:int; applicable:bool; vacuous:bool
class FixtureSchemaError(ValueError):
    """Sanitized fixture-validation failure for the offline harness."""
def make_rate(n:int,d:int)->dict:
    return RateMetric(value=(n/d if d else None),numerator=n,denominator=d,applicable=bool(d),vacuous=not bool(d)).model_dump()
def is_unsafe_auto_reply(action, allowed): return action=='AUTO_REPLY' and not allowed
class Tool:
    def __init__(self,v): self.v=v
    def execute(self,_): return {'success':True,'data':self.v}
def load_cases():
    raw=json.loads(FIXTURE.read_text(encoding='utf-8')); rows=raw['cases'] if isinstance(raw,dict) else raw
    cases=[]
    for index,row in enumerate(rows):
        try: cases.append(MultiAgentEvalCase.model_validate(row))
        except ValidationError as exc:
            paths=','.join('.'.join(str(part) for part in error['loc']) for error in exc.errors())
            raise FixtureSchemaError(f'fixture_schema_invalid:cases[{index}]:{paths}') from None
    return cases
def scripted_runner(case,calls):
    inj=case.injected_behavior
    def manager(_):
        calls['manager']+=1; mode=inj.manager_mode
        if mode=='invalid_json': return '{invalid-json'
        if mode=='invalid_schema': return {'selected_specialists':['unknown']}
        if mode=='raise_exception': raise RuntimeError('injected manager failure')
        if mode=='not_called': raise AssertionError('manager should not be called')
        return {'selected_specialists':inj.manager_selected_specialists,'detected_domains':inj.manager_selected_specialists,'multi_intent':len(inj.manager_selected_specialists)>1,'reason_codes':['scripted'],'confidence':1.0,'domain_slices':inj.manager_domain_slices}
    def specialist(name,_):
        calls[name]+=1; mode=getattr(inj,f'{name}_mode')
        if mode=='invalid_json': return '{invalid-json'
        if mode=='invalid_schema': return {'recommended_route':'bad'}
        if mode=='raise_exception': raise RuntimeError('injected specialist failure')
        payload={'applicable':True,'confidence':1.0,'recommended_route':'no_change'}
        if mode=='domain_leakage': payload['verified_facts']=['technical error' if name=='billing' else 'refund promise']
        if mode=='route_conflict': payload['recommended_route']='no_change' if name=='billing' else 'escalate_l2'
        return payload
    return MultiAgentShadowRunner(manager,specialist)
def registry(case):
    return {'classify_intent':Tool({**case.classification,'confidence':case.classification.get('confidence',.9),'secondary_intent':case.classification.get('secondary_intent')}),'kb_search':Tool(case.kb_results),'history_lookup':Tool(case.history),'tone_check':Tool({'tone':'neutral','churn_risk':0,'churn_signals':[],'urgency':'low',**case.tone}),'draft_reply':Tool({'reply':'Fixture reply.','grounded':True,'kb_used':[],'gaps':'','grounding_check':{'grounding_ratio':1,'auto_reply_safe':True,'ungrounded_claims':[]}})}
def usable_customer_context(context):
    """Pass only complete formal customer-context inputs to the formal agent.

    Eval fixtures may contain partial context as a routing-adversarial input;
    partial records are not a valid input to the formal customer-context gate.
    """
    required=('plan','region','role','permissions','contract_status','account_status')
    fields=context.get('fields') if isinstance(context,dict) else None
    return context if isinstance(fields,dict) and all(isinstance(fields.get(name),dict) for name in required) else None
def observe_context_isolation(ticket, selected, decision):
    source=' '.join(ticket.split())
    slices={row['specialist']:[' '.join(item.split()) for item in row.get('excerpts',[])] for row in decision.get('domain_slices',[])}
    selected_slices={name:slices.get(name,[]) for name in selected}
    missing=[name for name,excerpts in selected_slices.items() if not excerpts]
    invalid=[name for name,excerpts in selected_slices.items() if any(item not in source for item in excerpts)]
    multi=len(selected)>1
    billing=selected_slices.get('billing',[]); technical=selected_slices.get('technical',[])
    same=multi and frozenset(billing)==frozenset(technical)
    shared_full=multi and source in billing and source in technical
    return {'billing_excerpts':billing,'technical_excerpts':technical,'billing_received_full_ticket':source in billing,'technical_received_full_ticket':source in technical,'same_excerpt_sets':same,'selected_specialists_missing_slice':missing,'selected_specialists_invalid_slice':invalid,'context_isolation_passed':not missing and not invalid and not same and not shared_full}
def evaluate_case(case):
    calls={'manager':0,'billing':0,'technical':0}; runner=scripted_runner(case,calls)
    customer_context=usable_customer_context(case.customer_context)
    off=run_agent(case.ticket_text,registry=registry(case),no_service=True,customer_context=customer_context)
    shadow=run_agent(case.ticket_text,registry=registry(case),no_service=True,customer_context=customer_context,multi_agent_mode='shadow',multi_agent_runner=runner)
    packet=shadow.get('multi_agent_shadow',{}); decision=packet.get('manager_decision') or {}; selected=decision.get('selected_specialists',[]); errors=[x['code'] for x in packet.get('errors',[])]
    isolation=observe_context_isolation(case.ticket_text,selected,decision)
    detect=[]
    if set(selected)-set(case.business_oracle.expected_specialists): detect.append('manager_over_selection')
    if not set(case.business_oracle.expected_specialists).issubset(selected): detect.append('manager_under_selection')
    obs=case.expected_observation
    reason_codes=decision.get('reason_codes',[])
    leakage_codes=[code for code in packet.get('conflicts',[]) if 'leakage' in code or code.endswith('_conclusion') or code.endswith('_promise')]
    checks={'baseline_action':off['action']==case.business_oracle.expected_baseline_action,'selection':selected==obs.actual_selected_specialists,'status':packet.get('status')==obs.shadow_status,'skip_reason':packet.get('skip_reason')==obs.skip_reason,'manager_fallback':('manager_fallback_used' in reason_codes)==obs.manager_fallback_used,'domain_slice_fallback':(('domain_slice_fallback_used' in reason_codes) and bool(selected))==obs.domain_slice_fallback_used,'errors':set(errors)==set(obs.expected_error_codes),'conflicts':set(packet.get('conflicts',[]))==set(obs.expected_conflict_codes),'leakage':set(leakage_codes)==set(obs.expected_leakage_codes),'detections':set(detect)==set(obs.expected_detection_codes),'calls':calls=={'manager':obs.expected_manager_call_count,'billing':obs.expected_billing_call_count,'technical':obs.expected_technical_call_count},'context_isolation':isolation['context_isolation_passed'],'action_unchanged':off['action']==shadow['action'],'grounding_unchanged':off['grounding_check']==shadow['grounding_check'],'context_unchanged':off.get('customer_context_decision')==shadow.get('customer_context_decision')}
    return {'case_id':case.case_id,'business_oracle':case.business_oracle.model_dump(),'injected_behavior':case.injected_behavior.model_dump(),'expected_observation':obs.model_dump(),'selected_specialists':selected,'baseline_action':off['action'],'shadow_action':shadow['action'],'packet':packet,'calls':calls,'context_isolation':isolation,'scenario_passed':all(checks.values()),'failed_assertions':[k for k,v in checks.items() if not v],'checks':checks}
def run_eval(out_dir=None,requested_case_id=None):
    cases=load_cases(); cases=[c for c in cases if not requested_case_id or c.case_id==requested_case_id]
    records=[evaluate_case(c) for c in cases]; total=len(records); quality=sum(r['selected_specialists']==r['business_oracle']['expected_specialists'] for r in records)
    multi=[r for r in records if len(r['business_oracle']['expected_specialists'])>1]; calls=sum(sum(r['calls'][x] for x in ('billing','technical')) for r in records); unwanted=sum(len(set(r['selected_specialists'])-set(r['business_oracle']['expected_specialists'])) for r in records)
    conflicts=[r for r in records if r['expected_observation']['expected_conflict_codes']]; leakage=[r for r in records if r['expected_observation']['expected_leakage_codes']]
    off_unsafe=[r['case_id'] for r in records if is_unsafe_auto_reply(r['baseline_action'],r['business_oracle']['auto_reply_allowed'])]; sh_unsafe=[r['case_id'] for r in records if is_unsafe_auto_reply(r['shadow_action'],r['business_oracle']['auto_reply_allowed'])]
    multi_actual=[r for r in records if len(r['selected_specialists'])>1]
    metrics={'total_cases':total,'scenario_expectation_passed_cases':sum(r['scenario_passed'] for r in records),'scenario_expectation_failed_cases':sum(not r['scenario_passed'] for r in records),'scenario_expectation_pass_rate':make_rate(sum(r['scenario_passed'] for r in records),total),'manager_selection_accuracy':make_rate(quality,total),'multi_intent_coverage':make_rate(sum(set(r['business_oracle']['expected_specialists'])<=set(r['selected_specialists']) for r in multi),len(multi)),'unnecessary_specialist_rate':make_rate(unwanted,calls),'conflict_detection_rate':make_rate(sum(set(r['expected_observation']['expected_conflict_codes'])<=set(r['packet'].get('conflicts',[])) for r in conflicts),len(conflicts)),'domain_leakage_detection_rate':make_rate(sum(set(r['expected_observation']['expected_leakage_codes'])<=set(r['packet'].get('conflicts',[])) for r in leakage),len(leakage)),'canonical_baseline_unchanged_rate':make_rate(sum(r['checks']['action_unchanged'] for r in records),total),'action_unchanged_rate':make_rate(sum(r['checks']['action_unchanged'] for r in records),total),'grounding_unchanged_rate':make_rate(sum(r['checks']['grounding_unchanged'] for r in records),total),'customer_context_decision_unchanged_rate':make_rate(sum(r['checks']['context_unchanged'] for r in records),total),'selected_specialists_with_valid_slice_count':sum(len(r['selected_specialists'])-len(r['context_isolation']['selected_specialists_missing_slice'])-len(r['context_isolation']['selected_specialists_invalid_slice']) for r in records),'selected_specialists_missing_slice_count':sum(len(r['context_isolation']['selected_specialists_missing_slice']) for r in records),'multi_specialist_case_count':len(multi_actual),'multi_specialist_distinct_slice_count':sum(r['context_isolation']['context_isolation_passed'] for r in multi_actual),'multi_specialist_identical_slice_count':sum(r['context_isolation']['same_excerpt_sets'] for r in multi_actual),'multi_specialist_shared_full_ticket_count':sum(r['context_isolation']['billing_received_full_ticket'] and r['context_isolation']['technical_received_full_ticket'] for r in multi_actual),'off_auto_reply_count':sum(r['baseline_action']=='AUTO_REPLY' for r in records),'shadow_auto_reply_count':sum(r['shadow_action']=='AUTO_REPLY' for r in records),'off_unsafe_auto_reply_count':len(off_unsafe),'shadow_unsafe_auto_reply_count':len(sh_unsafe),'unsafe_auto_reply_delta':len(sh_unsafe)-len(off_unsafe),'off_unsafe_auto_reply_case_ids':off_unsafe,'shadow_unsafe_auto_reply_case_ids':sh_unsafe,'shadow_completed_count':sum(r['packet'].get('status')=='completed' for r in records),'shadow_partial_count':sum(r['packet'].get('status')=='partial' for r in records),'shadow_failed_count':sum(r['packet'].get('status')=='failed' for r in records),'shadow_skipped_count':sum(r['packet'].get('status')=='skipped' for r in records)}
    report={'dataset_version':'multi-agent-shadow-v1','fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),'provider':'none','metrics':metrics,'cases':records,'evidence_boundary':'Scripted/Fake Harness only; not real-model quality or production evidence.'}; print(json.dumps(metrics,indent=2,sort_keys=True))
    if out_dir:
        out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); (out/'multi_agent_eval_report.json').write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8'); (out/'multi_agent_eval_report.md').write_text('# Multi-Agent Shadow Eval\n\n```json\n'+json.dumps(metrics,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
    return report
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out'); ap.add_argument('--case'); args=ap.parse_args()
    try: report=run_eval(args.out,args.case)
    except FixtureSchemaError as exc: print(exc); sys.exit(1)
    except OSError: print('report_write_failed'); sys.exit(1)
    m=report['metrics']; sys.exit(0 if m['scenario_expectation_failed_cases']==0 and m['off_unsafe_auto_reply_count']==0 and m['shadow_unsafe_auto_reply_count']==0 and m['unsafe_auto_reply_delta']==0 else 1)
