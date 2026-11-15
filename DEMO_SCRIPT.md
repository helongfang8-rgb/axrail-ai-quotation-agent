# Eight-minute screen recording plan and narration (English)

The supplied sample files have been run locally and through the deployed AgentCore Runtime in AWS Singapore. Record both the local scenarios and one cloud invocation. Keep account identifiers, credentials and billing details out of the recording.

## 0:00–1:30 — Architecture

Show the Mermaid diagram in the README and `agent_runtime.py`, `lambda_handler.py`, and `aws_adapter.py`.

> This is a review-first quotation workflow for a CNC shop. Source files are normalized into one RFQ structure. The Runtime hosts the workflow; the Gateway exposes deterministic pricing and approval tools through MCP; Memory stores the RFQ session review state. An optional Bedrock Converse step proposes fields from email and searchable PDF text with source evidence. Program validation and human review remain between extraction and pricing. IAM and SigV4 secure the tool path. AgentCore Code Interpreter and Browser are unnecessary here, because fixed arithmetic and supplied files solve this task more cheaply and reliably. Observability uses Runtime and Lambda logs in CloudWatch. Compared with a typical LangGraph or LangChain supply-chain agent, this design keeps explicit workflow state, tool contracts, review gates and tests; AgentCore replaces self-managed serving, custom tool access and ad hoc session memory.

## 1:30–4:30 — Live local run in two formats

Show the command line, `quote.json`, `quotation.pdf`, `review.json` and `email_draft.txt`. Run:

```bash
PYTHONPATH=src python3 -m quotation_agent.cli inputs/rfq_email.txt --context demo_context.json --output output_email
PYTHONPATH=src python3 -m quotation_agent.cli inputs/part_list.xlsx inputs/part_spec.pptx --context demo_context.json --output output_attachments
```

> The first run uses the email body. The second uses Excel and PowerPoint, with the same RFQ metadata supplied separately because the attachments omit the discount request. Both produce the same three priced items and MYR 74,684.00 draft total. The two other parts are on hold. The PDF contains the line table, total, validity and assumptions. The email is only a draft; the system never sends it.

## 4:30–6:15 — Problems and policy

Run:

```bash
PYTHONPATH=src python3 -m quotation_agent.cli inputs/rfq_email.txt inputs/part_list.xlsx inputs/part_spec.pptx inputs/drawing_CVR-310_RevB.pdf --context demo_context.json --output output_all
```

Open the PDF and `review.json`.

> The drawing says 800 covers, while the email and Excel say 1,000. The agent flags the conflict and excludes that line, lowering the priced subtotal to MYR 24,334.00. The spacer has no quantity, so setup cost per unit cannot be calculated. The titanium housing has no listed material price, and its tolerance is tighter than the standard rate table. These are estimator decisions. The customer requested 15% off, above the standard maximum of 8%, so it needs sales manager approval. I assume quotes of MYR 20,000 or more need approval because the brief does not give a threshold. The 15% is never silently applied.

## 6:15–7:30 — Traceability and cost

Open `pricing.py` and one priced line in `quote.json`.

> For the bracket, the supplied example gives unit cost of MYR 21.20. I interpret 25% margin as cost divided by 0.75, giving MYR 28.27 list price. A standard 5% volume discount gives MYR 26.86 per unit. Each line contains the exact table rates, components and source references. The demonstrated path makes no model call. Cloud cost per quote would be Runtime compute, Gateway and Lambda calls, small Memory events and logs. Singapore, ap-southeast-1, is my proposed production region for this Malaysian customer, subject to their residency and contract requirements.

## 7:30–8:00 — Cloud verification and limits

Show the successful AgentCore Runtime invocation, the returned quote, the Gateway tool calls, the saved Memory session state, and the relevant CloudWatch logs. Do not describe these logs as distributed traces.

> Four local tests cover the worked arithmetic, missing rates and quantity, format equivalence and PDF conflict. The live AgentCore invocation returned a quote through Gateway tools, and a follow-up invocation retrieved saved session state from Memory. Runtime and Lambda logs are available in CloudWatch; distributed traces have not been verified. The optional Bedrock extraction code is not enabled in this verified run; a live model invocation requires account model access and billable requests. Scanned drawings still need OCR, and arbitrary layouts need a validated extraction extension.
