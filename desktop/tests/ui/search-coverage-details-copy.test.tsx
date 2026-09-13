// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {SearchCoverageDetails} from '../../src/renderer/pages/tasks/SearchCoverageDetails';
import {coverageFixture} from './r4-search-coverage-fixtures';

const openExternal=vi.fn().mockResolvedValue(undefined);
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>({service:{openExternal}})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('uses the source URL as visible evidence identity and folds internal version identifiers',async()=>{
  const unit=coverageFixture().units[0];
  render(<SearchCoverageDetails unit={unit}/>);
  fireEvent.click(screen.getByRole('tab',{name:'来源依据'}));
  expect(screen.getByText(unit.evidence[0].url).closest('details')).toBeNull();
  expect(screen.getByText(unit.evidence[0].excerpt).closest('details')).toBeNull();
  const technical=screen.getByText(/证据版本 TEST-source-v1/).closest('details');
  expect(technical).not.toBeNull();expect(technical!.open).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'打开原始来源'}));
  await waitFor(()=>expect(openExternal).toHaveBeenCalledWith(unit.evidence[0].url));
});
