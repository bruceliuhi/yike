export class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() {return this.values.size;}
  clear() {this.values.clear();}
  getItem(key: string) {return this.values.get(String(key)) ?? null;}
  key(index: number) {return Array.from(this.values.keys())[index] ?? null;}
  removeItem(key: string) {this.values.delete(String(key));}
  setItem(key: string, value: string) {this.values.set(String(key), String(value));}
}
/** Install before mounting the real App. No persistent storage or business network. */
export function isolateBrowser(record: (operation: string, detail?: string) => void) {
  if (window.location.hostname !== '127.0.0.1' || window.location.port !== '18794') throw new Error('Visual harness requires 127.0.0.1:18794');
  const session = new MemoryStorage();
  const local = new MemoryStorage();
  Object.defineProperty(window, 'sessionStorage', {value: session, configurable: true});
  Object.defineProperty(window, 'localStorage', {value: local, configurable: true});
  Object.defineProperty(window, 'yikeDesktop', {value: undefined, configurable: false});
  window.fetch = async () => {record('BLOCKED_FETCH'); throw new Error('TEST business fetch blocked');};
  window.open = () => {record('BLOCKED_WINDOW_OPEN'); return null;};
  XMLHttpRequest.prototype.open = function () {record('BLOCKED_XHR'); throw new Error('TEST XHR blocked');};
  Object.defineProperty(navigator, 'sendBeacon', {value: () => {record('BLOCKED_BEACON'); return false;}, configurable: true});
  Object.defineProperty(navigator, 'clipboard', {value: {writeText: async (value: string) => record('BLOCKED_CLIPBOARD', `TEST ${value.length} characters; no clipboard write`)}, configurable: true});
  // CSV export uses a detached anchor; a document listener alone cannot catch it.
  const clickAnchor = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const url = new URL(this.href, location.href);
    if (this.hasAttribute('download') || url.origin !== location.origin) {record('BLOCKED_LINK_OR_DOWNLOAD'); return;}
    clickAnchor.call(this);
  };
  document.addEventListener('click', event => {
    const anchor = event.target instanceof Element ? event.target.closest('a') : null;
    if (!anchor || !anchor.hasAttribute('href')) return;
    const url = new URL(anchor.href, location.href);
    if (anchor.hasAttribute('download') || url.origin !== location.origin) {
      event.preventDefault(); event.stopImmediatePropagation(); record('BLOCKED_LINK_OR_DOWNLOAD');
    }
  }, true);
  document.addEventListener('submit', event => {
    const form = event.target;
    if (form instanceof HTMLFormElement && form.hasAttribute('action')) {event.preventDefault(); record('BLOCKED_FORM');}
  }, true);
  return {session, local};
}
