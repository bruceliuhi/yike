import {describe,it,expect} from 'vitest';
import {nativeOutreachCommandSchema} from '../src/shared/nativeOutreach';
import {randomUUID} from 'node:crypto';
describe('native outreach renderer intent boundary',()=>{
  it('accepts business draft only and strips the UI fingerprint',()=>{
    const draft={opportunityId:randomUUID(),channel:'dm',content:'你好',savedContent:'你好',version:1,accountId:'account',recipient:'buyer',confirmedFingerprint:'ui'};
    const value=nativeOutreachCommandSchema.parse({action:'PREPARE',requestId:randomUUID(),draft});
    expect(value).not.toHaveProperty('draft.confirmedFingerprint');
    expect(nativeOutreachCommandSchema.safeParse({action:'PREPARE',requestId:randomUUID(),draft:{...draft,profileId:randomUUID()}}).success).toBe(false);
    expect(nativeOutreachCommandSchema.safeParse({action:'CONFIRM',flowId:randomUUID(),humanConfirmed:false}).success).toBe(false);
  });
});
