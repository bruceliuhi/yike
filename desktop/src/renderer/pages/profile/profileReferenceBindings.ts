import type {Profile,ProfileFields} from '../../domain/models';
import type {Material} from '../../domain/materials';
import type {ProfileMaterialReference,ProfileReferenceOptions} from '../../../shared/profileMaterialReferences';
export type ReferenceBindings=Partial<Record<keyof ProfileFields,{reference:ProfileMaterialReference;value:string;valid:boolean}>>;
export function savedBindings(profile:Profile):ReferenceBindings{
  return Object.fromEntries((profile.materialReferences??[]).map(ref=>[ref.field,{reference:{field:ref.field,referenceId:ref.referenceId},value:profile.fields[ref.field],valid:ref.valid}]));
}
export function adoptedBindings(fields:Partial<ProfileFields>,record:Material):ReferenceBindings{
  return Object.fromEntries(Object.entries(fields).map(([field,value])=>[field,{reference:{field,sourceProfileVersionId:record.profileVersionId,materialId:record.id,materialVersion:record.version,extractionId:record.extraction!.id},value,valid:true}]));
}
export function bindingOptions(bindings:ReferenceBindings,profileId:string|null):ProfileReferenceOptions|undefined{
  const materialReferences=Object.values(bindings).map(binding=>binding!.reference);
  if(!materialReferences.length)return undefined;
  return {...(materialReferences.some(ref=>'referenceId'in ref)&&profileId?{baseProfileVersionId:profileId}:{}),materialReferences};
}
