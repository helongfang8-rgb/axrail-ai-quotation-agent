"""Invoke the deployed AgentCore Runtime and save its draft quote and PDF."""
import argparse
import base64
import json
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime_arn", help="AgentCore Runtime ARN shown in the AWS console")
    parser.add_argument("payload", type=Path, help="JSON produced by make_payload.py")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--output", type=Path, default=Path("output_cloud"))
    args = parser.parse_args()
    request = args.payload.read_bytes()
    response = boto3.client("bedrock-agentcore", region_name=args.region).invoke_agent_runtime(
        agentRuntimeArn=args.runtime_arn, qualifier="DEFAULT", payload=request,
        contentType="application/json", accept="application/json")
    result = json.loads(response["response"].read())
    if "quote" not in result or "pdf_b64" not in result:
        raise RuntimeError(f"Unexpected Runtime response: {str(result)[:500]}")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "quote.json").write_text(json.dumps(result["quote"], indent=2))
    (args.output / "quotation.pdf").write_bytes(base64.b64decode(result["pdf_b64"], validate=True))
    (args.output / "previous_session_state.json").write_text(
        json.dumps(result.get("previous_session_state"), indent=2))
    print(json.dumps({"quote_no": result["quote"]["quote_no"],
                      "total_myr": result["quote"]["total_myr"],
                      "approval": result["quote"]["approval"],
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
