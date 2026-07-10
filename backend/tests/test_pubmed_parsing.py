"""Unit tests for PubMed XML parsing — no network.

The parser is the riskiest part of the client: PubMed XML is ragged (structured
vs. flat abstracts, missing dates, collective authors, dead records). We pin
that behavior with a representative fixture.
"""

from datetime import date

from app.services.pubmed import PubMedClient

SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>35113657</PMID>
      <Article>
        <Journal><Title>Nature Medicine</Title>
          <JournalIssue><PubDate><Year>2023</Year><Month>Mar</Month><Day>15</Day></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Lecanemab in Early Alzheimer's Disease</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Amyloid beta accumulates.</AbstractText>
          <AbstractText Label="RESULTS">Lecanemab reduced markers.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>van Dyck</LastName><Initials>CH</Initials></Author>
          <Author><CollectiveName>Clarity AD Investigators</CollectiveName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>99999999</PMID>
      <Article>
        <Journal><Title>Ghost Journal</Title>
          <JournalIssue><PubDate><MedlineDate>2021 Spring</MedlineDate></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Flat abstract paper</ArticleTitle>
        <Abstract><AbstractText>A single unlabeled abstract paragraph.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11111111</PMID>
      <Article><Journal><Title>Empty</Title></Journal><ArticleTitle></ArticleTitle></Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_parses_structured_abstract_and_authors() -> None:
    papers = PubMedClient._parse_articles(SAMPLE_XML)
    # Dead record (empty title) is dropped -> 2, not 3.
    assert len(papers) == 2

    p = papers[0]
    assert p.pmid == "35113657"
    assert p.title == "Lecanemab in Early Alzheimer's Disease"
    assert p.journal == "Nature Medicine"
    assert p.publication_date == date(2023, 3, 15)
    assert p.authors == ["van Dyck CH", "Clarity AD Investigators"]
    assert "BACKGROUND: Amyloid beta accumulates." in p.abstract
    assert "RESULTS: Lecanemab reduced markers." in p.abstract


def test_medline_date_fallback_and_flat_abstract() -> None:
    papers = PubMedClient._parse_articles(SAMPLE_XML)
    p = papers[1]
    assert p.pmid == "99999999"
    # MedlineDate "2021 Spring" -> year only, month/day default to 1.
    assert p.publication_date == date(2021, 1, 1)
    assert p.abstract == "A single unlabeled abstract paragraph."
    assert p.authors == []
