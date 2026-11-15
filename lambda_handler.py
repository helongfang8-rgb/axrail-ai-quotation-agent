"""Deploy this file plus the quotation_agent package to Lambda behind Gateway."""
from quotation_agent.pricing import price_line, approval_policy


def lambda_handler(event, context):
    name = context.client_context.custom["bedrockAgentCoreToolName"].split("___", 1)[1]
    if name == "price_line": return price_line(event["part"])
    if name == "approval_policy": return approval_policy(event["lines"], event.get("requested_discount_pct"))
    raise ValueError(f"Unknown tool: {name}")
