import {z} from 'zod';
export const profileMaterialField = z.enum(['service','customer','regions','preference','exclusions']);
const id=z.string().trim().min(1).max(200).refine(value=>!value.includes('\0'));
export const profileMaterialReference=z.union([
  z.object({field:profileMaterialField,referenceId:z.string().uuid()}).strict(),
  z.object({field:profileMaterialField,sourceProfileVersionId:z.string().uuid(),materialId:id,
    materialVersion:z.number().int().min(1).max(2147483647),extractionId:id}).strict(),
]);
export const savedMaterialReferences=z.array(z.object({field:profileMaterialField,referenceId:z.string().uuid(),valid:z.boolean()}).strict())
  .max(5).refine(values=>new Set(values.map(value=>value.field)).size===values.length);
export const profileSaveSchema=z.object({
  description:z.string().max(8000).refine(value=>!!value.trim()),
  baseProfileVersionId:z.string().uuid().optional(),
  materialReferences:z.array(profileMaterialReference).max(5)
    .refine(values=>new Set(values.map(value=>value.field)).size===values.length).optional(),
}).strict().refine(value=>!value.materialReferences?.some(ref=>'referenceId' in ref)||!!value.baseProfileVersionId);
export type ProfileMaterialReference=z.infer<typeof profileMaterialReference>;
export type SavedMaterialReference=z.infer<typeof savedMaterialReferences>[number];
export type ProfileReferenceOptions=Pick<z.infer<typeof profileSaveSchema>,'baseProfileVersionId'|'materialReferences'>;
