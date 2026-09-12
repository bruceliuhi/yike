import { describe, expect, it } from "vitest";
import {
  parseOpportunitySourceEvidence,
  type OpportunitySourceEvidence,
} from "../src/renderer/domain/opportunitySourceEvidence";
import { capturedEvidenceFixture } from "./fixtures/opportunitySourceEvidence";

const expected = { opportunityId: "TEST-o", profileVersionId: "TEST-p" };
const fixedError = "INVALID_OPPORTUNITY_SOURCE_EVIDENCE";
it('preserves human demand provenance without inventing raw author or timestamp',()=>{
 const raw:any=capturedEvidenceFixture();
 const proof={schemaVersion:'human-demand-evidence-v1',authorLocator:'TEST第2楼',authorExcerpt:'TEST买方',
   demandExcerpt:'需要报价',publishedDate:'2026-09-10',dateExcerpt:'2026-09-10'};
 Object.assign(raw.snapshot.source,{platform:'PUBLIC_WEB',kind:'PAGE',external_source_id:null,external_comment_id:null,
   container_title:null,parent:null,author_public_id:null,published_at:null,
   body:'TEST买方 2026-09-10 需要报价',author_updates:[proof.demandExcerpt],source_read_scope:'HUMAN_CONFIRMED_EXCERPT'});
 Object.assign(raw.snapshot.verification,{demandEvidence:proof,demandEvidenceId:'66666666-6666-4666-8666-666666666666',checkedBy:'TEST-owner'});
 raw.snapshot.assessment.citations=[{dimension:'intent',field:'source.author_updates.0',quote:'需要报价'}];
 expect(parseOpportunitySourceEvidence(raw,expected)).toEqual(raw);
 const missing=structuredClone(raw);delete missing.snapshot.verification.demandEvidence;rejects(missing);
 const wrong=structuredClone(raw);wrong.snapshot.source.author_updates=['第三方报价'];rejects(wrong);
 const body=structuredClone(raw);body.snapshot.assessment.citations[0].field='source.body';rejects(body);
});
it('preserves author-update citations in a captured opportunity without promoting them to the main body',()=>{
 const raw:any=capturedEvidenceFixture();Object.assign(raw.snapshot.source,{platform:'PUBLIC_WEB',kind:'PAGE',external_comment_id:null,container_title:null,parent:null,author_updates:['请提供作品'],source_read_scope:'AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD'});
 raw.snapshot.assessment.citations=[{dimension:'intent',field:'source.author_updates.0',quote:'提供作品'}];
 expect(parseOpportunitySourceEvidence(raw,expected)).toEqual(raw);
 raw.snapshot.assessment.citations[0].field='source.author_updates.1';rejects(raw);
});

type PathPart = string | number;
type MutableObject = Record<string, unknown>;

function valueAt(root: unknown, path: readonly PathPart[]): unknown {
  let cursor: unknown = root;
  for (const key of path) {
    if (typeof key === "number") cursor = (cursor as unknown[])[key];
    else cursor = (cursor as MutableObject)[key];
  }
  return cursor;
}

function objectAt(root: unknown, path: readonly PathPart[]): MutableObject {
  const cursor = valueAt(root, path);
  if (cursor === null || typeof cursor !== "object" || Array.isArray(cursor))
    throw new Error(`bad TEST fixture path: ${path.join(".")}`);
  return cursor as MutableObject;
}

function changed(
  path: readonly PathPart[],
  change: (target: MutableObject) => void,
): MutableObject {
  const raw = structuredClone(capturedEvidenceFixture());
  change(objectAt(raw, path));
  return raw;
}

function rejects(raw: unknown, options = expected) {
  expect(() => parseOpportunitySourceEvidence(raw, options)).toThrowError(
    new Error(fixedError),
  );
}

