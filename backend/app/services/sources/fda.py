"""openFDA drug labels — the FDA's structured drug labeling data.
https://open.fda.gov/apis/drug/label/

Not a research paper, but a drug's official indications/usage and warnings are
authoritative grounding evidence for treatment questions. We build a record per
label with the brand/generic name as title and the indications text as abstract."""

import logging

from app.services.sources.base import HTTPProvider, SourceRecord

logger = logging.getLogger(__name__)


def _first(value) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    return value


class FDAProvider(HTTPProvider):
    name = "fda"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        # Search the indications field so results are treatment-relevant.
        params = {"search": f"indications_and_usage:{query}", "limit": limit}
        resp = await self._client.get("https://api.fda.gov/drug/label.json", params=params)
        if resp.status_code == 404:
            return []  # openFDA returns 404 for zero matches
        resp.raise_for_status()
        results = resp.json().get("results", [])

        records: list[SourceRecord] = []
        for rank, r in enumerate(results):
            openfda = r.get("openfda", {})
            brand = _first(openfda.get("brand_name")) or _first(openfda.get("generic_name"))
            indications = _first(r.get("indications_and_usage"))
            if not brand or not indications:
                continue
            label_id = r.get("id") or r.get("set_id") or ""
            # Combine the most clinically useful label sections as the abstract.
            body_parts = [
                indications,
                _first(r.get("dosage_and_administration")) or "",
                _first(r.get("warnings_and_cautions")) or "",
            ]
            records.append(
                SourceRecord(
                    source=self.name,
                    title=f"FDA label: {brand}",
                    abstract="\n\n".join(p for p in body_parts if p)[:8000],
                    authors=[_first(openfda.get("manufacturer_name")) or "FDA"],
                    external_id=label_id,
                    journal="openFDA Drug Label",
                    url=(f"https://labels.fda.gov/getPackageInsert.cfm?id={label_id}"
                         if label_id else "https://open.fda.gov/"),
                    rank=rank,
                )
            )
        return records
