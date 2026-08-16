# ContributionVerifier

`ContributionVerifier` is a standalone GenLayer Intelligent Contract for
reviewing whether a submitted Web3 contribution is meaningful. It combines
public evidence retrieval, nondeterministic AI evaluation, and
leader-validator consensus before storing an assessment on-chain.

## 1. What it does

A contributor submits a title, description, public evidence URL, and
contribution category. The contract stores the submission, then evaluates the
claim against the fetched evidence. The resulting assessment contains:

```json
{
  "valid": true,
  "score": 86,
  "category": "technical",
  "reason": "The public evidence supports a meaningful technical contribution."
}
```

## 2. Problem

Web3 contribution claims are difficult to review consistently. A title and
link do not necessarily show that work is real, relevant, or meaningful.
ContributionVerifier provides a small, auditable verification primitive that
keeps the claim and its consensus-backed assessment separate.

## 3. Contract architecture

The contract has two storage maps:

- `contributions`: submitted claims and their status.
- `verifications`: the final consensus-backed assessment.

The main methods are `submit_contribution`, `verify_contribution`,
`get_contribution`, `get_verification`, `contribution_exists`, and
`verification_exists`.

## 4. Supported contribution categories

`technical`, `documentation`, `research`, `education`, `community`,
`tooling`, and `integration`.

## 5. Nondeterministic evidence fetching

During evaluation, the contract uses `gl.nondet.web.request` to fetch the
submitted HTTP(S) evidence URL. The response body, together with the claim,
is passed to `gl.nondet.exec_prompt`, which must return JSON with exactly
`valid`, `score`, `category`, and `reason`.

Inaccessible or uninterpretable evidence should result in `valid: false` and
score `0`. The contract validates the returned structure before it can be
stored.

## 6. How AI evaluation works

The AI evaluates the strength of the evidence relative to the submitted
claim. `valid` indicates whether the evidence supports a meaningful
contribution; `score` is an integer from 0 to 100; `category` must match the
submitted category; and `reason` explains the decision. The contract does not
award tokens or reputation.

## 7. GenLayer leader-validator consensus

`verify_contribution` calls `gl.vm.run_nondet`. The leader performs the web
fetch and AI evaluation. Validators independently repeat that evaluation and
vote on whether the leader result is equivalent. Only the agreed result is
written to storage. This is genuine GenLayer nondeterministic execution, not
a deterministic contract with AI terminology added around it.

## 8. Validator equivalence rules

Before comparison, the validator requires the leader result to be a JSON
object with exactly the expected fields and valid types/ranges. It then
requires:

- `valid` must agree.
- `category` must agree and match the submitted category.
- The absolute score difference must be at most 10.
- Explanations may differ; exact reason-text equality is not required.

Malformed JSON, missing or extra fields, boolean scores, scores outside
0–100, unsupported categories, mismatched categories, and empty reasons are
rejected.

## 9. State stored by the contract

Each contribution stores its ID, contributor address, title, description,
evidence URL, category, and status (`SUBMITTED`, `VERIFIED`, or `REJECTED`).
Each verification stores its contribution ID, validity, score, category, and
reason.

## 10. Local lint and test instructions

Create a virtual environment and install the pinned requirements:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run the quick static checks:

```bash
python -m py_compile contracts/contribution_verifier.py
genvm-lint contracts/contribution_verifier.py
```

Run the focused mocked GenVM tests:

```bash
gltest -q test/test_contribution_verifier.py
```

These tests do not require a live AI provider. For a real deployment, use
GenLayer Studio or the configured Studionet network and call
`submit_contribution` followed by `verify_contribution`.

## 11. Studionet deployment evidence

The contract was deployed and exercised on GenLayer Studionet without
modifying the contract afterward.

- Network: **GenLayer Studionet**
- Contract: `0xd8730Bfaf1818587260bd83885d01C0ad228787C`
- Positive contribution ID: `studionet-demo-technical-002`
- Evidence URL: `https://raw.githubusercontent.com/ethereum/ethereum-org-website/dev/README.md`
- Submission transaction: `0x56859ad84d56262f5b7ae8f8eb2fcfe8f1ce45142b004a507dd8ff07b56fa84f`
- Verification transaction: `0xec9864a59e5d2fe682b25f776280db9eda47ba6fd7db27792e4c3d7719c85715`
- Consensus: `ACCEPTED / MAJORITY_AGREE`
- Assessment: `valid: true`, `score: 86`, `category: technical`

The contract also rejected an earlier submission whose evidence URL returned
HTTP 404. That result was stored as invalid with score 0, demonstrating that
the verifier does not blindly approve inaccessible evidence.

## License

MIT. See [LICENSE](LICENSE).
