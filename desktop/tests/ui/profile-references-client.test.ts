// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {service, mapProfile, profileDescription} from '../../src/renderer/services/client';
import {profileSaveSchema} from '../../src/shared/profileMaterialReferences';
import {EMPTY_PROFILE} from '../../src/renderer/domain/models';
const profileId='11111111-1111-4111-8111-111111111111';
const referenceId='22222222-2222-4222-8222-222222222222';
const fields={...EMPTY_PROFILE,service:'知识库实施',customer:'企业',regions:'上海'};
const refs=[{field:'service',sourceProfileVersionId:profileId,materialId:'material-one',materialVersion:4,extractionId:'extract-one'}];
afterEach(()=>{delete (window as any).yikeDesktop;});
it('saves explicit provenance and maps authoritative saved references',async()=>{
  const savedRefs=[{field:'service',referenceId,valid:true}];
  const requestApi=vi.fn().mockResolvedValue({ok:true,status:200,data:{version_id:profileId,version:2,status:'DRAFT',material_references:savedRefs}});
  (window as any).yikeDesktop={requestApi};
  const saved=await service.saveProfile(fields,{baseProfileVersionId:profileId,materialReferences:refs as any});
  expect(requestApi).toHaveBeenCalledWith({operation:'profiles.save',payload:{description:profileDescription(fields),baseProfileVersionId:profileId,materialReferences:refs}});
  expect(saved.materialReferences).toEqual(savedRefs);
  expect(mapProfile({version_id:profileId,version:2,status:'CONFIRMED',payload:{description:profileDescription(fields)},material_references:[{...savedRefs[0],valid:false}]}).materialReferences?.[0].valid).toBe(false);
});
it('rejects duplicate fields, arbitrary keys, and inheritance without a base before transport',async()=>{
  const description=profileDescription(fields);
  expect(profileSaveSchema.safeParse({description,materialReferences:[refs[0],refs[0]]}).success).toBe(false);
  expect(profileSaveSchema.safeParse({description,materialReferences:[{...refs[0],tenantId:'other'}]}).success).toBe(false);
  expect(profileSaveSchema.safeParse({description,materialReferences:[{field:'service',referenceId}]}).success).toBe(false);
  const requestApi=vi.fn();(window as any).yikeDesktop={requestApi};
  await expect(service.saveProfile(fields,{materialReferences:[{field:'service',referenceId}]})).rejects.toBeDefined();
  expect(requestApi).not.toHaveBeenCalled();
});
it('does not accept missing or malformed provenance receipts as a successful reference save',async()=>{
  (window as any).yikeDesktop={requestApi:vi.fn().mockResolvedValue({ok:true,status:200,data:{version_id:profileId,version:1,status:'DRAFT'}})};
  await expect(service.saveProfile(fields,{materialReferences:refs as any})).rejects.toBeDefined();
  expect(()=>mapProfile({version_id:profileId,version:1,status:'DRAFT',payload:{description:profileDescription(fields)},material_references:[{field:'service',referenceId,valid:'yes'}]})).toThrow();
});