describe("parseOpportunitySourceEvidence", () => {
  it("accepts only the exact legacy unavailable shape", () => {
    const unavailable = { status: "UNAVAILABLE", reason: "NOT_CAPTURED" };
    expect(parseOpportunitySourceEvidence(unavailable, expected)).toEqual(
      unavailable,
    );
    for (const invalid of [
      undefined,
      null,
      {},
      { status: "UNAVAILABLE" },
      { status: "UNAVAILABLE", reason: null },
      { status: "UNAVAILABLE", reason: "UNKNOWN" },
      { status: "UNKNOWN", reason: "NOT_CAPTURED" },
      { ...unavailable, extra: "private" },
    ])
      rejects(invalid);
  });

  it("accepts a complete bound CAPTURED snapshot and preserves literal values", () => {
    const raw = capturedEvidenceFixture();
    const parsed = parseOpportunitySourceEvidence(raw, expected);
    expect(parsed).toEqual(raw);
    expect(parsed).not.toBe(raw);
    if (parsed.status !== "CAPTURED") throw new Error("expected TEST snapshot");
    const source = parsed.snapshot.source;
    expect(source.body).toBe(
      "TEST 评论正文：我们需要批量制作\n  保留 空白",
    );
    expect(source.parent?.body).toBe("TEST 父评论正文：请说明交付时间");
  });

  it.each([
    ["outer", [], "status"],
    ["snapshot", ["snapshot"], "schema_version"],
    ["source", ["snapshot", "source"], "platform"],
    ["parent", ["snapshot", "source", "parent"], "external_comment_id"],
    ["observation", ["snapshot", "observation"], "id"],
    ["assessment", ["snapshot", "assessment"], "id"],
    ["citation", ["snapshot", "assessment", "citations", 0], "dimension"],
    ["verification", ["snapshot", "verification"], "method"],
  ] as const)("rejects missing, null, and extra fields at the %s level", (_name, path, required) => {
    rejects(changed(path, (target) => {
      delete target[required];
    }));
    rejects(changed(path, (target) => {
      target[required] = null;
    }));
    rejects(changed(path, (target) => {
      target.private_profile_description = "TEST private text must not pass";
    }));
  });

  it("rejects missing or null nested object containers", () => {
    for (const [path, key] of [
      [[], "snapshot"],
      [["snapshot"], "source"],
      [["snapshot"], "observation"],
      [["snapshot"], "assessment"],
      [["snapshot"], "verification"],
    ] as const) {
      rejects(changed(path, (target) => {
        delete target[key];
      }));
      rejects(changed(path, (target) => {
        target[key] = null;
      }));
    }
  });

  it("rejects private response, profile, and observation-history fields", () => {
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      assessment.model_response = { raw: "TEST private response" };
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      assessment.profile_description = "TEST private profile";
    }));
    rejects(changed(["snapshot", "observation"], (observation) => {
      observation.history = [{ body: "TEST older observation" }];
    }));
  });

  it("requires exact opportunity and profile-version bindings", () => {
    rejects(capturedEvidenceFixture(), {
      opportunityId: "TEST-other-o",
      profileVersionId: "TEST-p",
    });
    rejects(capturedEvidenceFixture(), {
      opportunityId: "TEST-o",
      profileVersionId: "TEST-other-p",
    });
    rejects(changed(["snapshot"], (snapshot) => {
      snapshot.opportunity_id = "TEST-other-o";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      assessment.profile_version_id = "TEST-other-p";
    }));
  });

  it("accepts exactly the five platforms and three source kinds", () => {
    for (const platform of [
      "XIAOHONGSHU",
      "DOUYIN",
      "BILIBILI",
      "ZHIHU",
      "PUBLIC_WEB",
    ]) {
      const raw = changed(["snapshot", "source"], (source) => {
        source.platform = platform;
      });
      expect(parseOpportunitySourceEvidence(raw, expected).status).toBe(
        "CAPTURED",
      );
    }
    rejects(changed(["snapshot", "source"], (source) => {
      source.platform = "TEST_UNKNOWN";
    }));

    for (const kind of ["POST", "PAGE"]) {
      const raw = changed(["snapshot", "source"], (source) => {
        source.kind = kind;
        source.external_comment_id = null;
        source.title = "TEST page title";
        source.container_title = null;
        source.parent = null;
      });
      objectAt(raw, ["snapshot", "assessment"]).citations = [
        {
          dimension: "businessMatch",
          field: "source.title",
          quote: "page title",
        },
        {
          dimension: "intent",
          field: "source.body",
          quote: "需要批量制作",
        },
      ];
      expect(parseOpportunitySourceEvidence(raw, expected).status).toBe(
        "CAPTURED",
      );
    }
    rejects(changed(["snapshot", "source"], (source) => {
      source.kind = "VIDEO";
    }));
  });

  it("enforces COMMENT title, original-post title, id, and parent roles", () => {
    rejects(changed(["snapshot", "source"], (source) => {
      source.title = "TEST wrongly attributed original title";
    }));
    rejects(changed(["snapshot", "source"], (source) => {
      source.external_comment_id = null;
    }));
    for (const kind of ["POST", "PAGE"]) {
      rejects(changed(["snapshot", "source"], (source) => {
        source.kind = kind;
        source.external_comment_id = null;
        source.title = "TEST title";
        source.container_title = "TEST comment-only container";
        source.parent = null;
      }));
      rejects(changed(["snapshot", "source"], (source) => {
        source.kind = kind;
        source.external_comment_id = null;
        source.title = "TEST title";
        source.container_title = null;
      }));
    }
  });

  it("preserves unknown nullable source and parent values as null", () => {
    const raw = changed(["snapshot", "source"], (source) => {
      source.external_source_id = null;
      source.container_title = null;
      source.author_public_id = null;
      source.published_at = null;
      source.parent = {
        external_comment_id: "TEST-parent-comment-unknown",
        body: null,
        author_public_id: null,
        published_at: null,
        public_url: null,
      };
    });
    const assessment = objectAt(raw, ["snapshot", "assessment"]);
    assessment.citations = (assessment.citations as MutableObject[]).filter(
      (citation) => citation.field !== "source.parent.body" && citation.field !== "source.container_title",
    );
    expect(parseOpportunitySourceEvidence(raw, expected)).toEqual(raw);
  });

  it("validates exact citation dimensions, fields, subjects, and whitespace", () => {
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[0].dimension = "confidence";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[0].field = "source.author_public_id";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[0].field = "source.body";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[3].quote = "保留  空白";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[0].quote = "TEST fabricated";
    }));
    rejects(changed(["snapshot", "assessment"], (assessment) => {
      (assessment.citations as MutableObject[])[0].field = "source.title";
    }));
  });

  it("accepts legitimate long Unicode source text without an arbitrary DTO cap", () => {
    const body = `TEST 🧪需求\n${"星河　原文🌏".repeat(12_000)}\nEND`;
    const raw = changed(["snapshot", "source"], (source) => {
      source.body = body;
    });
    const assessment = objectAt(raw, ["snapshot", "assessment"]);
    assessment.citations = [
      { dimension: "intent", field: "source.body", quote: "星河　原文🌏" },
    ];
    const parsed = parseOpportunitySourceEvidence(raw, expected);
    if (parsed.status !== "CAPTURED") throw new Error("expected TEST snapshot");
    expect(parsed.snapshot.source.body).toBe(body);
  });

  it("rejects malformed Unicode that the server cannot encode as UTF-8", () => {
    rejects(changed(["snapshot", "source"], (source) => {
      source.body = `${String(source.body)}\ud800`;
    }));
  });

  it("reuses the service aggregate 2 MiB response bound", () => {
    const raw = changed(["snapshot", "source"], (source) => {
      source.body = `TEST ${"界".repeat(700_000)}`;
    });
    objectAt(raw, ["snapshot", "assessment"]).citations = [
      { dimension: "intent", field: "source.body", quote: "TEST" },
    ];
    rejects(raw);
  });

  it("accepts Python six-digit timestamps and rejects impossible calendars or missing zones", () => {
    for (const timestamp of [
      "2024-02-29T23:59:59.123456+08:00",
      "2026-09-10T01:02:03.000001Z",
      "2026-09-10T01:02:03+00:00",
      "2026-09-10T01:02:03.123456-05:30",
    ]) {
      const raw = changed(["snapshot"], (snapshot) => {
        snapshot.captured_at = timestamp;
      });
      expect(parseOpportunitySourceEvidence(raw, expected).status).toBe(
        "CAPTURED",
      );
    }
    for (const timestamp of [
      "2023-02-29T01:02:03.123456+00:00",
      "2026-04-31T01:02:03.123456+00:00",
      "2026-09-10T24:00:00.123456+00:00",
      "2026-09-10T01:60:00.123456+00:00",
      "2026-09-10T01:02:60.123456+00:00",
      "2026-09-10T01:02:03.123456",
      "2026-09-10",
    ])
      rejects(changed(["snapshot"], (snapshot) => {
        snapshot.captured_at = timestamp;
      }));
  });

  it("requires lowercase SHA-256 formats and safe integer counts", () => {
    for (const [path, key] of [
      [[], "snapshot_sha256"],
      [["snapshot", "source"], "content_sha256"],
      [["snapshot", "assessment"], "rule_sha256"],
    ] as const) {
      rejects(changed(path, (target) => {
        target[key] = "A".repeat(64);
      }));
      rejects(changed(path, (target) => {
        target[key] = "a".repeat(63);
      }));
    }
    for (const value of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1, true])
      rejects(changed(["snapshot", "assessment"], (assessment) => {
        assessment.profile_version = value;
      }));
    for (const value of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1, true])
      rejects(changed(["snapshot", "assessment"], (assessment) => {
        assessment.omitted_profile_citations = value;
      }));
  });

  it("accepts only safe HTTP(S) public links and preserves their original spelling", () => {
    const url = "HTTPS://Example.TEST/公开/原文?q=TEST#定位";
    const raw = changed(["snapshot", "source"], (source) => {
      source.public_url = url;
    });
    const parsed = parseOpportunitySourceEvidence(raw, expected);
    if (parsed.status !== "CAPTURED") throw new Error("expected TEST snapshot");
    expect(parsed.snapshot.source.public_url).toBe(url);

    for (const dangerous of [
      "javascript:alert(1)",
      "data:text/html,TEST",
      "file:///TEST",
      "https://TEST-user:TEST-password@example.test/private",
      "https://example.test/line\nbreak",
      "https://example.test/\u0000control",
      "//example.test/no-scheme",
    ])
      rejects(changed(["snapshot", "source"], (source) => {
        source.public_url = dangerous;
      }));
  });

  it("does not require current source status for a historical CAPTURED snapshot", () => {
    for (const currentStatus of ["BLOCKED", "EXPIRED"]) {
      const raw = capturedEvidenceFixture();
      expect(
        parseOpportunitySourceEvidence(raw, {
          ...expected,
          currentStatus,
        } as typeof expected),
      ).toEqual(raw);
    }
  });

  it("never leaks invalid input or an underlying parser cause in its error", () => {
    const secret = "TEST-PRIVATE-SHOULD-NOT-LEAK";
    const raw = changed(["snapshot", "source"], (source) => {
      source.body = secret;
      source.private = secret;
    });
    try {
      parseOpportunitySourceEvidence(raw, expected);
      throw new Error("expected parser to reject TEST payload");
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toBe(fixedError);
      expect(String(error)).not.toContain(secret);
      expect((error as Error).cause).toBeUndefined();
    }
  });
});
