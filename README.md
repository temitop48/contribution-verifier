# ContributionVerifier v2

ContributionVerifier v2 is a standalone GenLayer intelligent contract for
multi-evidence contribution adjudication. It accepts a claim and one to five
public URLs, normalizes each item independently, aggregates the findings, and
stores only the result accepted by leader-validator consensus.

## 1. Problem

A contribution claim is rarely established by one link. A reviewer may need a
repository, pull request, deployment, documentation page, or research record
to determine whether work is accessible, relevant, substantive, and meaningful.

## 2. Why v1 was insufficient

v1 fetched one URL and passed it to one generic judgment prompt. It stored a
leader-selected raw score and accepted a validator score within ten points:
`abs(leader_score - validator_score) <= 10`. That made the stored numeric score
not fully consensus-bound and did not provide evidence-level normalization or
aggregation.

## 3. v2 architecture

`submit_contribution` stores a claim with one to five URLs and status
`SUBMITTED`. `verify_contribution` snapshots the claim, then runs the same
nondeterministic pipeline for leader and validator:

1. Fetch every URL independently.
2. Normalize every accessible item into a small structured finding.
3. Aggregate the findings into a contribution assessment.
4. Compare material outputs under exact consensus.
5. Write state only after consensus succeeds.

## 4. Multi-evidence input

The API is:

```python
submit_contribution(
    contribution_id,
    title,
    description,
    evidence_urls,       # list[str], 1–5 unique http(s) URLs
    contribution_type,   # technical, documentation, research, education,
                         # community, tooling, or integration
)
```

URLs are intentionally provider-neutral: repositories, pull requests, issues,
documentation, deployments/explorers, research, education, and community
pages are all supported.

## 5. Evidence normalization

Each URL is fetched with `gl.nondet.web.request`. An accessible item is sent to
an evidence-specific normalization prompt. The normalized finding has exactly:

```json
{
  "url": "https://example.com/project/pull/7",
  "accessible": true,
  "relevant": true,
  "supports_claim": true,
  "evidence_type": "pull_request",
  "finding": "A reviewed change adds the claimed behavior and tests."
}
```

HTTP failures and fetch exceptions become an explicit inaccessible finding;
they never count as supporting evidence. URL identity, flags, type, and finding
text are validated before aggregation.

## 6. Evidence aggregation

The aggregate prompt receives normalized findings, not a concatenated URL list.
It considers technical substance, claim relevance, evidence quality,
significance/impact, and meaningfulness or originality where applicable. The
contract independently derives `verified_evidence_count` as the number of
findings that are both accessible and materially supportive. If none qualify,
the contract deterministically returns an invalid `INSUFFICIENT` assessment.

## 7. Material score buckets

The canonical score is a consensus-bound bucket, not a leader-selected raw
score with tolerance:

| Bucket | Meaning |
| --- | --- |
| `INSUFFICIENT` | 0–19 |
| `LOW` | 20–39 |
| `MODERATE` | 40–59 |
| `STRONG` | 60–79 |
| `EXCEPTIONAL` | 80–100 |

No raw numeric score is stored. The model may reason about the ranges, but the
bucket is the material score output.

## 8. GenLayer consensus design

The leader and validator each execute the complete URL-fetch, per-item
normalization, and aggregate-evaluation pipeline. The validator does not trust
the leader's findings or assessment and does not merely check formatting.
Before comparison it validates the leader payload, its exact fields, types,
category, bucket, findings, and counts.

All storage values needed by both nondeterministic closures are copied into
local variables before `gl.vm.run_nondet`; mutable contract storage is not read
inside either callback. Final storage writes happen only after the call returns
successfully.

## 9. Exact fields bound by consensus

The exact material assessment fields are:

```json
{
  "valid": true,
  "category": "technical",
  "score_bucket": "STRONG",
  "verified_evidence_count": 2,
  "total_evidence_count": 3,
  "reason": "Two accessible findings materially support the claim."
}
```

Consensus requires exact equality for `valid`, `category`, `score_bucket`, and
both evidence counts. It also requires the total count to equal the submitted
URL count. This removes the v1 ten-point score tolerance entirely.

## 10. Why explanation text may differ

`reason` must be a non-empty string and is stored as supporting explanation.
It is intentionally not compared byte-for-byte because equivalent independent
reviewers may phrase the same adjudication differently. The decision, bucket,
category, and counts—not prose wording—are the canonical consensus outputs.

## 11. State/lifecycle

Contributions move through the simple lifecycle `SUBMITTED` → `VERIFIED` or
`REJECTED`. A verification stores the canonical assessment plus normalized
findings as supporting audit data. There are no tokens, rewards, appeals, or
frontend components.

## 12. Example contribution

```json
{
  "contribution_id": "wallet-connector-001",
  "title": "Improve wallet connector",
  "description": "Adds support for a commonly used Web3 wallet.",
  "evidence_urls": [
    "https://github.com/example/project/pull/7",
    "https://docs.example.org/wallet-connector",
    "https://explorer.example.org/tx/0xabc"
  ],
  "contribution_type": "technical"
}
```

## 13. Example normalized evidence

```json
[
  {
    "url": "https://github.com/example/project/pull/7",
    "accessible": true,
    "relevant": true,
    "supports_claim": true,
    "evidence_type": "pull_request",
    "finding": "The change adds the connector implementation and tests."
  },
  {
    "url": "https://explorer.example.org/tx/0xabc",
    "accessible": false,
    "relevant": false,
    "supports_claim": false,
    "evidence_type": "other",
    "finding": "The public URL was not accessible."
  }
]
```

## 14. Example final adjudication

```json
{
  "valid": true,
  "category": "technical",
  "score_bucket": "STRONG",
  "verified_evidence_count": 2,
  "total_evidence_count": 3,
  "reason": "Two accessible findings establish a substantive, relevant change."
}
```

## 15. Testing

The suite covers URL cardinality and format, unsupported categories,
duplicates, malformed assessment and finding schemas, invalid buckets and
counts, exact bucket/validity/category consensus, allowed reason differences,
inaccessible evidence, mixed evidence, and all-inaccessible evidence. Mocked
GenVM tests use `mock_web` and `mock_llm`; they do not fake deployment or model
consensus output.

```bash
python -m py_compile contracts/contribution_verifier.py
genvm-lint contracts/contribution_verifier.py
pytest --collect-only -q test/test_contribution_verifier.py
gltest -q test/test_contribution_verifier.py
```

## 16. Deployment

Deploy the current source as a fresh Studionet contract, then exercise
`submit_contribution` and `verify_contribution` against that new address.
Deployment evidence must match this v2 source and its multi-evidence API.

## 17. Historical v1 deployment

The previous v1 deployment at
`0xd8730Bfaf1818587260bd83885d01C0ad228787C` is historical only. It is not
evidence of this v2 implementation and must not be reused as v2 deployment
proof.

## 18. v2 deployment placeholder

**Studionet v2 contract:** to be filled after a fresh deployment of this exact
source.

**Deployment and verification transactions:** to be filled after deployment.

## License

MIT. See [LICENSE](LICENSE).
