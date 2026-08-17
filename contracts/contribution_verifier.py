# { "Depends": "py-genlayer:1j12s63yfjpva9ik2xgnffgrs6v44y1f52jvj9w7xvdn7qckd379" }

"""Multi-evidence contribution adjudication for GenLayer.

The contract deliberately keeps nondeterministic work in small, repeatable
steps: each URL is fetched and normalized independently, then the normalized
findings are aggregated into a contribution assessment.  Only the material
assessment fields accepted by leader-validator consensus are canonical.
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
MAX_EVIDENCE_URLS = 5
SUPPORTED_EVIDENCE_TYPES = {
    "code_repository",
    "pull_request",
    "documentation",
    "deployment",
    "research",
    "education",
    "community",
    "other",
}
SCORE_BUCKETS = {
    "INSUFFICIENT",
    "LOW",
    "MODERATE",
    "STRONG",
    "EXCEPTIONAL",
}


def _assessment_fields() -> set:
    return {
        "valid",
        "category",
        "score_bucket",
        "verified_evidence_count",
        "total_evidence_count",
        "reason",
    }


def _normalize_assessment(raw: dict, contribution_type: str) -> str:
    """Validate the small, material contribution assessment schema."""
    if not isinstance(raw, dict):
        raise gl.vm.UserError("Assessment result must be a JSON object")
    if set(raw.keys()) != _assessment_fields():
        raise gl.vm.UserError("Assessment result has invalid fields")
    if not isinstance(raw["valid"], bool):
        raise gl.vm.UserError("Assessment valid field must be boolean")
    if raw["category"] not in SUPPORTED_TYPES:
        raise gl.vm.UserError("Assessment category is invalid")
    if raw["category"] != contribution_type:
        raise gl.vm.UserError("Assessment category does not match submission")
    if raw["score_bucket"] not in SCORE_BUCKETS:
        raise gl.vm.UserError("Assessment score bucket is invalid")
    for field in ("verified_evidence_count", "total_evidence_count"):
        if isinstance(raw[field], bool) or not isinstance(raw[field], int):
            raise gl.vm.UserError("Assessment evidence counts must be integers")
        if raw[field] < 0 or raw[field] > MAX_EVIDENCE_URLS:
            raise gl.vm.UserError("Assessment evidence count is out of range")
    if raw["verified_evidence_count"] > raw["total_evidence_count"]:
        raise gl.vm.UserError("Verified evidence count exceeds total count")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise gl.vm.UserError("Assessment reason must be a non-empty string")

    return json.dumps(raw, sort_keys=True, separators=(",", ":"))


def _normalize_finding(raw: dict, expected_url: str) -> str:
    """Validate one independently-produced normalized evidence finding."""
    expected = {
        "url",
        "accessible",
        "relevant",
        "supports_claim",
        "evidence_type",
        "finding",
    }
    if not isinstance(raw, dict) or set(raw.keys()) != expected:
        raise gl.vm.UserError("Evidence finding has invalid fields")
    if raw["url"] != expected_url:
        raise gl.vm.UserError("Evidence finding URL does not match submission")
    for field in ("accessible", "relevant", "supports_claim"):
        if not isinstance(raw[field], bool):
            raise gl.vm.UserError("Evidence finding flags must be boolean")
    if raw["evidence_type"] not in SUPPORTED_EVIDENCE_TYPES:
        raise gl.vm.UserError("Evidence type is invalid")
    if not isinstance(raw["finding"], str) or not raw["finding"].strip():
        raise gl.vm.UserError("Evidence finding must be non-empty")
    if not raw["accessible"] and raw["supports_claim"]:
        raise gl.vm.UserError("Inaccessible evidence cannot support a claim")
    return json.dumps(raw, sort_keys=True, separators=(",", ":"))


@allow_storage
@dataclass
class Contribution:
    contribution_id: str
    contributor: Address
    title: str
    description: str
    # JSON is used here as a conservative GenVM storage-compatible list.
    evidence_urls_json: str
    contribution_type: str
    status: str


@allow_storage
@dataclass
class Verification:
    contribution_id: str
    valid: bool
    score_bucket: str
    category: str
    verified_evidence_count: u8
    total_evidence_count: u8
    reason: str
    # Supporting normalized findings; the canonical result is the material
    # assessment fields above, which are checked by exact consensus.
    normalized_evidence_json: str


class ContributionVerifier(gl.Contract):
    """Adjudicate a contribution claim against one to five evidence URLs."""

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
        evidence_urls: list[str],
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
        if not isinstance(evidence_urls, list) or not evidence_urls:
            raise gl.vm.UserError("At least one evidence URL is required")
        if len(evidence_urls) > MAX_EVIDENCE_URLS:
            raise gl.vm.UserError("Too many evidence URLs")
        if len(set(evidence_urls)) != len(evidence_urls):
            raise gl.vm.UserError("Evidence URLs must be unique")
        for evidence_url in evidence_urls:
            if not isinstance(evidence_url, str) or not (
                evidence_url.startswith("http://")
                or evidence_url.startswith("https://")
            ):
                raise gl.vm.UserError("Evidence URL must use http or https")
        if contribution_type not in SUPPORTED_TYPES:
            raise gl.vm.UserError("Unsupported contribution category")

        self.contributions[contribution_id] = Contribution(
            contribution_id=contribution_id,
            contributor=gl.message.sender_address,
            title=title,
            description=description,
            evidence_urls_json=json.dumps(evidence_urls, separators=(",", ":")),
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
            "evidence_urls": json.loads(contribution.evidence_urls_json),
            "contribution_type": contribution.contribution_type,
            "status": contribution.status,
        }

    @gl.public.view
    def contribution_exists(self, contribution_id: str) -> bool:
        return contribution_id in self.contributions

    def _evaluate(self, contribution: Contribution) -> str:
        # Snapshot every storage value needed by both closures before entering
        # nondeterministic execution.  Storage reads inside these callbacks are
        # forbidden by GenVM.
        contribution_type = contribution.contribution_type
        title = contribution.title
        description = contribution.description
        evidence_urls = list(json.loads(contribution.evidence_urls_json))

        def evaluate_once() -> str:
            findings = []
            for url in evidence_urls:
                try:
                    response = gl.nondet.web.request(url, method="GET")
                    if response.status < 200 or response.status >= 400:
                        findings.append({
                            "url": url,
                            "accessible": False,
                            "relevant": False,
                            "supports_claim": False,
                            "evidence_type": "other",
                            "finding": "The public URL was not accessible.",
                        })
                        continue
                    body = response.body.decode("utf-8")[:12000]
                except Exception:
                    findings.append({
                        "url": url,
                        "accessible": False,
                        "relevant": False,
                        "supports_claim": False,
                        "evidence_type": "other",
                        "finding": "The public URL could not be fetched.",
                    })
                    continue

                prompt = f"""
