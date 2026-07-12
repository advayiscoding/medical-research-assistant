"""Builds the set of source providers for a federated search.

One shared httpx.AsyncClient is reused across all HTTP providers (connection
pooling), and one PubMedClient is shared by the two NCBI providers (PubMed, PMC)
so they respect NCBI's combined per-IP rate limit. The list here IS the set of
sources the app federates over — add a provider, add a line."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.core.config import Settings
from app.services.pubmed import PubMedClient
from app.services.sources.arxiv import ArxivProvider
from app.services.sources.base import SourceProvider
from app.services.sources.clinicaltrials import ClinicalTrialsProvider
from app.services.sources.crossref import CrossrefProvider
from app.services.sources.europepmc import (
    BioRxivProvider,
    EuropePMCProvider,
    MedRxivProvider,
)
from app.services.sources.fda import FDAProvider
from app.services.sources.openalex import OpenAlexProvider
from app.services.sources.pmc import PMCProvider
from app.services.sources.pubmed_src import PubMedProvider


@asynccontextmanager
async def build_providers(settings: Settings) -> AsyncIterator[list[SourceProvider]]:
    """Yield all ten providers wired to shared clients; closes them on exit."""
    email = settings.pubmed_email or ""
    # No custom User-Agent: politeness for OpenAlex/Crossref/NCBI is conveyed via
    # the mailto/email query params, and ClinicalTrials.gov's WAF returns 403 for
    # non-default UAs (verified) — so we keep httpx's default UA.
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as http:
        pubmed_client = PubMedClient(settings, client=http)
        providers: list[SourceProvider] = [
            PubMedProvider(pubmed_client),
            PMCProvider(pubmed_client),
            OpenAlexProvider(http, email),
            ClinicalTrialsProvider(http, email),
            EuropePMCProvider(http, email),
            CrossrefProvider(http, email),
            ArxivProvider(http, email),
            BioRxivProvider(http, email),
            MedRxivProvider(http, email),
            FDAProvider(http, email),
        ]
        yield providers
