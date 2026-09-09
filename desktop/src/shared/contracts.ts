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
  requestApi(request: ApiRequest): Promise<ApiResult>;
  openExternal(url: string): Promise<DesktopActionResult>;
  copyText(text: string): Promise<DesktopActionResult>;
}

export const API_OPERATIONS = [
  'session.get', 'session.login', 'session.logout',
  'profiles.list', 'profiles.save', 'profiles.confirm',
  'opportunities.list', 'opportunities.get', 'followups.list', 'followups.add',
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
