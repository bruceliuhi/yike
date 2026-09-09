import { useOperationLedger } from "../../app/operationLedger";
import { ServiceError } from "../../services/contracts";
import {
  candidateOperation,
  parseCandidateOperation,
  type CandidateDecision,
  type CandidateReviewOperation,
} from "../../domain/candidateReviewOperation";

export function useCandidateReviewLedger(userId?: string) {
  const [entries, setEntries] = useOperationLedger("candidate-reviews", userId);
  const records = Object.keys(entries).flatMap((key) => {
    const record = parseCandidateOperation(key);
    return record ? [record] : [];
  });
  const begin = async (request: CandidateDecision, current: () => boolean) => {
    const operation = await candidateOperation(request);
    if (!current())
      throw new ServiceError("REQUEST_CANCELLED", "已离开本次复核，尚未提交。");
    setEntries((old) => {
      if (
        Object.keys(old).some(
          (key) =>
            parseCandidateOperation(key)?.candidateId === request.candidateId,
        )
      )
        throw new ServiceError(
          "REVIEW_PENDING",
          "上次复核结果尚未核对，未再次提交。",
        );
      return { ...old, [operation.key]: "PENDING" };
    });
    return operation;
  };
  const release = (operation: CandidateReviewOperation) =>
    setEntries((old) => {
      const next = { ...old };
      delete next[operation.key];
      return next;
    });
  return { records, begin, release };
}
