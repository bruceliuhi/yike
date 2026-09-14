import {parseRawCandidateEvidence} from '../shared/rawCandidateEvidence';

export interface XhsSourceTarget {
  noteId: string;
  sourceKind: 'POST' | 'COMMENT';
  originalAuthorId: string | null;
  query: string | null;
  deviceId: string;
  connection: {platform: 'XIAOHONGSHU'; access_mode: 'PLATFORM_ACCOUNT';
    connection_id: string; connection_version: number};
}
const noteIdPattern=/^[a-f0-9]{24}$/;

/** Main derives a navigation target from fresh evidence, never from a renderer URL. */
export function resolveXhsSourceTarget(raw: unknown, expected: unknown): XhsSourceTarget {
  try {
    const {candidate,observations}=parseRawCandidateEvidence(raw,expected);
    const noteId=candidate.external_source_id;
    if(candidate.platform!=='XIAOHONGSHU' || candidate.kind==='PAGE' || noteId===null || !noteIdPattern.test(noteId))throw new Error();
    const observation=observations.items.find(item=>item.observation_id===candidate.current_observation_id);
    if(!observation || 'kind' in observation.execution_context ||
      observation.execution_context.access_mode!=='PLATFORM_ACCOUNT')throw new Error();
    const execution=observation.execution_context;
    if(execution.connection_id===null || execution.connection_version===null)throw new Error();
    const commentId=candidate.external_comment_id;
    if(candidate.kind==='COMMENT' && (commentId===null || !noteIdPattern.test(commentId)))throw new Error();
    const canonical=`https://www.xiaohongshu.com/explore/${noteId}`+
      (candidate.kind==='COMMENT'?`?comment_id=${commentId}`:'');
    if(candidate.current_version.public_url!==canonical)throw new Error();
    const author=candidate.current_version.author_public_id;
    // A comment's author and its parent commenter are not the original post author.
    const originalAuthorId=candidate.kind==='POST' && author!==null && noteIdPattern.test(author)?author:null;
    const query=observation.query;
    if(query!==null && (!query.trim() || Array.from(query).length>200 || /[\p{Cc}\p{Cf}]/u.test(query)))throw new Error();
    if(originalAuthorId===null && query===null)throw new Error();
    return {noteId,sourceKind:candidate.kind,originalAuthorId,query,deviceId:execution.device_id,
      connection:{platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',
        connection_id:execution.connection_id,connection_version:execution.connection_version}};
  } catch {
    throw new Error('SOURCE_VIEW_UNAVAILABLE');
  }
}
