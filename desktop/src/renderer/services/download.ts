import {
  EXPORT_ERROR_CODES, type ExportErrorCode, type ExportRequest,
  type SaveExportResult, type YikeDesktopApi
} from '../../shared/contracts';
import {validatedExport} from '../../shared/exportValidation';

export type DownloadResult = SaveExportResult | {status: 'initiated'};
export function downloadErrorMessage(error: ExportErrorCode): string {
  if (error === 'INVALID_EXPORT_REQUEST') return '导出内容或文件名不符合要求，请检查格式及 2 MiB 大小限制。';
  if (error === 'EXPORT_BUSY') return '请先完成当前保存窗口，再尝试导出。';
  if (error === 'INVALID_EXPORT_DESTINATION') return '请选择与导出格式一致的文件扩展名。';
  if (error === 'EXPORT_UNAVAILABLE') return '当前客户端不支持保存导出文件，请更新客户端。';
  return '文件未能保存，请检查保存位置后重试。';
}

export async function downloadText(input: ExportRequest): Promise<DownloadResult> {
  const request = validatedExport(input);
  if (!request) return {status: 'error', error: 'INVALID_EXPORT_REQUEST'};
  const bridge = (window as unknown as {yikeDesktop?: YikeDesktopApi}).yikeDesktop;
  if (bridge || window.location.protocol === 'yike:') {
    if (!bridge?.saveExport) return {status: 'error', error: 'EXPORT_UNAVAILABLE'};
    try {
      const result: unknown = await bridge.saveExport(request);
      if (result && typeof result === 'object') {
        const response = result as Record<string, unknown>;
        if (response.status === 'saved') return {status: 'saved'};
        if (response.status === 'cancelled') return {status: 'cancelled'};
        if (response.status === 'error' && EXPORT_ERROR_CODES.includes(response.error as ExportErrorCode))
          return {status: 'error', error: response.error as ExportErrorCode};
      }
    } catch { /* Never show IPC exception details or paths. */ }
    return {status: 'error', error: 'EXPORT_FAILED'};
  }
  if (!['http:', 'https:'].includes(window.location.protocol)) return {status: 'error', error: 'EXPORT_UNAVAILABLE'};
  let url: string | undefined;
  try {
    url = URL.createObjectURL(new Blob([request.content], {
      type: request.format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8'
    }));
    const link = document.createElement('a');
    link.href = url;
    link.download = request.name;
    link.click();
    return {status: 'initiated'};
  } catch { return {status: 'error', error: 'EXPORT_FAILED'}; }
  finally { if (url) window.setTimeout(() => URL.revokeObjectURL(url!), 1000); }
}
