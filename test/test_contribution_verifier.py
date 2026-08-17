import json

import pytest


SUPPORTED_FINDING = (
    '{"url":"https://example.com/evidence","accessible":true,'
    '"relevant":true,"supports_claim":true,'
    '"evidence_type":"code_repository","finding":"A concrete patch and tests."}'
)
SUPPORTED_ASSESSMENT = (
    '{"valid":true,"category":"technical","score_bucket":"STRONG",'
    '"verified_evidence_count":1,"total_evidence_count":1,'
    '"reason":"The evidence shows a substantive technical change."}'
)


def _deploy(direct_deploy):
    return direct_deploy("contracts/contribution_verifier.py", sdk_version="v0.2.12")


def _submit(contract, evidence_urls=None, contribution_type="technical"):
    if evidence_urls is None:
        evidence_urls = ["https://example.com/evidence"]
    contract.submit_contribution(
        "contrib-001",
        "Improve wallet connector",
        "Adds support for a commonly used Web3 wallet.",
        evidence_urls,
        contribution_type,
    )


def _mock_supported(direct_vm, urls=("evidence",), aggregate=SUPPORTED_ASSESSMENT):
    for url in urls:
        direct_vm.mock_web(
            rf"example\.com/{url}",
            {"status": 200, "body": "The patch and tests are described here."},
        )
    direct_vm.mock_llm(r"Normalize exactly one public evidence item", SUPPORTED_FINDING)
    direct_vm.mock_llm(r"Aggregate normalized evidence findings", aggregate)


def test_submit_stores_multiple_evidence_urls(direct_deploy):
    contract = _deploy(direct_deploy)
    urls = ["https://example.com/one", "https://example.com/two"]
    _submit(contract, urls)

    contribution = contract.get_contribution("contrib-001")
    assert contribution["evidence_urls"] == urls
    assert contribution["status"] == "SUBMITTED"


@pytest.mark.parametrize(
    ("evidence_urls", "message"),
    [([], "At least one evidence URL is required"),
     ([f"https://example.com/{i}" for i in range(6)], "Too many evidence URLs"),
     (["ftp://example.com/evidence"], "Evidence URL must use http or https"),
     (["https://example.com/evidence", "https://example.com/evidence"], "unique")],
)
def test_submit_rejects_invalid_evidence_input(direct_deploy, evidence_urls, message):
    contract = _deploy(direct_deploy)
    with pytest.raises(Exception, match=message):
        _submit(contract, evidence_urls)


def test_submit_rejects_unsupported_type(direct_deploy):
    contract = _deploy(direct_deploy)
    with pytest.raises(Exception, match="Unsupported contribution category"):
        _submit(contract, contribution_type="code")


def test_duplicate_contribution_rejected(direct_deploy):
    contract = _deploy(direct_deploy)
    _submit(contract)
    with pytest.raises(Exception, match="Contribution already exists"):
        _submit(contract)


def test_verification_stores_bucket_counts_and_normalized_findings(direct_vm, direct_deploy):
    contract = _deploy(direct_deploy)
    _submit(contract)
    _mock_supported(direct_vm)

    contract.verify_contribution("contrib-001")

    verification = contract.get_verification("contrib-001")
    assert verification["score_bucket"] == "STRONG"
    assert verification["verified_evidence_count"] == 1
    assert verification["total_evidence_count"] == 1
    assert verification["normalized_evidence"][0]["supports_claim"] is True
    assert contract.get_contribution("contrib-001")["status"] == "VERIFIED"


@pytest.mark.parametrize(
    "aggregate",
    [
        "not json",
        '{"valid":true,"category":"technical","score_bucket":"STRONG",'
        '"verified_evidence_count":1,"total_evidence_count":1}',
        '{"valid":true,"category":"technical","score_bucket":"UNKNOWN",'
        '"verified_evidence_count":1,"total_evidence_count":1,"reason":"x"}',
        '{"valid":true,"category":"research","score_bucket":"STRONG",'
        '"verified_evidence_count":1,"total_evidence_count":1,"reason":"x"}',
        '{"valid":"yes","category":"technical","score_bucket":"STRONG",'
        '"verified_evidence_count":1,"total_evidence_count":1,"reason":"x"}',
        '{"valid":true,"category":"technical","score_bucket":"STRONG",'
        '"verified_evidence_count":-1,"total_evidence_count":1,"reason":"x"}',
        '{"valid":true,"category":"technical","score_bucket":"STRONG",'
        '"verified_evidence_count":2,"total_evidence_count":1,"reason":"x"}',
        '{"valid":true,"category":"technical","score_bucket":"STRONG",'
        '"verified_evidence_count":1,"total_evidence_count":1,"reason":"",'
        '"extra":"x"}',
    ],
)
def test_malformed_aggregate_is_not_stored(direct_vm, direct_deploy, aggregate):
    contract = _deploy(direct_deploy)
    _submit(contract)
    _mock_supported(direct_vm, aggregate=aggregate)

    with pytest.raises(Exception):
        contract.verify_contribution("contrib-001")
    assert contract.verification_exists("contrib-001") is False


