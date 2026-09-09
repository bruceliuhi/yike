import type {YikeDesktopApi} from '../shared/contracts';

declare global {
  interface Window {
    yikeDesktop: YikeDesktopApi;
  }
}

const statusElement = document.querySelector<HTMLElement>('#runtime-status');

void window.yikeDesktop.getRuntimeStatus().then((status) => {
  if (statusElement !== null) {
    statusElement.textContent =
      status.state === 'FAILED' ? 'DESKTOP_RUNTIME_NOT_READY' : status.state;
  }
});
