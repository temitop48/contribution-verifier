import { abi, createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import "./style.css";

const RPC = "https://studio.genlayer.com/api";
const CONTRACT = "0xa6301e4b1DD6C14130Ab08449C7F58556B151da6";
const CONTRIBUTION_ID = "studionet-v2-technical-001";

const args = [
  CONTRIBUTION_ID,
  "ContributionVerifier v2 multi-evidence adjudication",
  "Implemented a GenLayer intelligent contract that independently normalizes multiple public evidence items, aggregates their findings, and uses validator consensus over a canonical material score bucket.",
  [
    "https://github.com/temitop48/contribution-verifier",
    "https://raw.githubusercontent.com/temitop48/contribution-verifier/main/contracts/contribution_verifier.py",
    "https://raw.githubusercontent.com/temitop48/contribution-verifier/main/test/test_contribution_verifier.py",
  ],
  "technical",
];

let provider = null;
let address = null;
let readClient = null;
let writeClient = null;
let transactionHash = null;
let preflightPassed = false;
let verifyPreflightPassed = false;
let verificationTransactionHash = null;

const $ = (id) => document.getElementById(id);

function safeValue(value) {
  if (typeof value === "bigint") return value.toString();
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [k, safeValue(v)]));
  if (Array.isArray(value)) return value.map(safeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, safeValue(v)]));
  }
  return value;
}

function show(element, value) {
  element.textContent = typeof value === "string"
    ? value
    : JSON.stringify(safeValue(value), null, 2);
}

function setSendEnabled(enabled) {
  preflightPassed = enabled;
  $("send").disabled = !enabled;
}

function requireProvider() {
  if (!window.ethereum) throw new Error("No EIP-1193 window.ethereum provider detected.");
  return window.ethereum;
}

function isAddress(value) {
  return typeof value === "string" && /^0x[a-fA-F0-9]{40}$/.test(value);
}

function jsonRpcAccount(address) {
  return { address, type: "json-rpc" };
}

function field(value, name) {
  return value instanceof Map ? value.get(name) : value?.[name];
}

async function ensureStudionet(provider) {
  const expectedChainId = `0x${studionet.id.toString(16)}`;
  let walletChainId = await provider.request({ method: "eth_chainId" });
  if (walletChainId === expectedChainId) return walletChainId;

  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: expectedChainId }],
    });
  } catch (error) {
    // EIP-1193 error 4902 means the requested chain is not installed.
    if (error?.code !== 4902) throw error;
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [{
        chainId: expectedChainId,
        chainName: studionet.name,
        rpcUrls: studionet.rpcUrls.default.http,
        nativeCurrency: studionet.nativeCurrency,
        blockExplorerUrls: [studionet.blockExplorers.default.url],
      }],
    });
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: expectedChainId }],
    });
  }

  walletChainId = await provider.request({ method: "eth_chainId" });
  if (walletChainId !== expectedChainId) {
    throw new Error(`Wallet remained on ${walletChainId}; expected Studionet ${expectedChainId}.`);
  }
  return walletChainId;
}

async function connectWallet() {
  try {
    provider = requireProvider();
    const accounts = await provider.request({ method: "eth_requestAccounts" });
    if (!accounts?.length) throw new Error("The wallet returned no accounts.");
    address = accounts[0];

    const [initialChainId, networkVersion] = await Promise.all([
      provider.request({ method: "eth_chainId" }).catch(() => null),
      provider.request({ method: "net_version" }).catch(() => null),
    ]);

    readClient = createClient({ chain: studionet, endpoint: RPC });
    writeClient = createClient({
      chain: studionet,
      endpoint: RPC,
      // Keep the client account as an address string so genlayer-js routes
      // eth_sendTransaction through the configured EIP-1193 provider.
      account: address,
      provider,
    });

    const chainId = await ensureStudionet(provider);

    show($("wallet"), {
      provider_detected: true,
      connectedAccount: address,
      connected_address: address,
      initial_chain_id: initialChainId,
      chain_id: chainId,
      wallet_chain_id: chainId,
      network_version: networkVersion,
      configured_network: "studionet",
      expected_studionet_chain_id: `0x${studionet.id.toString(16)}`,
      chain_matches_studionet: chainId === `0x${studionet.id.toString(16)}`,
      account_object: jsonRpcAccount(address),
      contractAddress: CONTRACT,
    });
    $("preflight").disabled = false;
    $("verifyPreflight").disabled = false;
    $("connect").textContent = "Wallet Connected";
    setSendEnabled(false);
  } catch (error) {
    show($("wallet"), { error: error.message });
    $("preflight").disabled = true;
    $("verifyPreflight").disabled = true;
  }
}

