import {useState} from 'react';
import {useApp} from '../../app/context';
import {useResource} from '../../app/hooks';
import {boundedRequest} from '../../app/boundedRequest';
import {Button,Notice} from '../../components/ui';
import {parseMaterials} from '../../domain/materials';
import type {ContactDraft,Opportunity} from '../../domain/models';
import {draftMaterialReferenceSchema} from '../../../shared/contactDrafts';

/** Only explicit, owner-visible source excerpts enter a draft. Saving and
 * final qualification remain server-owned; this list grants no permission. */
export function ContactMaterialQuotes({row,draft,onChange,disabled}:{row:Opportunity;draft:ContactDraft;
 onChange:(change:Partial<ContactDraft>)=>void;disabled:boolean}) {
 const {service,session}=useApp();
 const [attempt,setAttempt]=useState(0);
 const enabled=!disabled&&session.authenticated&&!!service.materials&&!!service.contactDrafts;
 const identity=JSON.stringify([session.authenticated,session.userId,session.accountScope,row.id,row.profileVersionId,draft.channel]);
 const resource=useResource(async()=>enabled?parseMaterials(await boundedRequest(()=>service.materials!.list(row.profileVersionId),
  {timeoutMessage:'读取业务资料超时，请重试。'}),row.profileVersionId):[],[service,identity,enabled,attempt]);
 const refs=draft.materialReferences??[];
 if(!enabled&&!refs.length)return null;
 const choices=enabled&&!resource.loading&&!resource.error?(resource.data??[]).filter(m=>m.status==='READY'&&m.visibility==='external')
  .flatMap(m=>Array.from(new Set(m.extraction!.evidence.map(e=>e.quote))).map(quote=>({name:m.name,ref:{sourceProfileVersionId:m.profileVersionId,
   materialId:m.id,materialVersion:m.version,extractionId:m.extraction!.id,quote}}))):[];
 return <details className="contact-routing"><summary>引用业务资料{refs.length?` · ${refs.length}段`:''}</summary>
  <p className="field-hint">请选择允许对外引用的资料。</p>
  {refs.map((ref,index)=><div key={JSON.stringify(ref)}><p>{resource.data?.find(material=>material.id===ref.materialId)?.name || `已选资料 ${index+1}`}</p><blockquote>{ref.quote}</blockquote>
   {!draft.content.includes(ref.quote)&&<Notice tone="warning">引用片段已被编辑，请重新选用或移除引用。</Notice>}
   <Button disabled={disabled} onClick={()=>onChange({content:draft.content.split(ref.quote).join(''),materialReferences:refs.filter((_,i)=>i!==index)})}>移除引用片段</Button></div>)}
  {enabled&&resource.loading&&<p role="status">正在读取可引用资料…</p>}
  {enabled&&resource.error&&<Notice tone="error">{resource.error}<Button onClick={()=>setAttempt(n=>n+1)}>重新读取业务资料</Button></Notice>}
  {enabled&&!resource.loading&&!resource.error&&!choices.length&&<p>当前画像没有可引用的已确认外部资料。</p>}
  {choices.map(({name,ref})=><div key={JSON.stringify(ref)}><p>{name}</p><blockquote>{ref.quote}</blockquote>
   <Button disabled={refs.length>=3||refs.some(r=>JSON.stringify(r)===JSON.stringify(ref))||draft.content.length+ref.quote.length+1>8000}
    onClick={()=>{const checked=draftMaterialReferenceSchema.parse(ref);onChange({content:draft.content+(draft.content?'\n':'')+checked.quote,materialReferences:[...refs,checked]});}}>带入资料片段</Button></div>)}
 </details>;
}
