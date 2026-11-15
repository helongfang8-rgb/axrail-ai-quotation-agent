"""Encode local sample files for AgentCore Runtime invocation."""
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
context = json.loads((ROOT / "demo_context.json").read_text())
attachments = []
for name in sys.argv[1:]:
    path = Path(name)
    attachments.append({"name":path.name,"data_b64":base64.b64encode(path.read_bytes()).decode()})
print(json.dumps({"actor_id":"customer_example","session_id":"RFQ_2026_118",
                  "context":context,"attachments":attachments}))