async function runPreflight() {
  setSendEnabled(false);
  $("preflight").disabled = true;
  try {
    if (!Array.isArray(args[3]) || args[3].length !== 3) {
      throw new Error("evidence_urls must be a three-element JavaScript array.");
    }

    const encoded = abi.calldata.encode(
      abi.calldata.makeCalldataObject("submit_contribution", args),
    );
    const decoded = abi.calldata.decode(encoded);
    const decodedArgs = decoded instanceof Map ? decoded.get("args") : decoded.args;
    const arrayEncoded = Array.isArray(decodedArgs?.[3]);
    if (!arrayEncoded) throw new Error("ABI decode returned a scalar evidence argument.");

    const schema = await readClient.getContractSchema(CONTRACT);
    const submitSchema = schema?.methods?.submit_contribution;
    if (!submitSchema) throw new Error("submit_contribution is absent from the deployed schema.");

    const exists = await readClient.readContract({
      address: CONTRACT,
      functionName: "contribution_exists",
      args: [CONTRIBUTION_ID],
    });
    if (exists !== false) throw new Error(`Contribution already exists or returned unexpected value: ${exists}`);

    const simulation = await writeClient.simulateWriteContract({
      account: jsonRpcAccount(address),
      address: CONTRACT,
      functionName: "submit_contribution",
      args,
    });

    show($("preflightResult"), {
      schema_loaded: true,
      submit_contribution_schema: submitSchema,
      contribution_exists: exists,
      javascript_array: Array.isArray(args[3]),
      array_length: args[3].length,
      abi_encoded_and_decoded_array: arrayEncoded,
      evidence_urls: decodedArgs[3],
      simulation_result: simulation,
      simulation_succeeded: true,
      connectedAccount: address,
      contractAddress: CONTRACT,
      typeof_connectedAccount: typeof address,
      typeof_contractAddress: typeof CONTRACT,
      send_gate: "OPEN — explicit Send click still required",
    });
    setSendEnabled(true);
  } catch (error) {
    show($("preflightResult"), { preflight_failed: true, error: error.message });
  } finally {
    $("preflight").disabled = false;
  }
}

async function sendContribution() {
  if (!preflightPassed || !writeClient) return;
  $("send").disabled = true;

  const connectedAccount = address;
  const contractAddress = CONTRACT;
  const addressDiagnostics = {
    connectedAccount,
    contractAddress,
    typeof_connectedAccount: typeof connectedAccount,
    typeof_contractAddress: typeof contractAddress,
    connectedAccount_valid: isAddress(connectedAccount),
    contractAddress_valid: isAddress(contractAddress),
  };
  show($("sendResult"), { write_preflight: addressDiagnostics });

  if (!isAddress(connectedAccount) || !isAddress(contractAddress)) {
    show($("sendResult"), {
      write_refused: true,
      reason: "Both connectedAccount and contractAddress must be 20-byte hex addresses.",
      write_preflight: addressDiagnostics,
    });
    $("send").disabled = false;
    return;
  }

  try {
    transactionHash = await writeClient.writeContract({
      // writeContract needs an Account-shaped JSON-RPC account here. Passing
      // the bare string makes the SDK later read senderAccount.address as
      // undefined. The client itself retains the string above so its custom
      // transport sends through window.ethereum.
      account: jsonRpcAccount(connectedAccount),
      address: contractAddress,
      functionName: "submit_contribution",
      args,
      value: 0n,
    });
    show($("sendResult"), {
      transaction_hash: transactionHash,
      sender: connectedAccount,
      contract: contractAddress,
      method: "submit_contribution",
      arguments: args,
      note: "The wallet popup was explicitly approved by the user.",
    });
    $("finality").disabled = false;
  } catch (error) {
    show($("sendResult"), { send_failed: true, error: error.message });
    $("send").disabled = false;
  }
}

