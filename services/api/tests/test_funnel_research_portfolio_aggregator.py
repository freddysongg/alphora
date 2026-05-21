import uuid

from app.schemas.company_thesis import (
    CompanyCatalyst,
    CompanyRisk,
    CompanyThesis,
    CompanyThesisPublic,
)
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
)
from app.services.strategies.funnel_research.portfolio.aggregator import (
    aggregate_portfolio,
)


def _cited_claim(*, chunk_id: uuid.UUID, quote: str, source: str) -> CitedClaim:
    return CitedClaim(
        claim_text="capex acceleration",
        exact_quote=quote,
        chunk_id=chunk_id,
        source=source,
    )


def _macro_brief(cited_claims: list[CitedClaim] | None = None) -> MacroBrief:
    return MacroBrief(
        themes=[Theme(name="ai capex", evidence_ids=[uuid.uuid4()], confidence=0.7)],
        sector_calls=[],
        watch_items=[
            WatchItem(name="rate path", reason="watch", evidence_ids=[uuid.uuid4()])
        ],
        cited_claims=cited_claims or [],
        proposed_hypotheses=[],
        confidence=0.65,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _macro_judge(status: JudgeStatus = JudgeStatus.passed) -> JudgePublic:
    return JudgePublic(status=status, reasons=[], call_id=uuid.uuid4())


def _sector_public(
    *,
    sector_name: str,
    direction: SectorCallDirection,
    confidence: float,
    judge_status: JudgeStatus = JudgeStatus.passed,
    verifier_status: VerifierStatus = VerifierStatus.verified,
    cited_claims: list[CitedClaim] | None = None,
    sector_entity_id: uuid.UUID | None = None,
) -> SectorBriefPublic:
    brief = SectorBrief(
        sector_entity_id=sector_entity_id or uuid.uuid4(),
        sector_name=sector_name,
        direction=direction,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=cited_claims or [],
        confidence=confidence,
        verifier_status=verifier_status,
        regeneration_count=0,
    )
    return SectorBriefPublic(
        brief=brief,
        judge=JudgePublic(
            status=judge_status,
            reasons=[],
            call_id=uuid.uuid4() if judge_status is not JudgeStatus.not_run else None,
        ),
        chunks=[],
    )


def _company_public(
    *,
    company_name: str,
    sector_name: str,
    direction: SectorCallDirection,
    conviction: float,
    judge_status: JudgeStatus = JudgeStatus.passed,
    verifier_status: VerifierStatus = VerifierStatus.verified,
    cited_claims: list[CitedClaim] | None = None,
) -> CompanyThesisPublic:
    thesis = CompanyThesis(
        company_entity_id=uuid.uuid4(),
        company_name=company_name,
        sector_entity_id=uuid.uuid4(),
        sector_name=sector_name,
        ticker=None,
        direction=direction,
        conviction=conviction,
        bull_case="Growth is steady.",
        bear_case="Risks remain.",
        catalysts=[
            CompanyCatalyst(
                name="next earnings",
                expected_timing=None,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        risks=[
            CompanyRisk(
                name="competition",
                severity=0.3,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        cited_claims=cited_claims or [],
        confidence=conviction,
        evidence_ids=[uuid.uuid4()],
        verifier_status=verifier_status,
        regeneration_count=0,
    )
    return CompanyThesisPublic(
        thesis=thesis,
        judge=JudgePublic(
            status=judge_status,
            reasons=[],
            call_id=uuid.uuid4() if judge_status is not JudgeStatus.not_run else None,
        ),
        chunks=[],
    )


def test_aggregate_empty_inputs() -> None:
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=[],
        companies=[],
    )
    assert brief.sectors == []
    assert brief.companies == []
    assert brief.cited_claims == []
    assert brief.cited_chunk_ids == []
    assert brief.coverage.sectors_selected == 0
    assert brief.coverage.companies_selected == 0
    assert brief.macro.confidence == 0.65
    assert brief.macro.judge_status is JudgeStatus.passed


def test_aggregate_sector_ranking_non_neutral_first_then_judge_then_conviction() -> None:
    sectors = [
        _sector_public(
            sector_name="Utilities",
            direction=SectorCallDirection.neutral,
            confidence=0.95,
        ),
        _sector_public(
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.4,
            judge_status=JudgeStatus.flagged,
        ),
        _sector_public(
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            confidence=0.6,
            judge_status=JudgeStatus.passed,
        ),
        _sector_public(
            sector_name="Health Care",
            direction=SectorCallDirection.underweight,
            confidence=0.7,
            judge_status=JudgeStatus.passed,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=[],
    )
    ranked_names = [entry.sector_name for entry in brief.sectors]
    assert ranked_names == [
        "Health Care",
        "Information Technology",
        "Energy",
        "Utilities",
    ]
    assert [entry.rank for entry in brief.sectors] == [1, 2, 3, 4]


def test_aggregate_sector_tiebreak_by_name() -> None:
    sectors = [
        _sector_public(
            sector_name="Materials",
            direction=SectorCallDirection.overweight,
            confidence=0.6,
        ),
        _sector_public(
            sector_name="Consumer Staples",
            direction=SectorCallDirection.overweight,
            confidence=0.6,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=[],
    )
    assert [entry.sector_name for entry in brief.sectors] == [
        "Consumer Staples",
        "Materials",
    ]


def test_aggregate_company_ranking() -> None:
    companies = [
        _company_public(
            company_name="Beta Inc",
            sector_name="Information Technology",
            direction=SectorCallDirection.neutral,
            conviction=0.9,
        ),
        _company_public(
            company_name="Alpha Corp",
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            conviction=0.6,
            judge_status=JudgeStatus.passed,
        ),
        _company_public(
            company_name="Gamma LLC",
            sector_name="Energy",
            direction=SectorCallDirection.underweight,
            conviction=0.7,
            judge_status=JudgeStatus.passed,
        ),
        _company_public(
            company_name="Delta Co",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.7,
            judge_status=JudgeStatus.flagged,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=[],
        companies=companies,
    )
    ranked = [(entry.company_name, entry.rank) for entry in brief.companies]
    assert ranked == [
        ("Gamma LLC", 1),
        ("Alpha Corp", 2),
        ("Delta Co", 3),
        ("Beta Inc", 4),
    ]


def test_aggregate_coverage_counts() -> None:
    sectors = [
        _sector_public(
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.7,
            judge_status=JudgeStatus.passed,
        ),
        _sector_public(
            sector_name="Materials",
            direction=SectorCallDirection.neutral,
            confidence=0.5,
            judge_status=JudgeStatus.flagged,
            verifier_status=VerifierStatus.quote_unverified,
        ),
    ]
    companies = [
        _company_public(
            company_name="A",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.6,
            judge_status=JudgeStatus.passed,
        ),
        _company_public(
            company_name="B",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.5,
            judge_status=JudgeStatus.flagged,
            verifier_status=VerifierStatus.quote_unverified,
        ),
        _company_public(
            company_name="C",
            sector_name="Materials",
            direction=SectorCallDirection.neutral,
            conviction=0.4,
            judge_status=JudgeStatus.not_run,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=companies,
    )
    coverage = brief.coverage
    assert coverage.sectors_selected == 2
    assert coverage.sectors_verified == 1
    assert coverage.sectors_judge_passed == 1
    assert coverage.sectors_judge_flagged == 1
    assert coverage.companies_selected == 3
    assert coverage.companies_verified == 2
    assert coverage.companies_judge_passed == 1
    assert coverage.companies_judge_flagged == 1


def test_aggregate_cited_claims_dedup_and_chunk_ids() -> None:
    shared_chunk = uuid.uuid4()
    macro_claim = _cited_claim(
        chunk_id=shared_chunk, quote="shared quote A", source="macro_src"
    )
    sector_dup = _cited_claim(
        chunk_id=shared_chunk, quote="shared quote A", source="sector_src"
    )
    sector_distinct_quote = _cited_claim(
        chunk_id=shared_chunk, quote="distinct quote", source="sector_src"
    )
    company_other_chunk = _cited_claim(
        chunk_id=uuid.uuid4(), quote="company quote", source="company_src"
    )

    macro = _macro_brief(cited_claims=[macro_claim])
    sectors = [
        _sector_public(
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.6,
            cited_claims=[sector_dup, sector_distinct_quote],
        )
    ]
    companies = [
        _company_public(
            company_name="A",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.5,
            cited_claims=[company_other_chunk],
        )
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=macro,
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=companies,
    )
    assert len(brief.cited_claims) == 3
    quotes = [claim.exact_quote for claim in brief.cited_claims]
    assert quotes == ["shared quote A", "distinct quote", "company quote"]
    assert brief.cited_chunk_ids == [shared_chunk, company_other_chunk.chunk_id]


def test_aggregate_macro_summary_passes_through() -> None:
    macro = _macro_brief()
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=macro,
        macro_judge=_macro_judge(JudgeStatus.flagged),
        sectors=[],
        companies=[],
    )
    assert brief.macro.themes == list(macro.themes)
    assert brief.macro.watch_items == list(macro.watch_items)
    assert brief.macro.confidence == macro.confidence
    assert brief.macro.judge_status is JudgeStatus.flagged


def test_aggregate_run_id_preserved() -> None:
    run_id = uuid.uuid4()
    brief = aggregate_portfolio(
        run_id=run_id,
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=[],
        companies=[],
    )
    assert brief.run_id == run_id
    assert brief.verifier_status is VerifierStatus.verified
    assert brief.regeneration_count == 0


def _unverified_macro() -> MacroBrief:
    return MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.4,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.quote_unverified,
        regeneration_count=2,
    )


def test_aggregate_verifier_status_degrades_when_macro_unverified() -> None:
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_unverified_macro(),
        macro_judge=_macro_judge(JudgeStatus.flagged),
        sectors=[],
        companies=[],
    )
    assert brief.verifier_status is VerifierStatus.quote_unverified


def test_aggregate_verifier_status_degrades_when_any_sector_unverified() -> None:
    sectors = [
        _sector_public(
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.7,
        ),
        _sector_public(
            sector_name="Materials",
            direction=SectorCallDirection.overweight,
            confidence=0.5,
            verifier_status=VerifierStatus.quote_unverified,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=[],
    )
    assert brief.verifier_status is VerifierStatus.quote_unverified


def test_aggregate_verifier_status_degrades_when_any_company_unverified() -> None:
    companies = [
        _company_public(
            company_name="A",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.6,
            verifier_status=VerifierStatus.quote_unverified,
        ),
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=[],
        companies=companies,
    )
    assert brief.verifier_status is VerifierStatus.quote_unverified


def test_aggregate_verifier_status_stays_verified_when_all_upstream_verified() -> None:
    sectors = [
        _sector_public(
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.7,
        )
    ]
    companies = [
        _company_public(
            company_name="A",
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            conviction=0.6,
        )
    ]
    brief = aggregate_portfolio(
        run_id=uuid.uuid4(),
        macro=_macro_brief(),
        macro_judge=_macro_judge(),
        sectors=sectors,
        companies=companies,
    )
    assert brief.verifier_status is VerifierStatus.verified
