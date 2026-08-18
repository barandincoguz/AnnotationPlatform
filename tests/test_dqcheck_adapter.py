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


def test_case_3_extension_mismatch_is_yellow_detail():
    outcome = audit_references(
        human_references=[ref(fikra="1")],
        model_references=[ref(fikra="2")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("extension_mismatch",)
    assert [d["kind"] for d in outcome.discrepancies] == ["detail_mismatch"]
    assert outcome.discrepancies[0]["field_diffs"] == ["fikra"]


def test_case_4_evidence_mismatch_is_yellow():
    outcome = audit_references(
        human_references=[ref(source_text="zamanasimi hukmu duzenlenmistir")],
        model_references=[ref(source_text="tevkifat esaslarini belirler")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("evidence_mismatch",)
    assert outcome.discrepancies[0]["field_diffs"] == ["source_text"]


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


def test_case_8_model_error_is_quarantine():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[],
        document_text=DOC_TEXT,
        model_status="error",
    )
    assert outcome.bucket == "QUARANTINE"
    assert "model_processing_error" in outcome.reasons


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