async function checkFinality() {
  if (!transactionHash) return;
  try {
    const receipt = await readClient.waitForTransactionReceipt({
      hash: transactionHash,
      status: "FINALIZED",
      interval: 5000,
      retries: 1,
      fullTransaction: true,
    });
    show($("finalityResult"), receipt);
    $("exists").disabled = false;
    $("contribution").disabled = false;
  } catch (error) {
    show($("finalityResult"), { finality_check: "not finalized or failed", error: error.message });
  }
}

async function readExists() {
  try {
    const value = await readClient.readContract({
      address: CONTRACT,
      functionName: "contribution_exists",
      args: [CONTRIBUTION_ID],
    });
    show($("stateResult"), { contribution_exists: value });
  } catch (error) {
    show($("stateResult"), { error: error.message });
  }
}

async function readContribution() {
  try {
    const value = await readClient.readContract({
      address: CONTRACT,
      functionName: "get_contribution",
      args: [CONTRIBUTION_ID],
    });
    show($("stateResult"), { contribution: value });
  } catch (error) {
    show($("stateResult"), { error: error.message });
  }
}

async function runVerifyPreflight() {
  verifyPreflightPassed = false;
  $("verify").disabled = true;
  $("verifyPreflight").disabled = true;
  try {
    const expectedChainId = `0x${studionet.id.toString(16)}`;
    const walletChainId = provider
      ? await provider.request({ method: "eth_chainId" })
      : null;
    const contributionExists = await readClient.readContract({
      address: CONTRACT,
      functionName: "contribution_exists",
      args: [CONTRIBUTION_ID],
    });
    const contribution = await readClient.readContract({
      address: CONTRACT,
      functionName: "get_contribution",
      args: [CONTRIBUTION_ID],
    });
    const contributionStatus = field(contribution, "status");
    const verificationExists = await readClient.readContract({
      address: CONTRACT,
      functionName: "verification_exists",
      args: [CONTRIBUTION_ID],
    });
    const checks = {
      wallet_connected: Boolean(provider && address && writeClient),
      provider_detected: Boolean(provider),
      connectedAccount: address,
      connected_account_valid: isAddress(address),
      wallet_chain_id: walletChainId,
      expected_studionet_chain_id: expectedChainId,
      chain_matches_studionet: walletChainId === expectedChainId,
      contractAddress: CONTRACT,
      contract_address_valid: isAddress(CONTRACT),
      contribution_exists: contributionExists,
      contribution_status: contributionStatus,
      status_is_submitted: contributionStatus === "SUBMITTED",
      verification_exists: verificationExists,
      verification_is_absent: verificationExists === false,
    };
    // Keep the gate explicit and independent of display formatting.
    const gate = Boolean(
      provider && writeClient &&
      isAddress(address) && isAddress(CONTRACT) &&
      walletChainId === expectedChainId &&
      contributionExists === true &&
      contributionStatus === "SUBMITTED" &&
      verificationExists === false,
    );
    show($("verifyPreflightResult"), {
      checks,
      contribution,
      all_checks_passed: gate,
      send_gate: gate ? "OPEN — explicit Verify click still required" : "CLOSED",
      diagnostic_check_count: Object.keys(checks).length,
    });
    verifyPreflightPassed = gate;
    $("verify").disabled = !gate;
  } catch (error) {
    show($("verifyPreflightResult"), { preflight_failed: true, error: error.message });
  } finally {
    $("verifyPreflight").disabled = false;
  }
}

