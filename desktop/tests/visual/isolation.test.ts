// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://127.0.0.1:18794/"}
import {beforeAll, describe, expect, it} from 'vitest';
import {isolateBrowser, MemoryStorage} from './isolation';
const events: string[] = [];
beforeAll(() => {isolateBrowser(operation => events.push(operation));});
describe('browser isolation guards', () => {
  it('uses memory storage and removes the native bridge', () => {
    expect(window.localStorage).toBeInstanceOf(MemoryStorage);
    expect(window.sessionStorage).toBeInstanceOf(MemoryStorage);
    expect((window as unknown as {yikeDesktop?: unknown}).yikeDesktop).toBeUndefined();
  });
  it('rejects browser network primitives', async () => {
    await expect(window.fetch('https://external.invalid')).rejects.toThrow('TEST');
    expect(() => new XMLHttpRequest().open('GET', '/api/ui/session')).toThrow('TEST');
    expect(navigator.sendBeacon('https://external.invalid', 'TEST')).toBe(false);
  });
  it('records opening and copying without invoking external capabilities', async () => {
    expect(window.open('https://external.invalid')).toBeNull();
    await navigator.clipboard.writeText('TEST');
    expect(events).toContain('BLOCKED_WINDOW_OPEN');
    expect(events).toContain('BLOCKED_CLIPBOARD');
  });
  it('blocks detached download and external anchors as well as visible links', () => {
    const download = document.createElement('a'); download.href = 'blob:http://127.0.0.1:18794/TEST'; download.download = 'TEST.csv'; download.click();
    const external = document.createElement('a'); external.href = 'https://external.invalid'; external.click();
    const visible = document.createElement('a'); visible.href = 'https://external.invalid'; document.body.append(visible);
    const event = new MouseEvent('click', {bubbles: true, cancelable: true}); visible.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(events.filter(value => value === 'BLOCKED_LINK_OR_DOWNLOAD')).toHaveLength(3);
  });
});
