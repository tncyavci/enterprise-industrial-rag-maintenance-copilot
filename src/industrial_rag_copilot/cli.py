from __future__ import annotations

import argparse
import json
from industrial_rag_copilot.models import CopilotQueryRequest, SecurityClearance
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise Industrial Hybrid RAG & Maintenance Copilot CLI"
    )
    parser.add_argument("--query", required=True, help="Maintenance or diagnostic query")
    parser.add_argument(
        "--clearance",
        default="MAINTENANCE_ENGINEER_L2",
        choices=[c.value for c in SecurityClearance],
        help="Security clearance level",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Maximum SOP citations to return")
    args = parser.parse_args()

    service = IndustrialMaintenanceCopilotService()
    response = service.answer_query(
        CopilotQueryRequest(
            query=args.query,
            user_clearance=SecurityClearance(args.clearance),
            top_k=args.top_k,
        )
    )
    print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
