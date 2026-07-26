import asyncio

from agent.tools.rag.store import index_document

SAMPLE_DOCS = [
    ("Our company's internal pricing guidelines recommend positioning our product 15% below the market leader's list price, while emphasizing our superior customer support as the key differentiator.", "internal_pricing_memo.txt"),
    ("Q3 internal sales review: our enterprise tier saw 12% quarter-over-quarter growth, driven primarily by upsells from mid-market accounts rather than new logo acquisition.", "q3_sales_review.txt"),
    ("Customer feedback synthesis from Q3: the most common complaint was onboarding complexity, followed by a desire for more granular permission controls in the admin panel.", "q3_customer_feedback.txt"),
]


async def main():
    for text, source in SAMPLE_DOCS:
        await index_document(text, source)
        print(f"Indexed: {source}")


if __name__ == "__main__":
    asyncio.run(main())