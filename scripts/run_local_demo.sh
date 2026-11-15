#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR/src"

python3 -m quotation_agent.cli inputs/rfq_email.txt --context demo_context.json --output output_email
python3 -m quotation_agent.cli inputs/part_list.xlsx inputs/part_spec.pptx --context demo_context.json --output output_attachments
python3 -m quotation_agent.cli inputs/rfq_email.txt inputs/part_list.xlsx inputs/part_spec.pptx inputs/drawing_CVR-310_RevB.pdf --context demo_context.json --output output_all

echo
echo "Open output_email/quotation.pdf and output_all/quotation.pdf to compare."
echo "Read output_all/email_draft.txt and output_all/review.json for the buyer draft and review list."