Normalize exactly one public evidence item for a contribution claim.
This is an evidence-normalization step, not the final score.

Claim type: {contribution_type}
Claim title: {title}
Claim description: {description}
Evidence URL: {url}
Fetched public content:
{body}

Return JSON only with exactly these fields:
{{
  "url": "{url}",
  "accessible": true,
  "relevant": true,
  "supports_claim": true,
  "evidence_type": "code_repository",
  "finding": "short factual finding"
}}

Classify the evidence as code_repository, pull_request, documentation,
deployment, research, education, community, or other.  Set relevant and
supports_claim false when the content does not materially support the claim.
Do not infer facts absent from the fetched content.  Keep finding short.
"""
                raw = gl.nondet.exec_prompt(prompt, response_format="json")
                if isinstance(raw, str):
                    raw = json.loads(raw)
                findings.append(json.loads(_normalize_finding(raw, url)))

            verified_count = sum(
                1
                for finding in findings
                if finding["accessible"] and finding["supports_claim"]
            )
            total_count = len(findings)

            if verified_count == 0:
                assessment = {
                    "valid": False,
                    "category": contribution_type,
                    "score_bucket": "INSUFFICIENT",
                    "verified_evidence_count": 0,
                    "total_evidence_count": total_count,
                    "reason": "No accessible evidence materially supports the claim.",
                }
                return json.dumps(
                    {"assessment": json.loads(_normalize_assessment(assessment, contribution_type)),
                     "findings": findings},
                    sort_keys=True,
                    separators=(",", ":"),
                )

            aggregate_prompt = f"""
