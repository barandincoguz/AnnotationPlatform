"""Golden bucket cases for the vendored router + discrepancy alignment."""
from backend.quality.adapter import (
    AUDIT_POLICY_ID,
    audit_references,
    canonical_tuple,
    reference_identities,
)

DOC_TEXT = (
    "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. "
    "Gelir Vergisi Kanunu'nun 94 uncu maddesi tevkifat esaslarini belirler."
)


def ref(kanun_no="213", kanun_ad="Vergi Usul Kanunu", madde="114", fikra="", bent="",
        source_text="zamanasimi hukmu duzenlenmistir"):
    return {
        "kanun_no": kanun_no, "kanun_ad": kanun_ad, "madde": madde,
        "fikra": fikra, "bent": bent, "source_text": source_text,
    }


def test_case_1_identical_sets_are_green():
    outcome = audit_references(
        human_references=[ref()], model_references=[ref()], document_text=DOC_TEXT
    )
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()
    assert outcome.similarity == 1.0


def test_case_2_normalization_only_difference_is_green():
    outcome = audit_references(
        human_references=[ref(kanun_ad="VUK", madde="114.")],
        model_references=[ref(kanun_ad="Vergi Usul Kanunu", madde="114")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()


def test_compound_model_madde_matches_split_human_bent():
    """MLX may emit ``13/b`` while the annotation API stores ``13`` + ``b``.

    These are the same legal reference and must not create a false RED audit.
    """
    outcome = audit_references(
        human_references=[ref(madde="13", bent="b")],
        model_references=[ref(madde="13/b", bent="")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"
    assert outcome.similarity == 1.0
    assert outcome.discrepancies == ()


def test_compound_model_madde_matches_split_human_fikra_and_bent():
    outcome = audit_references(
        human_references=[ref(madde="16", fikra="1", bent="a")],
        model_references=[ref(madde="16/1-a", fikra="", bent="")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"
    assert outcome.similarity == 1.0
    assert outcome.discrepancies == ()


def test_compound_model_madde_with_conflicting_explicit_bent_fails_closed():
    outcome = audit_references(
        human_references=[ref(madde="13", bent="b")],
        model_references=[ref(madde="13/b", bent="c")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert outcome.discrepancies


def test_case_3_extension_mismatch_is_yellow_detail():
    outcome = audit_references(
        human_references=[ref(fikra="1")],
        model_references=[ref(fikra="2")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("extension_mismatch",)
    assert [d["kind"] for d in outcome.discrepancies] == ["detail_mismatch"]
    assert outcome.discrepancies[0]["human_reference"]["fikra"] == "1"
    assert outcome.discrepancies[0]["model_reference"]["fikra"] == "2"
    assert outcome.discrepancies[0]["field_diffs"] == ["fikra"]
    # Side-exclusive: both sides cited kanun_no 213 / madde 114, only fikra
    # differs, so each list carries exactly the fikra its own side asserted.
    assert outcome.human_only == ({"kanun_no": "213", "madde": "114", "fikra": "1", "bent": ""},)
    assert outcome.model_only == ({"kanun_no": "213", "madde": "114", "fikra": "2", "bent": ""},)


def test_case_4_evidence_mismatch_is_yellow():
    outcome = audit_references(
        human_references=[ref(source_text="zamanasimi hukmu duzenlenmistir")],
        model_references=[ref(source_text="tevkifat esaslarini belirler")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("evidence_mismatch",)
    assert outcome.discrepancies[0]["field_diffs"] == ["source_text"]
    # Both sides cited the same identity (kanun_no/madde/fikra/bent) and only
    # the quote differs, so the exclusive sets must both be empty: recording
    # the shared identity in either list would be a group dump, not a diff.
    assert outcome.human_only == ()
    assert outcome.model_only == ()


def test_case_5_human_only_core_is_red_and_not_actionable():
    outcome = audit_references(
        human_references=[ref(), ref(kanun_no="193", kanun_ad="Gelir Vergisi Kanunu", madde="94")],
        model_references=[ref()],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert "missing_core_reference" in outcome.reasons
    kinds = [d["kind"] for d in outcome.discrepancies]
    assert kinds == ["human_only"]
    assert outcome.human_only == ({"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""},)
    assert outcome.model_only == ()


def test_case_6_model_only_core_is_red_and_actionable():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[ref(), ref(kanun_no="193", kanun_ad="Gelir Vergisi Kanunu", madde="94",
                                    source_text="tevkifat esaslarini belirler")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert "extra_or_different_core_reference" in outcome.reasons
    (discrepancy,) = outcome.discrepancies
    assert discrepancy["kind"] == "model_only"
    assert discrepancy["madde"] == "94"
    assert discrepancy["model_reference"]["source_text"] == "tevkifat esaslarini belirler"
    assert discrepancy["match_mode"] == "normalized_exact"
    assert outcome.model_only == ({"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""},)
    assert outcome.human_only == ()


def test_case_7_conflicting_law_identity_is_red():
    # The vendored router looks for a law-number/name contradiction WITHIN one
    # candidate's own list, never across human vs model, so the conflict has to
    # live on one side: 213 appears as both VUK and GVK in the human list.
    outcome = audit_references(
        human_references=[ref(), ref(kanun_ad="Gelir Vergisi Kanunu", madde="94")],
        model_references=[ref()],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert outcome.reasons == ("conflicting_law_identity",)
    assert [d["kind"] for d in outcome.discrepancies] == ["human_only"]
    assert outcome.human_only == ({"kanun_no": "213", "madde": "94", "fikra": "", "bent": ""},)
    assert outcome.model_only == ()


def test_case_8_model_error_is_quarantine():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[],
        document_text=DOC_TEXT,
        model_status="error",
    )
    assert outcome.bucket == "QUARANTINE"
    assert "model_processing_error" in outcome.reasons
    # The router still aligns human vs. (empty) model even though the
    # document is quarantined, so the audit-log writer has real rows to
    # persist for a document the model never processed: the single human
    # reference reports as "human_only", nothing is "model_only", and there
    # is no model reference to compute a match_mode from.
    assert [d["kind"] for d in outcome.discrepancies] == ["human_only"]
    assert outcome.discrepancies[0]["model_reference"] is None
    assert outcome.discrepancies[0]["match_mode"] is None
    assert outcome.human_only == ({"kanun_no": "213", "madde": "114", "fikra": "", "bent": ""},)
    assert outcome.model_only == ()


def test_case_9_vuk_413_boilerplate_is_filtered_by_policy():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[
            ref(),
            ref(madde="413", source_text="Mukellefler Maliye Bakanligindan izahat isteyebilir"),
        ],
        document_text=DOC_TEXT,
    )
    assert AUDIT_POLICY_ID == "ignore_vuk_213_article_413_v1"
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()


def test_case_10_multi_reference_core_group_is_side_exclusive():
    # One core group (same kanun_no/madde) with two references per side:
    # human cites fikra {1, 2}, model cites fikra {2, 3}. Fikra 2 was cited
    # by both sides and must not appear in either exclusive list; only the
    # fikra each side asserted alone should surface.
    outcome = audit_references(
        human_references=[ref(fikra="1"), ref(fikra="2")],
        model_references=[ref(fikra="2"), ref(fikra="3")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("extension_mismatch",)
    assert [d["kind"] for d in outcome.discrepancies] == ["detail_mismatch"]
    assert outcome.discrepancies[0]["human_reference"]["fikra"] == "1"
    assert outcome.discrepancies[0]["model_reference"]["fikra"] == "3"
    assert outcome.discrepancies[0]["field_diffs"] == ["fikra"]
    assert outcome.human_only == ({"kanun_no": "213", "madde": "114", "fikra": "1", "bent": ""},)
    assert outcome.model_only == ({"kanun_no": "213", "madde": "114", "fikra": "3", "bent": ""},)


def test_case_11_aliased_law_name_exclusivity_is_document_level_not_per_group():
    # kanun_no 6102 cited once per side, agreeing on kanun_no/madde/fikra/bent
    # but spelled differently ("Turk Ticaret Kanunu" vs "TTK"). LAW_NAME_ALIASES
    # only maps eight laws and 6102 is not one of them, so the two spellings
    # normalize to different kanun_ad strings, which makes core_identity (and
    # therefore the ab_diff grouping) differ even though canonical_tuple
    # (kanun_no/madde/fikra/bent only) is identical on both sides. The router
    # genuinely sees this as two different core identities -> RED, and the
    # annotator must still see both rows -- but the exclusive lists must
    # recognize the two sides agree on the article and stay empty, rather
    # than recording the same canonical tuple as exclusive to both sides.
    outcome = audit_references(
        human_references=[
            ref(kanun_no="6102", kanun_ad="Turk Ticaret Kanunu", madde="376")
        ],
        model_references=[ref(kanun_no="6102", kanun_ad="TTK", madde="376")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert "missing_core_reference" in outcome.reasons
    assert "extra_or_different_core_reference" in outcome.reasons
    assert sorted(d["kind"] for d in outcome.discrepancies) == ["human_only", "model_only"]
    assert outcome.model_only == ()
    assert outcome.human_only == ()


def test_case_12_field_diffs_excludes_evidence_compatible_source_text():
    # fikra genuinely differs (1 vs 2), but the two source_text quotes are
    # evidence-compatible under the router's own _evidence_compatible rule
    # (one loosely contains the other), so field_diffs must report only
    # "fikra" -- reporting "source_text" here would contradict a router that
    # treats this exact quote pair as compatible evidence elsewhere.
    outcome = audit_references(
        human_references=[ref(fikra="1", source_text="zamanasimi hukmu")],
        model_references=[
            ref(fikra="2", source_text="zamanasimi hukmu duzenlenmistir")
        ],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert [d["kind"] for d in outcome.discrepancies] == ["detail_mismatch"]
    assert outcome.discrepancies[0]["field_diffs"] == ["fikra"]
    assert outcome.human_only == ({"kanun_no": "213", "madde": "114", "fikra": "1", "bent": ""},)
    assert outcome.model_only == ({"kanun_no": "213", "madde": "114", "fikra": "2", "bent": ""},)


def test_quote_not_present_in_document_reports_no_match_mode():
    outcome = audit_references(
        human_references=[],
        model_references=[ref(source_text="bu cumle dokumanda hic yok")],
        document_text=DOC_TEXT,
    )
    assert outcome.discrepancies[0]["match_mode"] is None


def test_canonical_tuple_shape_is_json_each_friendly():
    assert canonical_tuple(
        {"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
         "fikra": "1", "bent": "a", "source_text": "x"}
    ) == {"kanun_no": "213", "madde": "114", "fikra": "1", "bent": "a"}


def test_reference_identities_tolerates_none_fields():
    identities = reference_identities([
        {"kanun_no": "213", "kanun_ad": None, "madde": "114",
         "fikra": None, "bent": None, "source_text": "x"}
    ])
    assert len(identities) == 1


def test_reference_identities_applies_reference_policy():
    # A VUK 213/madde 413 boilerplate reference is filtered by the same
    # AUDIT_POLICY_ID that audit_references uses, so a caller comparing raw
    # identity sets never sees it — while a normal reference still appears.
    identities = reference_identities([ref(), ref(madde="413")])
    assert len(identities) == 1
    assert all(identity[3] != "413" for identity in identities)


def test_reference_identities_compacts_law_level_reference_like_the_router():
    # route_document's pipeline is policy -> compact. A law-level reference
    # (empty madde) for the same law as a specific-article reference is
    # compaction noise that compact_references drops; reference_identities
    # must mirror that exactly, or a later "did the human accept the model's
    # reference" comparison would see an identity audit_references itself
    # ignores.
    identities = reference_identities([ref(), ref(madde="")])
    assert len(identities) == 1
    (identity,) = identities
    assert identity[3] == "114"


def test_router_compatible_evidence_stays_green_without_discrepancy_rows():
    """The diff must never contradict the bucket.

    The router treats a quote pair as compatible when one loosely contains the
    other (`normalized_five_field_set_equal` + `evidence_format_or_length_only`
    → GREEN). Deciding "same" on strict source_text equality would emit a
    detail_mismatch row for that consensus and write both identities into the
    audit log's model_only/human_only columns.
    """
    outcome = audit_references(
        human_references=[ref(source_text="zamanasimi hukmu")],
        model_references=[ref(source_text="zamanasimi hukmu duzenlenmistir")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()
    assert outcome.model_only == ()
    assert outcome.human_only == ()
