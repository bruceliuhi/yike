import {useEffect,useRef,useState} from 'react';
import {useApp} from '../../app/context';
import {useOperationLedger} from '../../app/operationLedger';
import {boundedRequest} from '../../app/boundedRequest';
import {useTaskScope} from './useTaskScope';
import {monitorCollectionCommandSchema,type MonitorCollectionCommand,type MonitorCollectionResult} from '../../../shared/monitorCollection';

type Write=Extract<MonitorCollectionCommand,{action:'CREATE'|'SET_STATE'}>;
type Listing=Extract<MonitorCollectionResult,{state:'LIST'}>;
export function useMonitorCollection(){
 const {service,session}=useApp(),scope=useTaskScope();
 const api=service.monitorCollection;
 const [ledger,setLedger]=useOperationLedger('monitor-operations',session.userId ? JSON.stringify([session.userId,session.accountScope??null]) : undefined);
 const [state,setState]=useState<{identity:object;list:Listing|null;error:string;busy:boolean}>({identity:scope.identity,list:null,error:'',busy:false});
 const lock=useRef<object|null>(null);
 const shown=state.identity===scope.identity?state:{identity:scope.identity,list:null,error:'',busy:false};
 const pending=Object.keys(ledger).map(key=>monitorCollectionCommandSchema.parse(JSON.parse(key)) as Write);
 function show(patch:Partial<typeof state>){if(scope.current())setState(old=>({...((old.identity===scope.identity)?old:{identity:scope.identity,list:null,error:'',busy:false}),...patch}));}
 async function call(command:MonitorCollectionCommand){
  if(!api || !session.authenticated || !scope.current())throw new Error();
  const result=await boundedRequest(()=>api.execute(command),{timeoutMessage:'监控响应等待超时，请核对原请求。'});
  if(!scope.current())throw new Error();return result;
 }
 const refresh=async()=>{
  if(!api || !session.authenticated)return;
  try{const list=await call({action:'LIST'});if(list.state!=='LIST')throw new Error();show({list,error:''});}
  catch{show({list:null,error:'监控状态暂时无法核实，请检查服务与账号后刷新。'});}
 };
 useEffect(()=>{void refresh();const timer=setInterval(()=>{if(lock.current!==scope.identity)void refresh();},20_000);return()=>clearInterval(timer);},[scope.identity,api]);
 async function execute(command:Exclude<MonitorCollectionCommand,{action:'LIST'}>):Promise<MonitorCollectionResult|null>{
  if(lock.current===scope.identity || !session.authenticated || !scope.current())return null;
  lock.current=scope.identity;show({busy:true,error:''});
  const write=command.action==='CREATE'||command.action==='SET_STATE'?command:null;
  const original=command.action==='RECEIPT'?command.command:write;
  const key=original?JSON.stringify(original):null;
  try{
   if(write)setLedger(old=>{
    if(Object.keys(old).some(existing=>{
     const value=monitorCollectionCommandSchema.parse(JSON.parse(existing)) as Write;
     return value.requestId===write.requestId || write.action==='CREATE' && value.action==='CREATE' && value.strategyVersionId===write.strategyVersionId ||
      write.action==='SET_STATE' && value.action==='SET_STATE' && value.planId===write.planId;
    }))throw new Error();
    return {...old,[key!]:'PENDING'};
   });
   const result=await call(command);
   if(key && (result.state==='RECORDED' || write && ['CONFLICT','INVALID_REQUEST'].includes(result.state)))
    setLedger(old=>{const next={...old};delete next[key];return next;});
   if(!['RECORDED','ATTACHED'].includes(result.state)){
    show({error:result.state==='CONFLICT'?'计划已变化或账号不匹配，请刷新后重新核对。':'操作结果尚未确认；请核对原请求与最新计划，不要重复创建。'});
   }
   if(['RECORDED','ATTACHED'].includes(result.state))await refresh();return result;
  }catch{show({error:'监控响应未核实，原请求已保留；请核对原请求，不要重新创建。'});return null;}
  finally{if(lock.current===scope.identity)lock.current=null;show({busy:false});}
 }
 return {...shown,pending,execute,refresh,available:!!api};
}
