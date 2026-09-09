import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import { connections, monitor, profile, TEST_USER } from "./fixtures";

/** Explicit TEST-only state alignment with R3. Never imported by the product renderer. */
export function applyReferenceState(service: YikeService, page: string) {
  service.connections = async () => structuredClone(connections);
  if (page === "P03")
    service.profiles = async () => [
      {
        ...structuredClone(profile),
        status: "DRAFT",
        fields: { ...profile.fields, regions: "" },
      },
    ];
  if (page === "P05" || page === "P08") service.tasks = async () => [];
  if (page === "P09")
    service.tasks = async () => [
      {
        ...structuredClone(monitor),
        statistics: undefined,
        platformStages: monitor.platformStages?.map((row, index) =>
          index < 2
            ? { ...row, newCount: undefined }
            : {
                ...row,
                status: "WAITING",
                newCount: undefined,
                reason: "TEST 等待平台运行结果",
              },
        ),
      },
    ];
  if (page === "P14" || page === "P15") {
    const unavailable = async (): Promise<never> => {
      throw new ServiceError(
        "CAPABILITY_UNAVAILABLE",
        "TEST 空态夹具不执行跟进更改。",
        501,
      );
    };
    service.followup = {
      list: async () => ({
        records: [],
        members: [{ id: TEST_USER, name: "TEST 当前成员" }],
      }),
      replies: async () => [],
      mutate: unavailable,
      operation: unavailable,
    };
  }
}
