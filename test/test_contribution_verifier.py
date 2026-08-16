import pytest


def _deploy(direct_deploy):
    return direct_deploy(
        "contracts/contribution_verifier.py",
        sdk_version="v0.2.12",
    )


def test_submit_contribution_stores_claim(direct_vm, direct_deploy):
    contract = _deploy(direct_deploy)
    contract.submit_contribution(
        "contrib-001",
        "Improve wallet connector",
        "Adds support for a commonly used Web3 wallet.",
        "https://github.com/example/project/pull/1",
        "technical",
    )

    contribution = contract.get_contribution("contrib-001")
    assert contribution["title"] == "Improve wallet connector"
    assert contribution["contribution_type"] == "technical"
    assert contribution["status"] == "SUBMITTED"


@pytest.mark.parametrize(
    ("contribution_type", "message"),
    [
        ("code", "Unsupported contribution category"),
        ("", "Unsupported contribution category"),
    ],
)
def test_submit_rejects_unsupported_type(
    direct_deploy, contribution_type, message
):
    contract = _deploy(direct_deploy)
    with pytest.raises(Exception, match=message):
        contract.submit_contribution(
            "contrib-001",
            "A contribution",
            "A description",
            "https://example.com/evidence",
            contribution_type,
        )


def test_verification_uses_structured_nondeterministic_result(
    direct_vm, direct_deploy
):
    contract = _deploy(direct_deploy)
    contract.submit_contribution(
        "contrib-001",
        "Fix a protocol bug",
        "Prevents an incorrect accounting result.",
        "https://example.com/evidence",
        "technical",
    )
    direct_vm.mock_web(
        r"example\.com/evidence",
        {"status": 200, "body": "The patch and tests are described here."},
    )
    direct_vm.mock_llm(
        r"Evaluate whether this Web3 contribution is meaningful",
        '{"valid":true,"score":90,"category":"technical",'
        '"reason":"The evidence supports a concrete fix"}',
    )

    contract.verify_contribution("contrib-001")

    assert contract.get_verification("contrib-001") == {
        "contribution_id": "contrib-001",
        "valid": True,
        "score": 90,
        "category": "technical",
        "reason": "The evidence supports a concrete fix",
    }
    assert contract.get_contribution("contrib-001")["status"] == "VERIFIED"


@pytest.mark.parametrize(
    "result",
    [
        '{"valid":"yes","score":90,"category":"technical","reason":"x"}',
        '{"valid":true,"score":101,"category":"technical","reason":"x"}',
        '{"valid":true,"score":90,"category":"research","reason":"x"}',
        '{"valid":true,"score":90,"category":"technical","reason":""}',
    ],
)
def test_verification_rejects_invalid_assessment(direct_vm, direct_deploy, result):
    contract = _deploy(direct_deploy)
    contract.submit_contribution(
        "contrib-001",
        "Fix a protocol bug",
        "Prevents an incorrect accounting result.",
        "https://example.com/evidence",
        "technical",
    )
    direct_vm.mock_web(
        r"example\.com/evidence",
        {"status": 200, "body": "The patch and tests are described here."},
    )
    direct_vm.mock_llm(
        r"Evaluate whether this Web3 contribution is meaningful", result
    )

    with pytest.raises(Exception):
        contract.verify_contribution("contrib-001")

    assert contract.verification_exists("contrib-001") is False


def _capture_validator(direct_vm, direct_deploy, validator_result):
    contract = _deploy(direct_deploy)
    contract.submit_contribution(
        "contrib-001",
        "Fix a protocol bug",
        "Prevents an incorrect accounting result.",
        "https://example.com/evidence",
        "technical",
    )
    direct_vm.mock_web(
        r"example\.com/evidence",
        {"status": 200, "body": "The patch and tests are described here."},
    )
    direct_vm.mock_llm(
        r"Evaluate whether this Web3 contribution is meaningful",
        '{"valid":true,"score":90,"category":"technical","reason":"leader"}',
    )
    contract.verify_contribution("contrib-001")

    direct_vm.clear_mocks()
    direct_vm.mock_web(
        r"example\.com/evidence",
        {"status": 200, "body": "The patch and tests are described here."},
    )
    direct_vm.mock_llm(
        r"Evaluate whether this Web3 contribution is meaningful",
        validator_result,
    )
    return direct_vm


@pytest.mark.parametrize(
    "leader_result",
    [
        "not json",
        '{"valid":true,"score":90,"category":"technical"}',
        '{"valid":true,"score":90,"category":"technical","reason":"x",'
        '"extra":"x"}',
        '{"valid":true,"score":false,"category":"technical","reason":"x"}',
        '{"valid":true,"score":-1,"category":"technical","reason":"x"}',
        '{"valid":true,"score":101,"category":"technical","reason":"x"}',
        '{"valid":true,"score":90,"category":"research","reason":"x"}',
        '{"valid":true,"score":90,"category":"documentation","reason":"x"}',
        '{"valid":true,"score":90,"category":"technical","reason":""}',
    ],
)
def test_validator_rejects_malformed_leader_result(
    direct_vm, direct_deploy, leader_result
):
    vm = _capture_validator(
        direct_vm,
        direct_deploy,
        '{"valid":true,"score":90,"category":"technical","reason":"validator"}',
    )

    assert vm.run_validator(leader_result=leader_result) is False


@pytest.mark.parametrize(
    ("leader_score", "validator_score", "expected"),
    [(90, 80, True), (90, 79, False)],
)
def test_validator_enforces_score_tolerance(
    direct_vm, direct_deploy, leader_score, validator_score, expected
):
    validator = (
        '{"valid":true,"score":'
        + str(validator_score)
        + ',"category":"technical","reason":"validator"}'
    )
    vm = _capture_validator(direct_vm, direct_deploy, validator)
    leader = (
        '{"valid":true,"score":'
        + str(leader_score)
        + ',"category":"technical","reason":"leader"}'
    )

    assert vm.run_validator(leader_result=leader) is expected


def test_validator_rejects_validity_disagreement(direct_vm, direct_deploy):
    vm = _capture_validator(
        direct_vm,
        direct_deploy,
        '{"valid":false,"score":10,"category":"technical","reason":"validator"}',
    )
    leader = (
        '{"valid":true,"score":10,"category":"technical","reason":"leader"}'
    )

    assert vm.run_validator(leader_result=leader) is False
