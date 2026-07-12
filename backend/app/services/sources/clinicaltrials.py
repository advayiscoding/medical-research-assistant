"""ClinicalTrials.gov — the registry of clinical studies. API v2 (JSON).
https://clinicaltrials.gov/data-api/api

A trial isn't a paper, but its brief summary is high-value grounding evidence
about what is actually being tested in humans. We map the NCT id as the record
identity and the brief summary as the abstract."""

import logging

from app.services.sources.base import HTTPProvider, SourceRecord, parse_iso_date

logger = logging.getLogger(__name__)


class ClinicalTrialsProvider(HTTPProvider):
    name = "clinicaltrials"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        params = {"query.term": query, "pageSize": limit}
        resp = await self._client.get(
            "https://clinicaltrials.gov/api/v2/studies", params=params
        )
        resp.raise_for_status()
        studies = resp.json().get("studies", [])

        records: list[SourceRecord] = []
        for rank, study in enumerate(studies):
            ps = study.get("protocolSection", {})
            ident = ps.get("identificationModule", {})
            desc = ps.get("descriptionModule", {})
            status = ps.get("statusModule", {})
            sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
            nct = ident.get("nctId")
            if not nct:
                continue
            title = ident.get("officialTitle") or ident.get("briefTitle") or ""
            records.append(
                SourceRecord(
                    source=self.name,
                    title=title,
                    abstract=desc.get("briefSummary") or desc.get("detailedDescription"),
                    authors=[sponsor["name"]] if sponsor.get("name") else [],
                    external_id=nct,
                    journal="ClinicalTrials.gov",
                    publication_date=parse_iso_date(
                        (status.get("startDateStruct") or {}).get("date")
                    ),
                    url=f"https://clinicaltrials.gov/study/{nct}",
                    rank=rank,
                )
            )
        return [r for r in records if r.title]