def _capture_validator(direct_vm, direct_deploy, validator_aggregate=SUPPORTED_ASSESSMENT):
    contract = _deploy(direct_deploy)
    _submit(contract)
    _mock_supported(direct_vm, aggregate=SUPPORTED_ASSESSMENT)
    contract.verify_contribution("contrib-001")
    direct_vm.clear_mocks()
    _mock_supported(direct_vm, aggregate=validator_aggregate)
    return direct_vm


def _leader_payload(**overrides):
    assessment = json.loads(SUPPORTED_ASSESSMENT)
    assessment.update(overrides)
    return json.dumps({
        "assessment": assessment,
        "findings": [json.loads(SUPPORTED_FINDING)],
    })


@pytest.mark.parametrize(
    "leader_result",
    [
        "not json",
        '{"assessment":{},"findings":[]}',
        json.dumps({"assessment": json.loads(SUPPORTED_ASSESSMENT), "findings": []}),
        json.dumps({"assessment": json.loads(SUPPORTED_ASSESSMENT), "findings": [
            {"url": "https://example.com/evidence", "accessible": True,
             "relevant": True, "supports_claim": True,
             "evidence_type": "invalid", "finding": "x"}
        ]}),
    ],
)
def test_validator_rejects_malformed_leader_result(direct_vm, direct_deploy, leader_result):
    vm = _capture_validator(direct_vm, direct_deploy)
    assert vm.run_validator(leader_result=leader_result) is False


def test_validator_requires_exact_bucket_agreement(direct_vm, direct_deploy):
    vm = _capture_validator(direct_vm, direct_deploy)
    assert vm.run_validator(leader_result=_leader_payload(score_bucket="MODERATE")) is False


def test_validator_requires_exact_validity_agreement(direct_vm, direct_deploy):
    vm = _capture_validator(direct_vm, direct_deploy)
    assert vm.run_validator(leader_result=_leader_payload(valid=False)) is False


def test_validator_requires_exact_category_agreement(direct_vm, direct_deploy):
    vm = _capture_validator(direct_vm, direct_deploy)
    assert vm.run_validator(leader_result=_leader_payload(category="research")) is False


def test_validator_allows_reason_difference(direct_vm, direct_deploy):
    vm = _capture_validator(direct_vm, direct_deploy)
    assert vm.run_validator(leader_result=_leader_payload(reason="Leader wording")) is True


def test_inaccessible_evidence_does_not_count(direct_vm, direct_deploy):
    contract = _deploy(direct_deploy)
    _submit(contract)
    direct_vm.mock_web(
        r"example\.com/evidence", {"status": 404, "body": "missing"}
    )

    contract.verify_contribution("contrib-001")
    verification = contract.get_verification("contrib-001")
    assert verification["valid"] is False
    assert verification["score_bucket"] == "INSUFFICIENT"
    assert verification["verified_evidence_count"] == 0
    assert verification["normalized_evidence"][0]["accessible"] is False


def test_mixed_accessible_and_inaccessible_evidence_aggregates_correctly(
    direct_vm, direct_deploy
):
    contract = _deploy(direct_deploy)
    _submit(contract, ["https://example.com/evidence", "https://example.com/missing"])
    direct_vm.mock_web(
        r"example\.com/evidence", {"status": 200, "body": "A concrete patch."}
    )
    direct_vm.mock_web(
        r"example\.com/missing", {"status": 404, "body": "missing"}
    )
    finding = SUPPORTED_FINDING.replace(
        "https://example.com/evidence", "https://example.com/evidence"
    )
    direct_vm.mock_llm(r"Normalize exactly one public evidence item", finding)
    direct_vm.mock_llm(
        r"Aggregate normalized evidence findings",
        '{"valid":true,"category":"technical","score_bucket":"MODERATE",'
        '"verified_evidence_count":1,"total_evidence_count":2,"reason":"One item supports the claim."}',
    )

    contract.verify_contribution("contrib-001")
    verification = contract.get_verification("contrib-001")
    assert verification["verified_evidence_count"] == 1
    assert verification["total_evidence_count"] == 2
    assert verification["normalized_evidence"][1]["accessible"] is False


def test_all_inaccessible_evidence_is_insufficient(direct_vm, direct_deploy):
    contract = _deploy(direct_deploy)
    _submit(contract, ["https://example.com/one", "https://example.com/two"])
    for url in ("one", "two"):
        direct_vm.mock_web(rf"example\.com/{url}", {"status": 500, "body": "down"})

    contract.verify_contribution("contrib-001")
    verification = contract.get_verification("contrib-001")
    assert verification["valid"] is False
    assert verification["score_bucket"] == "INSUFFICIENT"
    assert verification["verified_evidence_count"] == 0
    assert verification["total_evidence_count"] == 2
