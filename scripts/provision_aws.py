"""Provision Gateway, Lambda tools and short-term Memory in a global AWS region.

Requires AWS credentials and permissions. It is intentionally not run automatically.
Review resources and costs before executing in an account.
"""
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
if REGION.startswith("cn-"):
    raise SystemExit("Use an AWS global region, not an AWS China region")


def role(iam, name, service, policy=None):
    trust = {"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":service},"Action":"sts:AssumeRole"}]}
    try: arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    if policy:
        iam.put_role_policy(RoleName=name, PolicyName="QuotationAgentAccess", PolicyDocument=json.dumps(policy))
    return arn


def lambda_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "lambda_handler.py", "lambda_handler.py")
        for file in (ROOT / "src/quotation_agent").glob("*.py"):
            z.write(file, f"quotation_agent/{file.name}")
    return out.getvalue()


def main():
    sts = boto3.client("sts", region_name=REGION)
    account = sts.get_caller_identity()["Account"]
    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda", region_name=REGION)
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    prefix = f"axrail-quotation-{account[-4:]}"
    function_name = prefix + "-tools"
    lambda_arn = f"arn:aws:lambda:{REGION}:{account}:function:{function_name}"
    lambda_role = role(iam, prefix + "-lambda-role", "lambda.amazonaws.com")
    iam.attach_role_policy(RoleName=prefix + "-lambda-role", PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    gateway_policy = {"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"lambda:InvokeFunction","Resource":lambda_arn}]}
    gateway_role = role(iam, prefix + "-gateway-role", "bedrock-agentcore.amazonaws.com", gateway_policy)
    time.sleep(10)
    package = lambda_zip()
    try:
        lambda_client.get_function(FunctionName=function_name)
        lambda_client.update_function_code(FunctionName=function_name, ZipFile=package)
    except lambda_client.exceptions.ResourceNotFoundException:
        lambda_client.create_function(FunctionName=function_name, Runtime="python3.12",
                                      Role=lambda_role, Handler="lambda_handler.lambda_handler",
                                      Code={"ZipFile":package}, Timeout=30)
    # IAM protects the inbound MCP endpoint. Reuse resources on a retry.
    gateway_name = prefix + "-gateway"
    gateway = next((g for g in control.list_gateways()["items"] if g["name"] == gateway_name), None)
    if gateway is None:
        gateway = control.create_gateway(name=gateway_name, roleArn=gateway_role,
                                         protocolType="MCP", authorizerType="AWS_IAM",
                                         protocolConfiguration={"mcp":{"supportedVersions":["2025-03-26", "2026-07-28"]}})
    gateway_id = gateway["gatewayId"]
    gateway = control.get_gateway(gatewayIdentifier=gateway_id)
    if "2026-07-28" not in gateway.get("protocolConfiguration", {}).get("mcp", {}).get("supportedVersions", []):
        gateway = control.update_gateway(gatewayIdentifier=gateway_id, name=gateway_name,
                                         roleArn=gateway_role, authorizerType="AWS_IAM",
                                         protocolType="MCP", protocolConfiguration={"mcp":{
                                             "supportedVersions":["2025-03-26", "2026-07-28"]}})
    for _ in range(30):
        gateway = control.get_gateway(gatewayIdentifier=gateway_id)
        if gateway["status"] == "READY": break
        if gateway["status"] in ("FAILED", "DELETING"):
            raise RuntimeError(f"Gateway status: {gateway['status']}")
        time.sleep(2)
    else:
        raise TimeoutError("Gateway did not become ready")
    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    if not any(t["name"] == "QuotationTools" for t in targets):
        control.create_gateway_target(gatewayIdentifier=gateway_id, name="QuotationTools",
            targetConfiguration={"mcp":{"lambda":{"lambdaArn":lambda_arn,
                "toolSchema":{"inlinePayload":json.loads((ROOT / "tools.json").read_text())}}}},
            credentialProviderConfigurations=[{"credentialProviderType":"GATEWAY_IAM_ROLE"}])
    memory_name = "AxrailQuotationMemory"
    memory = None
    for item in control.list_memories()["memories"]:
        candidate = control.get_memory(memoryId=item["id"])["memory"]
        if candidate["name"] == memory_name:
            memory = candidate
            break
    if memory is None:
        memory = control.create_memory(name=memory_name, description="Short-term RFQ review state", eventExpiryDuration=30)["memory"]
    config = {"AWS_REGION":REGION, "AGENTCORE_GATEWAY_URL":gateway["gatewayUrl"],
              "AGENTCORE_MEMORY_ID":memory["id"],
              "AGENTCORE_PRICE_TOOL":"QuotationTools___price_line",
              "AGENTCORE_APPROVAL_TOOL":"QuotationTools___approval_policy",
              "BEDROCK_EXTRACTION_MODEL_ID":""}
    (ROOT / ".env.aws.example").write_text("".join(f"{k}={v}\n" for k,v in config.items()))
    print(json.dumps({"account":account,"region":REGION,"lambda_arn":lambda_arn,
                      "gateway_id":gateway_id,"memory_id":config["AGENTCORE_MEMORY_ID"],
                      "config_file":".env.aws.example"},indent=2))


if __name__ == "__main__": main()
