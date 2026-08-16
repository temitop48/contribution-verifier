# { "Depends": "py-genlayer:1j12s63yfjpva9ik2xgnffgrs6v44y1f52jvj9w7xvdn7qckd379" }

"""A standalone GenLayer contract for evaluating Web3 contributions.

The contract deliberately stores the submitted claim and the AI assessment
separately. The assessment is produced by nondeterministic web + LLM
execution and accepted only when the validator independently agrees with it.
"""

import json
from dataclasses import dataclass

from genlayer import *


SUPPORTED_TYPES = {
    "technical",
    "documentation",
    "research",
    "education",
    "community",
    "tooling",
    "integration",
}


def _normalize_assessment(raw: dict, contribution_type: str) -> str:
    """Validate and canonicalize an AI assessment for consensus comparison."""
    if not isinstance(raw, dict):
        raise gl.vm.UserError("Assessment result must be a JSON object")

    expected = {"valid", "score", "category", "reason"}
    if set(raw.keys()) != expected:
        raise gl.vm.UserError("Assessment result has invalid fields")
    if not isinstance(raw["valid"], bool):
        raise gl.vm.UserError("Assessment valid field must be boolean")
    if isinstance(raw["score"], bool) or not isinstance(raw["score"], int):
        raise gl.vm.UserError("Assessment score must be an integer")
    if not 0 <= raw["score"] <= 100:
        raise gl.vm.UserError("Assessment score must be between 0 and 100")
    if raw["category"] not in SUPPORTED_TYPES:
        raise gl.vm.UserError("Assessment category is invalid")
    if raw["category"] != contribution_type:
        raise gl.vm.UserError("Assessment category does not match submission")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise gl.vm.UserError("Assessment reason must be a non-empty string")

    return json.dumps(raw, sort_keys=True, separators=(",", ":"))


@allow_storage
@dataclass
class Contribution:
    contribution_id: str
    contributor: Address
    title: str
    description: str
    evidence_url: str
    contribution_type: str
    status: str


@allow_storage
@dataclass
class Verification:
    contribution_id: str
    valid: bool
    score: u8
    category: str
    reason: str


class ContributionVerifier(gl.Contract):
    """Submit Web3 contributions and verify their significance by consensus."""

    contributions: TreeMap[str, Contribution]
    verifications: TreeMap[str, Verification]

    def __init__(self):
        pass

    @gl.public.write
    def submit_contribution(
        self,
        contribution_id: str,
        title: str,
        description: str,
        evidence_url: str,
        contribution_type: str,
    ) -> None:
        if not contribution_id:
            raise gl.vm.UserError("Contribution ID cannot be empty")
        if contribution_id in self.contributions:
            raise gl.vm.UserError("Contribution already exists")
        if not title:
            raise gl.vm.UserError("Title cannot be empty")
        if not description:
            raise gl.vm.UserError("Description cannot be empty")
        if not (
            evidence_url.startswith("http://")
            or evidence_url.startswith("https://")
        ):
            raise gl.vm.UserError("Evidence URL must use http or https")
        if contribution_type not in SUPPORTED_TYPES:
            raise gl.vm.UserError(
                "Unsupported contribution category"
            )

        self.contributions[contribution_id] = Contribution(
            contribution_id=contribution_id,
            contributor=gl.message.sender_address,
            title=title,
            description=description,
            evidence_url=evidence_url,
            contribution_type=contribution_type,
            status="SUBMITTED",
        )

    @gl.public.view
    def get_contribution(self, contribution_id: str) -> dict:
        contribution = self.contributions[contribution_id]
        return {
            "contribution_id": contribution.contribution_id,
            "contributor": contribution.contributor.as_hex,
            "title": contribution.title,
            "description": contribution.description,
            "evidence_url": contribution.evidence_url,
            "contribution_type": contribution.contribution_type,
            "status": contribution.status,
        }

    @gl.public.view
    def contribution_exists(self, contribution_id: str) -> bool:
        return contribution_id in self.contributions

    def _evaluate(self, contribution: Contribution) -> str:
        # Snapshot storage values before entering nondeterministic execution;
        # GenVM forbids storage reads from inside leader/validator closures.
        contribution_type = contribution.contribution_type
        title = contribution.title
        description = contribution.description
        evidence_url = contribution.evidence_url

        def evaluate_once() -> str:
            response = gl.nondet.web.request(
                evidence_url,
                method="GET",
            )
            evidence = response.body.decode("utf-8")
            prompt = f"""
Evaluate whether this Web3 contribution is meaningful, based only on the
submitted claim and the fetched public evidence.

Type: {contribution_type}
Title: {title}
Description: {description}
Evidence URL: {evidence_url}
Fetched evidence:
{evidence}

Return JSON only with exactly these fields:
{{
  "valid": true,
  "score": 0,
  "category": "technical",
  "reason": "brief explanation connecting evidence to the claim"
}}

Set valid to true only when the evidence supports a meaningful contribution.
Score is an integer from 0 to 100 representing strength and significance.
Category must exactly match the submitted contribution category. If evidence
cannot be accessed or interpreted, use valid false and score 0. Do not award
points or discuss reputation. Do not include markdown or additional fields.
"""
            raw = gl.nondet.exec_prompt(prompt, response_format="json")
            if isinstance(raw, str):
                raw = json.loads(raw)
            return _normalize_assessment(raw, contribution_type)

        def validate(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                leader = json.loads(leader_result.calldata)
                # Validate the leader independently before comparing it.
                leader = json.loads(
                    _normalize_assessment(leader, contribution_type)
                )
                validator = json.loads(evaluate_once())
                # Explanations may differ, but validators must agree on the
                # decision, category, and a score band within ten points.
                return (
                    leader.get("valid") == validator.get("valid")
                    and leader.get("category") == validator.get("category")
                    and abs(leader.get("score") - validator.get("score")) <= 10
                )
            except Exception:
                return False

        return gl.vm.run_nondet(evaluate_once, validate)

    @gl.public.write
    def verify_contribution(self, contribution_id: str) -> None:
        if contribution_id not in self.contributions:
            raise gl.vm.UserError("Contribution not found")
        if contribution_id in self.verifications:
            raise gl.vm.UserError("Contribution already verified")

        contribution = self.contributions[contribution_id]
        result = json.loads(self._evaluate(contribution))
        self.verifications[contribution_id] = Verification(
            contribution_id=contribution_id,
            valid=result["valid"],
            score=result["score"],
            category=result["category"],
            reason=result["reason"],
        )
        contribution.status = "VERIFIED" if result["valid"] else "REJECTED"

    @gl.public.view
    def get_verification(self, contribution_id: str) -> dict:
        verification = self.verifications[contribution_id]
        return {
            "contribution_id": verification.contribution_id,
            "valid": verification.valid,
            "score": verification.score,
            "category": verification.category,
            "reason": verification.reason,
        }

    @gl.public.view
    def verification_exists(self, contribution_id: str) -> bool:
        return contribution_id in self.verifications
