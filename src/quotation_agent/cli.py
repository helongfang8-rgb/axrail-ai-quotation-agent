import argparse
import json
from pathlib import Path
from .workflow import build_quote, write_outputs


def main():
    parser = argparse.ArgumentParser(description="Create an auditable draft CNC quotation")
    parser.add_argument("files", nargs="+", help="Email .txt, Excel .xlsx, PowerPoint .pptx or PDF .pdf")
    parser.add_argument("--context", help="JSON file with RFQ/customer/discount metadata for attachment-only runs")
    parser.add_argument("--output", default="output")
    parser.add_argument("--bedrock-extraction", action="store_true",
                        help="Use the configured Bedrock model to propose evidence-backed fields (incurs model charges)")
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text()) if args.context else None
    extractor = None
    if args.bedrock_extraction:
        from .bedrock_extraction import BedrockFieldExtractor
        extractor = BedrockFieldExtractor()
    quote = build_quote(args.files, context, extractor=extractor)
    out = write_outputs(quote, args.output)
    print(json.dumps({"quote_no":quote["quote_no"], "total_myr":quote["total_myr"],
                      "approval":quote["approval"]["status"],
                      "priced":[x["part_no"] for x in quote["lines"] if x["status"]=="priced"],
                      "held":[x["part_no"] for x in quote["lines"] if x["status"]=="hold"],
                      "output_dir":str(out)}, indent=2))


if __name__ == "__main__": main()
