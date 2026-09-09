import { FileText } from "@phosphor-icons/react";
import { Badge, Button, formatDate } from "../../components/ui";
import type { MaterialDraft } from "../../domain/models";

export interface LocalMaterialDraft extends MaterialDraft {
  purpose: string;
}

export function LocalMaterialDrafts({
  drafts, onEdit, onRemove, onTransfer, transferDisabled = false,
}: {
  drafts: LocalMaterialDraft[];
  onEdit: (draft: LocalMaterialDraft) => void;
  onRemove: (draft: LocalMaterialDraft) => void;
  onTransfer?: (draft: LocalMaterialDraft) => void;
  transferDisabled?: boolean;
}) {
  return <div className="table-scroll material-table">
    <table>
      <thead><tr><th>资料名称</th><th>用途</th><th>引用范围</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>{drafts.map(entry => <tr key={entry.id}>
        <td><FileText aria-hidden />{entry.name}<small>{formatDate(entry.updatedAt)}</small></td>
        <td>{entry.purpose}</td>
        <td>{entry.visibility === "internal" ? "仅供内部判断" : "允许对外引用（待确认）"}</td>
        <td><Badge>本机草稿</Badge></td>
        <td><div className="inline-actions">
          <Button variant="ghost" onClick={() => onEdit(entry)}>编辑</Button>
          <Button variant="ghost" onClick={() => onRemove(entry)}>删除</Button>
          {onTransfer && <Button variant="ghost" disabled={transferDisabled} onClick={() => onTransfer(entry)}>带入当前画像</Button>}
        </div></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
