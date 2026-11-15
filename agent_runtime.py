"""AgentCore Runtime entrypoint. Payload contains base64 encoded source files."""
import base64
import os
import tempfile
from pathlib import Path
from bedrock_agentcore import BedrockAgentCoreApp
from quotation_agent.aws_adapter import GatewayTools, MemoryState
from quotation_agent.bedrock_extraction import BedrockFieldExtractor
from quotation_agent.workflow import build_quote, write_outputs

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    attachments = payload.get("attachments") or []
    if not attachments: raise ValueError("At least one source file is required")
    if len(attachments) > 10: raise ValueError("Too many attachments")
    actor_id = payload.get("actor_id", "customer_example")
    session_id = payload.get("session_id", "RFQ_2026_118")
    gateway = GatewayTools()
    memory = MemoryState()
    previous = memory.latest(actor_id, session_id)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, attachment in enumerate(attachments):
            name = Path(attachment["name"]).name
            if Path(name).suffix.lower() not in (".txt", ".xlsx", ".pptx", ".pdf"):
                raise ValueError("Unsupported attachment type")
            data = base64.b64decode(attachment["data_b64"], validate=True)
            if len(data) > 5_000_000: raise ValueError("Attachment exceeds 5 MB")
            path = Path(tmp) / f"{i}_{name}"
            path.write_bytes(data)
            paths.append(path)
        context = {k:previous[k] for k in ("rfq_no", "customer", "buyer_name", "delivery", "requested_discount_pct") if previous and k in previous}
        context.update(payload.get("context") or {})
        model_id = os.environ.get("BEDROCK_EXTRACTION_MODEL_ID", "").strip()
        extractor = BedrockFieldExtractor(model_id=model_id) if model_id else None
        quote = build_quote(paths, context, price_tool=gateway.price_line,
                            approval_tool=gateway.approval_policy, extractor=extractor)
        output = write_outputs(quote, Path(tmp) / "out")
        pdf_b64 = base64.b64encode((output / "quotation.pdf").read_bytes()).decode()
    memory.save(actor_id, session_id, quote)
    return {"quote": quote, "pdf_b64": pdf_b64, "previous_session_state": previous}


if __name__ == "__main__": app.run()
