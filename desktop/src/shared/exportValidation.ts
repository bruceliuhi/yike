import type {ExportRequest} from './contracts';

export const MAX_EXPORT_BYTES = 2 * 1024 * 1024;
export const exportExtension = (format: ExportRequest['format']) =>
  format === 'csv' ? '.csv' : '.yike-backup.json';

/** Both browser and main validate; the renderer cannot choose a path or file type. */
export function validatedExport(input: unknown): ExportRequest | null {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return null;
  const value = input as Record<string, unknown>;
  if (Object.keys(value).length !== 3 || !Object.keys(value).every(key => ['format', 'name', 'content'].includes(key))) return null;
  if (value.format !== 'csv' && value.format !== 'backup-json') return null;
  if (typeof value.name !== 'string' || typeof value.content !== 'string') return null;
  const extension = exportExtension(value.format);
  const name = value.name.toLowerCase().endsWith(extension)
    ? value.name.slice(0, -extension.length) : value.name;
  if (!/^[\p{L}\p{N}][\p{L}\p{N} _().-]{0,79}$/u.test(name)
    || name !== name.trim() || name.endsWith('.') || name.includes('..')
    || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) return null;
  if (!value.content || value.content.includes('\0') || value.content.length > MAX_EXPORT_BYTES
    || new TextEncoder().encode(value.content).byteLength > MAX_EXPORT_BYTES) return null;
  if (value.format === 'backup-json') {
    try {
      const parsed: unknown = JSON.parse(value.content);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    } catch { return null; }
  }
  return {format: value.format, name: name + extension, content: value.content};
}