Aggregate normalized evidence findings into one contribution adjudication.
The findings below were independently normalized URL by URL; do not fetch new
URLs and do not count inaccessible or non-supporting findings.

Claim type: {contribution_type}
Claim title: {title}
Claim description: {description}
Normalized findings:
{json.dumps(findings, sort_keys=True)}

Evaluate technical substance, relevance, evidence quality, significance or
impact, and meaningfulness/originality where applicable. Return JSON only with
exactly these fields:
{{
  "valid": true,
  "category": "{contribution_type}",
  "score_bucket": "STRONG",
  "verified_evidence_count": {verified_count},
  "total_evidence_count": {total_count},
  "reason": "brief aggregate explanation"
}}

Use exactly one bucket: INSUFFICIENT (0-19), LOW (20-39), MODERATE (40-59),
STRONG (60-79), or EXCEPTIONAL (80-100). The bucket is canonical; do not
return a raw numeric score. Set valid false if the evidence does not establish
a meaningful contribution. Counts must match the normalized findings.
"""
            raw = gl.nondet.exec_prompt(aggregate_prompt, response_format="json")
            if isinstance(raw, str):
                raw = json.loads(raw)
            assessment = json.loads(
                _normalize_assessment(raw, contribution_type)
            )
            if (
                assessment["verified_evidence_count"] != verified_count
                or assessment["total_evidence_count"] != total_count
            ):
                raise gl.vm.UserError("Assessment evidence counts do not match findings")
            return json.dumps(
                {"assessment": assessment, "findings": findings},
                sort_keys=True,
                separators=(",", ":"),
            )

        def validate(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                leader_payload = json.loads(leader_result.calldata)
                if not isinstance(leader_payload, dict):
                    return False
                if set(leader_payload.keys()) != {"assessment", "findings"}:
                    return False
                leader = json.loads(
                    _normalize_assessment(
                        leader_payload["assessment"], contribution_type
                    )
                )
                leader_findings = leader_payload["findings"]
                if not isinstance(leader_findings, list) or len(leader_findings) != len(evidence_urls):
                    return False
                for url, finding in zip(evidence_urls, leader_findings):
                    _normalize_finding(finding, url)

                validator_payload = json.loads(evaluate_once())
                validator = validator_payload["assessment"]
                if validator["total_evidence_count"] != len(evidence_urls):
                    return False
                return (
                    leader["valid"] == validator["valid"]
                    and leader["category"] == validator["category"]
                    and leader["score_bucket"] == validator["score_bucket"]
                    and leader["verified_evidence_count"]
                    == validator["verified_evidence_count"]
                    and leader["total_evidence_count"]
                    == validator["total_evidence_count"]
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
        assessment = json.loads(
            _normalize_assessment(result["assessment"], contribution.contribution_type)
        )
        self.verifications[contribution_id] = Verification(
            contribution_id=contribution_id,
            valid=assessment["valid"],
            score_bucket=assessment["score_bucket"],
            category=assessment["category"],
            verified_evidence_count=assessment["verified_evidence_count"],
            total_evidence_count=assessment["total_evidence_count"],
            reason=assessment["reason"],
            normalized_evidence_json=json.dumps(
                result["findings"], sort_keys=True, separators=(",", ":")
            ),
        )
        contribution.status = "VERIFIED" if assessment["valid"] else "REJECTED"

    @gl.public.view
    def get_verification(self, contribution_id: str) -> dict:
        verification = self.verifications[contribution_id]
        return {
            "contribution_id": verification.contribution_id,
            "valid": verification.valid,
            "score_bucket": verification.score_bucket,
            "category": verification.category,
            "verified_evidence_count": verification.verified_evidence_count,
            "total_evidence_count": verification.total_evidence_count,
            "reason": verification.reason,
            "normalized_evidence": json.loads(verification.normalized_evidence_json),
        }

    @gl.public.view
    def verification_exists(self, contribution_id: str) -> bool:
        return contribution_id in self.verifications
