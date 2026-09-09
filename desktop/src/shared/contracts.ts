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
}

export const DESKTOP_RUNTIME_NOT_READY: DesktopStatus = {
  state: 'FAILED',
  errorCode: 'LOCAL_SERVICE_UNAVAILABLE'
};

export const GET_RUNTIME_STATUS_CHANNEL = 'desktop:get-runtime-status';
