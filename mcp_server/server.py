"""UKNest MCP server: exposes the project's capabilities as MCP tools.

Any MCP client (our agent on Day 4, Claude Desktop, MCP Inspector...) can
discover these tools and call them. The client never needs to know about
Qdrant, postcodes.io or OpenStreetMap; it only sees the tool descriptions.

Run (stdio, used by the agent and the test client):
    python -m mcp_server.server

Run over HTTP (used on Day 6 when it gets its own Docker container):
    MCP_TRANSPORT=streamable-http python -m mcp_server.server
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from mcp_server import local_services
from rag.retriever import retrieve

# stdio servers must never print to stdout (it carries the protocol), so log to stderr
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("uknest-mcp")

mcp = FastMCP(
    "uknest",
    instructions=(
        "Tools for people settling in the UK. Use search_uk_guidance for rules and "
        "processes (right to work, renting, council tax, healthcare) and always cite "
        "the returned url and last_updated date. Use lookup_postcode and "
        "find_nearby_services for location questions. Information only, not legal advice."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)

Category = Literal["right_to_work", "renting", "council_tax", "healthcare"]
ServiceType = Literal[
    "gp", "pharmacy", "dentist", "hospital", "supermarket",
    "post_office", "bank", "mobile_phone_shop", "library",
]


@mcp.tool()
def search_uk_guidance(query: str, category: Optional[Category] = None, k: int = 5) -> dict:
    """Search official GOV.UK guidance for newcomers to the UK.

    Use for questions about rules and processes: proving right to work or right
    to rent, eVisas and share codes, National Insurance numbers, tenancy
    deposits and renting, council tax, and NHS access for migrants.

    Args:
        query: The user's question in plain English.
        category: Optional filter: right_to_work, renting, council_tax or healthcare.
        k: Number of passages to return (1-8).
    """
    k = max(1, min(k, 8))
    log.info("search_uk_guidance query=%r category=%s", query, category)
    hits = retrieve(query, k=k, category=category)
    return {
        "query": query,
        "results": [
            {
                "rank": i,
                "title": h["title"],
                "section": h["heading"],
                "url": h["url"],
                "last_updated": (h.get("public_updated_at") or "")[:10] or None,
                "score": h["score"],
                "text": h["text"].split("\n\n", 1)[-1],
            }
            for i, h in enumerate(hits, 1)
        ],
        "note": "Answer only from these passages and cite url + last_updated. "
                "If they do not answer the question, say so.",
    }


@mcp.tool()
def lookup_postcode(postcode: str) -> dict:
    """Look up a UK postcode: local council (who council tax is paid to),
    ward, region, country, parliamentary constituency and coordinates.

    Args:
        postcode: A UK postcode, e.g. "IG11 7QJ" or "sw1a1aa".
    """
    log.info("lookup_postcode %s", postcode)
    return local_services.lookup_postcode(postcode)


@mcp.tool()
def find_nearby_services(postcode: str, service_type: ServiceType,
                         radius_m: int = 1500, limit: int = 8) -> dict:
    """Find nearby services (GP surgeries, pharmacies, supermarkets, banks, etc.)
    around a UK postcode, nearest first, using OpenStreetMap.

    Args:
        postcode: A UK postcode to search around.
        service_type: gp, pharmacy, dentist, hospital, supermarket, post_office,
            bank, mobile_phone_shop or library.
        radius_m: Search radius in metres (200-5000, default 1500).
        limit: Maximum number of places to return.
    """
    log.info("find_nearby_services %s %s r=%s", postcode, service_type, radius_m)
    return local_services.find_nearby_services(postcode, service_type, radius_m, limit)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    log.info("Starting UKNest MCP server (transport=%s)", transport)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
