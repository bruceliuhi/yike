import type { PublicPageMetadata as Metadata } from '../../../shared/publicPageMetadata';

/** Publisher declarations are separate evidence, never a verified buyer identity. */
export function PublicPageMetadata({ metadata }: { metadata: Metadata }) {
  const { publication, author } = metadata;
  const dateOnly = publication?.precision === 'DATE';
  const displayedTime = publication === null ? null : dateOnly ? `${publication.value}（仅日期，时区未知）` :
    `${publication.value.replace('T', ' ').replace(/Z$/, '')}（${publication.precision === 'SECOND' ? 'UTC' : '时区未知'}）`;
  return <section aria-label="网页标注信息">
    <dl className="candidate-evidence-facts detail-list">
      {author !== null && <div><dt>网页标注作者</dt><dd>{author.value}</dd></div>}
      {publication !== null && <div>
        <dt>{dateOnly ? '网页标注发布日期' : '网页标注发布时间'}</dt>
        <dd><time dateTime={publication.value}>{displayedTime}</time></dd>
      </div>}
    </dl>
    <p className="muted">网页声明，不代表已核验的买方身份或需求日期。</p>
    <details className="candidate-evidence-details">
      <summary>网页声明原值</summary>
      <dl className="candidate-evidence-facts detail-list">
        {publication !== null && <div><dt>{publication.declaration}</dt><dd>{publication.raw}</dd></div>}
        {author !== null && <div><dt>{author.declaration}</dt><dd>{author.raw}</dd></div>}
      </dl>
    </details>
  </section>;
}
