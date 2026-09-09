/** Electron 43 uses details as its first argument; older releases use numeric level second. */
export function isRendererConsoleError(...args) {
  for (const value of args.slice(0, 2)) {
    if (value && typeof value === 'object' && (value.level === 'error' || value.level === 3)) return true;
  }
  return args[1] === 3 || args[1] === 'error';
}

/** Serialized into the actual renderer. Keep this function self-contained. */
export function inspectWorkbench(document) {
  const main = document.querySelector('main#main-content');
  const text = element => element?.textContent?.trim() || '';
  const headings = main ? [...main.querySelectorAll('.page-heading h1')] : [];
  const create = main ? [...main.querySelectorAll('.page-heading button')].find(button => text(button) === '创建获客任务') : null;
  const sample = main?.querySelector('.sample-section');
  const sampleAction = sample?.querySelector('button.sample-row');
  return {
    main: !!main,
    heading: headings.length === 1 && text(headings[0]) === '商机工作台',
    createAction: !!create && !create.disabled,
    sampleHeading: text(sample?.querySelector('h2')) === '公开研究样例',
    sampleAction: !!sampleAction && !sampleAction.disabled,
    errorPage: !!document.querySelector('.page-error') || !!main && [...main.querySelectorAll('h1,h2,h3')].some(element => text(element) === '页面未能打开'),
  };
}

export function workbenchFailure(snapshot) {
  if (snapshot?.errorPage) return 'PACKAGED_PAGE_ERROR';
  if (!snapshot || !['main', 'heading', 'createAction', 'sampleHeading', 'sampleAction'].every(key => snapshot[key] === true))
    return 'PACKAGED_WORKBENCH_NOT_RENDERED';
  return null;
}
