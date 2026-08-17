# ContributionVerifier v2

ContributionVerifier v2 is a GenLayer intelligent contract for steward-driven,
multi-evidence contribution adjudication on GenLayer Studionet.

## v2 architecture

`submit_contribution` accepts a contribution claim and one to five unique
public HTTP(S) evidence URLs. `verify_contribution` evaluates every URL
independently, aggregates the normalized findings, and stores the result only
after validator consensus.

For each URL, v2 independently records:

```json
{
  "url": "https://example.com/evidence",
  "accessible": true,
  "relevant": true,
  "supports_claim": true,
  "evidence_type": "repository",
  "finding": "The evidence supports the submitted contribution."
}
```

Aggregation happens only after all individual evidence items have been
normalized. Inaccessible evidence is not counted as verified evidence.

The canonical score is a material bucket, not a raw numeric score. The
consensus-bound material fields are matched exactly across validators:

- `valid`
- `category`
- `score_bucket`
- `verified_evidence_count`
- `total_evidence_count`

Validator explanation/reason text may differ because it is non-material prose.
The material decision fields must match exactly. Unlike v1, v2 stores no
canonical raw numeric score and uses no ±10 score tolerance.

## Deployed v2 contract

Network: **GenLayer Studionet**

Contract: [`0xa6301e4b1DD6C14130Ab08449C7F58556B151da6`](https://genlayer-explorer.vercel.app/address/0xa6301e4b1DD6C14130Ab08449C7F58556B151da6)

Deployment transaction: [`0xbcd29c4456730bdfa256c991cc2cd9caaf9ec99bbcadf239ee08523c45ed1b70`](https://genlayer-explorer.vercel.app/tx/0xbcd29c4456730bdfa256c991cc2cd9caaf9ec99bbcadf239ee08523c45ed1b70)

Deployment consensus: **ACCEPTED / MAJORITY_AGREE**

## Verified v2 Studionet adjudication

Contribution ID: `studionet-v2-technical-001`

Submission transaction: [`0x7b6b77839ef248437e06c7a70dd0930178954ac186a7294d14ed3479c0c551eb`](https://genlayer-explorer.vercel.app/tx/0x7b6b77839ef248437e06c7a70dd0930178954ac186a7294d14ed3479c0c551eb)

Submission result: **FINALIZED / MAJORITY_AGREE**  
Execution: **SUCCESS**

Verification transaction: [`0x37b9444e35b2d90019ef912b93d154f85428f0e98702a94e9c2186aa6df5f256`](https://genlayer-explorer.vercel.app/tx/0x37b9444e35b2d90019ef912b93d154f85428f0e98702a94e9c2186aa6df5f256)

Verification result: **FINALIZED / MAJORITY_AGREE**

Final stored verification:

```json
{
  "contribution_id": "studionet-v2-technical-001",
  "valid": true,
  "score_bucket": "STRONG",
  "category": "technical",
  "verified_evidence_count": 3,
  "total_evidence_count": 3,
  "reason": "All three accessible, relevant evidence items from the same repository strongly support the claim. They collectively demonstrate a complete implementation of a GenLayer smart contract for multi-evidence normalization, aggregation, and adjudication, including core logic and tests."
}
```

All three normalized evidence items were independently classified as:

```json
{
  "accessible": true,
  "relevant": true,
  "supports_claim": true
}
```

Evidence URLs:

1. <https://github.com/temitop48/contribution-verifier>
2. <https://raw.githubusercontent.com/temitop48/contribution-verifier/main/contracts/contribution_verifier.py>
3. <https://raw.githubusercontent.com/temitop48/contribution-verifier/main/test/test_contribution_verifier.py>

## Contract API

```python
submit_contribution(
    contribution_id,
    title,
    description,
    evidence_urls,       # list[str], 1–5 unique http(s) URLs
    contribution_type,   # technical, documentation, research, education,
                         # community, tooling, or integration
)

verify_contribution(contribution_id)
```

Contributions use the lifecycle `SUBMITTED` → `VERIFIED` or `REJECTED`.
Verification stores the canonical assessment and the separately normalized
evidence findings.

## Testing

```bash
python -m py_compile contracts/contribution_verifier.py
genvm-lint contracts/contribution_verifier.py
pytest --collect-only -q test/test_contribution_verifier.py
gltest -q test/test_contribution_verifier.py
```

## Historical / Previous Version

ContributionVerifier v1 used one evidence URL, a raw numeric score, and a
validator tolerance of `abs(leader_score - validator_score) <= 10`. The former
v1 deployment at `0xd8730Bfaf1818587260bd83885d01C0ad228787C` is historical only
and is not the current v2 contract.

## License

MIT. See [LICENSE](LICENSE).
