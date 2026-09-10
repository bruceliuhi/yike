export type DesktopStatus =
  | {state: 'STARTING'}
  | {
      state: 'READY';
      protocolVersion: 'YIKE_DESKTOP_SIDECAR_V1';
      factSchemaVersion: string;
    }
  | {
      state: 'FAILED';
      errorCode: 'LOCAL_SERVICE_START_FAILED' | 'LOCAL_SERVICE_UNAVAILABLE';
    };

export interface YikeDesktopApi {
  getRuntimeStatus(): Promise<DesktopStatus>;
  getClientInfo(): Promise<ClientInfo>;
  getPortableRuntimeStatus?():Promise<import('./portableRuntime').PortableRuntimeStatus>;
  getDeviceIdentityStatus?(): Promise<import('./deviceIdentity').DeviceIdentityStatus>;
  prepareDeviceIdentity?(options?: import('./deviceIdentity').DeviceIdentityRetry): Promise<import('./deviceIdentity').DeviceIdentityStatus>;
  executionCommand?(command: import('./desktopExecution').DesktopExecutionCommand): Promise<import('./desktopExecution').DesktopExecutionResult>;
  foregroundCollectionCommand?(command: import('./foregroundCollection').ForegroundCollectionCommand): Promise<import('./foregroundCollection').ForegroundCollectionResult>;
  monitorCollectionCommand?(command: import('./monitorCollection').MonitorCollectionCommand): Promise<import('./monitorCollection').MonitorCollectionResult>;
  platformConnectionCommand?(command: import('./platformConnection').PlatformConnectionCommand): Promise<import('./platformConnection').PlatformConnectionResult>;
  nativeOutreachCommand?(command: import('./nativeOutreach').NativeOutreachCommand): Promise<import('./nativeOutreach').NativeOutreachResult>;
  nativeReplyCommand?(command: import('./nativeReply').NativeReplyCommand): Promise<import('./nativeReply').NativeReplyResult>;
  requestApi(request: ApiRequest): Promise<ApiResult>;
  openExternal(url: string): Promise<DesktopActionResult>;
  copyText(text: string): Promise<DesktopActionResult>;
  saveExport(request: ExportRequest): Promise<SaveExportResult>;
}

export interface ExportRequest {
  format: 'csv' | 'backup-json';
  name: string;
  content: string;
}
export const EXPORT_ERROR_CODES = [
  'INVALID_EXPORT_REQUEST', 'UNTRUSTED_SENDER', 'EXPORT_BUSY',
  'INVALID_EXPORT_DESTINATION', 'EXPORT_UNAVAILABLE', 'EXPORT_FAILED'
] as const;
export type ExportErrorCode = typeof EXPORT_ERROR_CODES[number];
export type SaveExportResult =
  | {status: 'saved'}
  | {status: 'cancelled'}
  | {status: 'error'; error: ExportErrorCode};

export const API_OPERATIONS = [
  'session.get', 'session.login', 'session.logout',
  'session.requestCode', 'session.loginPhone',
  'profiles.list', 'profiles.save', 'profiles.confirm',
  'connections.list',
  'taskFeed.list', 'taskFeed.get',
  'opportunities.list', 'opportunities.get', 'followups.list', 'followups.add',
  'replies.evidence',
  'strategies.prepare', 'strategies.confirm', 'strategies.revoke', 'strategies.receipt', 'strategies.get',
  'candidates.list', 'candidates.review', 'candidates.verifySource', 'candidates.request', 'candidates.rawEvidence',
  'materials.list', 'materials.mutate', 'materials.operation', 'materials.impact',
  'capabilities.get'
] as const;

export type ApiOperation = typeof API_OPERATIONS[number];
export interface ApiRequest {
  operation: ApiOperation;
  payload?: unknown;
}
export type ApiResult =
  | {ok: true; status: number; data: unknown}
  | {ok: false; status: number; error: string};
export interface ClientInfo {
  version: string;
  platform: string;
  serviceConfigured: boolean;
}
export type DesktopActionResult = {ok: true} | {ok: false; error: string};

export const DESKTOP_RUNTIME_NOT_READY: DesktopStatus = {
  state: 'FAILED',
  errorCode: 'LOCAL_SERVICE_UNAVAILABLE'
};

export const GET_RUNTIME_STATUS_CHANNEL = 'desktop:get-runtime-status';
export const GET_CLIENT_INFO_CHANNEL = 'desktop:get-client-info';
export const REQUEST_API_CHANNEL = 'desktop:request-api';
export const OPEN_EXTERNAL_CHANNEL = 'desktop:open-external';
export const COPY_TEXT_CHANNEL = 'desktop:copy-text';
export const SAVE_EXPORT_CHANNEL = 'desktop:save-export';
