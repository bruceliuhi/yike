import type {
  Material,
  MaterialImpact,
  MaterialReceipt,
  MaterialRequest,
} from "../domain/materials";

/** Authenticated, versioned adapter. Absent from the production client until implemented. */
export interface MaterialService {
  list(profileVersionId: string): Promise<Material[]>;
  mutate(
    request: MaterialRequest,
    options: {
      signal: AbortSignal;
      onUploadProgress: (percent: number) => void;
    },
  ): Promise<MaterialReceipt>;
  operation(
    profileVersionId: string,
    requestId: string,
  ): Promise<MaterialReceipt>;
  impact(
    profileVersionId: string,
    materialId: string,
    version: number,
    action: "remove" | "revoke",
  ): Promise<MaterialImpact>;
}
