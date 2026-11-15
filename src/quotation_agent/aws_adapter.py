"""AgentCore Gateway and Memory adapters. Cloud path intentionally fails closed."""
import json
import os
from datetime import datetime, timezone


class GatewayTools:
    def __init__(self):
        self.url = os.environ["AGENTCORE_GATEWAY_URL"].rstrip("/")
        if not self.url.endswith("/mcp"): self.url += "/mcp"
        self.price_name = os.environ.get("AGENTCORE_PRICE_TOOL", "QuotationTools___price_line")
        self.approval_name = os.environ.get("AGENTCORE_APPROVAL_TOOL", "QuotationTools___approval_policy")

    def _call(self, name, arguments):
        import boto3
        import requests
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        region = os.environ.get("AWS_REGION", "ap-southeast-1")
        version = "2026-07-28"
        body = json.dumps({"jsonrpc":"2.0", "id":1, "method":"tools/call",
                           "params":{"name":name,"arguments":arguments,"_meta":{
                               "io.modelcontextprotocol/protocolVersion": version,
                               "io.modelcontextprotocol/clientInfo": {"name":"axrail-quotation-agent","version":"1.0"},
                               "io.modelcontextprotocol/clientCapabilities": {}}}}, separators=(",", ":")).encode()
        headers = {"Content-Type":"application/json", "Accept":"application/json, text/event-stream",
                   "MCP-Protocol-Version":version, "Mcp-Method":"tools/call", "Mcp-Name":name}
        credentials = boto3.Session(region_name=region).get_credentials()
        if credentials is None: raise RuntimeError("AWS credentials are required")
        request = AWSRequest(method="POST", url=self.url, data=body, headers=headers)
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", region).add_auth(request)
        response = requests.post(self.url, data=body, headers=dict(request.headers), timeout=45)
        if not response.ok:
            raise RuntimeError(f"Gateway HTTP {response.status_code}: {response.text[:500]}")
        raw = response.text
        if raw.startswith("data:") or "\ndata:" in raw:
            raw = next(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
        envelope = json.loads(raw)
        if "error" in envelope: raise RuntimeError(str(envelope["error"]))
        result = envelope["result"]
        if result.get("isError"): raise RuntimeError(str(result))
        for item in result.get("content", []):
            if item.get("type") == "text": return json.loads(item["text"])
        if "structuredContent" in result: return result["structuredContent"]
        raise RuntimeError("Gateway returned no structured tool output")

    def price_line(self, part): return self._call(self.price_name, {"part": part})
    def approval_policy(self, lines, requested_discount_pct=None):
        args = {"lines": lines}
        if requested_discount_pct is not None: args["requested_discount_pct"] = requested_discount_pct
        return self._call(self.approval_name, args)


class MemoryState:
    def __init__(self):
        import boto3
        self.id = os.environ["AGENTCORE_MEMORY_ID"]
        self.client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))

    def latest(self, actor_id, session_id):
        response = self.client.list_events(memoryId=self.id, actorId=actor_id,
                                           sessionId=session_id, includePayloads=True, maxResults=20)
        events = sorted(response.get("events", []), key=lambda x: x["eventTimestamp"])
        for event in reversed(events):
            for payload in event.get("payload", []):
                if "json" in payload and "content" in payload["json"]:
                    return payload["json"]["content"]
        return None

    def save(self, actor_id, session_id, quote):
        # Store state, not attachments or buyer email body. Keeps Memory usage small.
        state = {"quote_no":quote["quote_no"], "rfq_no":quote["rfq_no"],
                 "total_myr":quote["total_myr"], "approval":quote["approval"],
                 "review":quote["review"], "date":quote["date"],
                 "customer":quote["customer"], "buyer_name":quote["buyer_name"],
                 "delivery":quote["delivery"], "requested_discount_pct":quote["requested_discount_pct"]}
        return self.client.create_event(memoryId=self.id, actorId=actor_id, sessionId=session_id,
                                        eventTimestamp=datetime.now(timezone.utc), payload=[{"json":{"content":state}}])
