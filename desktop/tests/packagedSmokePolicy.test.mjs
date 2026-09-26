// @vitest-environment jsdom
import {afterEach, describe, expect, it} from 'vitest';
import {inspectWorkbench, isRendererConsoleError, workbenchFailure} from '../scripts/packaged-smoke-policy.mjs';

afterEach(() => { document.body.innerHTML = ''; });
const workbench = '<main id="main-content"><header class="page-heading"><h1>商机工作台</h1><button>创建获客任务</button></header><section class="sample-section"><h2>公开研究样例</h2><button class="sample-row">查看样例</button></section></main>';
const cardWorkbench = workbench.replace('class="sample-row"', 'class="sample-card"');

describe('actual workbench render evidence', () => {
  it('accepts the real workbench structure without treating it as business execution evidence', () => {
    document.body.innerHTML = workbench;
    expect(workbenchFailure(inspectWorkbench(document))).toBeNull();
    document.body.innerHTML = cardWorkbench;
    expect(workbenchFailure(inspectWorkbench(document))).toBeNull();
  });
  it('rejects the observed error boundary even though the body includes the workbench name', () => {
    document.body.innerHTML = '<aside>商机工作台</aside><main id="main-content"><section class="page-error"><h3>页面未能打开</h3><button>返回商机工作台</button></section></main>';
    expect(document.body.textContent).toContain('商机工作台');
    expect(workbenchFailure(inspectWorkbench(document))).toBe('PACKAGED_PAGE_ERROR');
  });
  it('rejects shell text, loading, missing actions and an error boundary alongside stale content', () => {
    for (const html of ['<nav>商机工作台</nav>', '<main id="main-content">正在加载商机工作台</main>', workbench.replace('<button>创建获客任务</button>', ''), workbench.replace('class="sample-row"', 'class="sample-row" disabled')]) {
      document.body.innerHTML = html;
      expect(workbenchFailure(inspectWorkbench(document))).toBe('PACKAGED_WORKBENCH_NOT_RENDERED');
    }
    document.body.innerHTML = workbench + '<section class="page-error">失败</section>';
    expect(workbenchFailure(inspectWorkbench(document))).toBe('PACKAGED_PAGE_ERROR');
  });
  it('keeps the DOM probe self-contained when serialized for Electron', () => {
    document.body.innerHTML = workbench;
    const serialized = Function('return (' + inspectWorkbench.toString() + ')')();
    expect(serialized(document)).toEqual(inspectWorkbench(document));
  });
});

describe('Electron console error signatures', () => {
  it.each([
    [{level: 'error', message: 'TEST React hook error'}],
    [{level: 'error', message: 'TEST React hook error'}, 3, 'TEST'],
    [{}, 3, 'TEST legacy error', 1, 'TEST-source'],
    [{}, {level: 'error', message: 'TEST compatibility object'}],
  ])('captures an error without depending on the message wording (%#)', (...args) => {
    expect(isRendererConsoleError(...args)).toBe(true);
  });
  it.each([[{level: 'warning'}], [{}, 2, 'error appears as quoted text'], [{level: 'info'}], [{}, 0], []])('does not mistake known non-error levels for errors (%#)', (...args) => {
    expect(isRendererConsoleError(...args)).toBe(false);
  });
});