async function verifyContribution() {
  if (!verifyPreflightPassed || !writeClient) return;
  $("verify").disabled = true;
  const connectedAccount = address;
  const contractAddress = CONTRACT;
  const diagnostics = {
    connectedAccount,
    contractAddress,
    typeof_connectedAccount: typeof connectedAccount,
    typeof_contractAddress: typeof contractAddress,
    connected_account_valid: isAddress(connectedAccount),
    contract_address_valid: isAddress(contractAddress),
  };
  show($("verifyResult"), { write_preflight: diagnostics });
  if (!isAddress(connectedAccount) || !isAddress(contractAddress)) {
    show($("verifyResult"), { write_refused: true, write_preflight: diagnostics });
    $("verify").disabled = false;
    return;
  }
  try {
    verificationTransactionHash = await writeClient.writeContract({
      account: jsonRpcAccount(connectedAccount),
      address: contractAddress,
      functionName: "verify_contribution",
      args: [CONTRIBUTION_ID],
      value: 0n,
    });
    show($("verifyResult"), {
      transaction_hash: verificationTransactionHash,
      sender: connectedAccount,
      contract: contractAddress,
      method: "verify_contribution",
      arguments: [CONTRIBUTION_ID],
    });
    $("verifyFinality").disabled = false;
  } catch (error) {
    show($("verifyResult"), { send_failed: true, error: error.message });
    $("verify").disabled = false;
  }
}

function executionSucceeded(receipt) {
  return receipt?.txExecutionResultName === "FINISHED_WITH_RETURN" ||
    receipt?.execution_result === "SUCCESS";
}

async function checkVerificationFinality() {
  if (!verificationTransactionHash) return;
  $("verifyFinality").disabled = true;
  try {
    const receipt = await readClient.waitForTransactionReceipt({
      hash: verificationTransactionHash,
      status: "FINALIZED",
      interval: 5000,
      retries: 1,
      fullTransaction: true,
    });
    const statusFinalized = receipt?.statusName === "FINALIZED" || receipt?.status === "FINALIZED";
    const majorityAgree = receipt?.resultName === "MAJORITY_AGREE";
    const executionSuccess = executionSucceeded(receipt);
    show($("verifyFinalityResult"), {
      receipt,
      finalized: statusFinalized,
      majority_agree: majorityAgree,
      execution_result_success: executionSuccess,
      verification_success: statusFinalized && majorityAgree && executionSuccess,
    });
    if (statusFinalized && majorityAgree && executionSuccess) {
      $("readFinalContribution").disabled = false;
      $("readVerification").disabled = false;
    } else {
      show($("verifyFinalityResult"), {
        receipt,
        verification_success: false,
        reason: "Requires FINALIZED, MAJORITY_AGREE, and successful execution.",
        finalized: statusFinalized,
        majority_agree: majorityAgree,
        execution_result_success: executionSuccess,
      });
    }
  } catch (error) {
    show($("verifyFinalityResult"), { finality_check: "not finalized or failed", error: error.message });
    $("verifyFinality").disabled = false;
  }
}

async function readFinalContribution() {
  try {
    const contribution = await readClient.readContract({
      address: CONTRACT,
      functionName: "get_contribution",
      args: [CONTRIBUTION_ID],
    });
    show($("finalContributionResult"), {
      final_contribution: contribution,
      status: field(contribution, "status"),
    });
  } catch (error) {
    show($("finalContributionResult"), { error: error.message });
  }
}

async function readVerification() {
  try {
    const verification = await readClient.readContract({
      address: CONTRACT,
      functionName: "get_verification",
      args: [CONTRIBUTION_ID],
    });
    show($("verificationResult"), {
      verification,
      contribution_id: field(verification, "contribution_id"),
      valid: field(verification, "valid"),
      score_bucket: field(verification, "score_bucket"),
      category: field(verification, "category"),
      verified_evidence_count: field(verification, "verified_evidence_count"),
      total_evidence_count: field(verification, "total_evidence_count"),
      reason: field(verification, "reason"),
      normalized_evidence: field(verification, "normalized_evidence"),
    });
  } catch (error) {
    show($("verificationResult"), { error: error.message });
  }
}

$("connect").addEventListener("click", connectWallet);
$("preflight").addEventListener("click", runPreflight);
$("send").addEventListener("click", sendContribution);
$("finality").addEventListener("click", checkFinality);
$("exists").addEventListener("click", readExists);
$("contribution").addEventListener("click", readContribution);
$("verifyPreflight").addEventListener("click", runVerifyPreflight);
$("verify").addEventListener("click", verifyContribution);
$("verifyFinality").addEventListener("click", checkVerificationFinality);
$("readFinalContribution").addEventListener("click", readFinalContribution);
$("readVerification").addEventListener("click", readVerification);

window.ethereum?.on?.("accountsChanged", () => window.location.reload());
window.ethereum?.on?.("chainChanged", () => window.location.reload());
