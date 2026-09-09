import {randomUUID} from 'node:crypto';
import {open, rename, rm} from 'node:fs/promises';
import path from 'node:path';
import type {ExportRequest, SaveExportResult} from '../shared/contracts';
import {exportExtension, validatedExport} from '../shared/exportValidation';

interface ExportDependencies<Event> {
  isTrusted(event: Event): boolean;
  chooseFile(event: Event, request: ExportRequest): Promise<{canceled: boolean; filePath?: string}>;
  writeFile(destination: string, content: string): Promise<void>;
}

/** One user-controlled save dialog at a time; pending dialogs are never queued. */
export function createExportHandler<Event>(dependencies: ExportDependencies<Event>) {
  let busy = false;
  return async (event: Event, input: unknown): Promise<SaveExportResult> => {
    if (!dependencies.isTrusted(event)) return {status: 'error', error: 'UNTRUSTED_SENDER'};
    const request = validatedExport(input);
    if (!request) return {status: 'error', error: 'INVALID_EXPORT_REQUEST'};
    if (busy) return {status: 'error', error: 'EXPORT_BUSY'};
    busy = true;
    try {
      const selected = await dependencies.chooseFile(event, request);
      if (selected.canceled) return {status: 'cancelled'};
      if (!dependencies.isTrusted(event)) return {status: 'error', error: 'UNTRUSTED_SENDER'};
      // Do not append an extension after the dialog: that could overwrite a
      // different existing file without the native overwrite confirmation.
      if (!selected.filePath || !path.isAbsolute(selected.filePath)
        || !selected.filePath.toLowerCase().endsWith(exportExtension(request.format))) {
        return {status: 'error', error: 'INVALID_EXPORT_DESTINATION'};
      }
      await dependencies.writeFile(selected.filePath, request.content);
      return {status: 'saved'};
    } catch { return {status: 'error', error: 'EXPORT_FAILED'}; }
    finally { busy = false; }
  };
}

/** Same-directory replace preserves the existing export if writing fails. */
export async function writeExportFile(destination: string, content: string): Promise<void> {
  const temporary = path.join(path.dirname(destination), '.yike-export-' + randomUUID() + '.tmp');
  let created = false;
  try {
    const file = await open(temporary, 'wx', 0o600);
    created = true;
    try { await file.writeFile(content, 'utf8'); await file.sync(); }
    finally { await file.close(); }
    await rename(temporary, destination);
    created = false;
  } finally {
    if (created) await rm(temporary, {force: true});
  }
}
