from merge_review.cases.naming import institutions_match, normalized_institution


def test_institution_normalization_ignores_at() -> None:
    assert normalized_institution(
        "University of Illinois Urbana-Champaign"
    ) == normalized_institution("University of Illinois at Urbana-Champaign")
    assert normalized_institution("Research and Development Center") == (
        normalized_institution("The Research Development Center")
    )


def test_institution_matching_does_not_infer_parent_system() -> None:
    assert not institutions_match(
        "University of Illinois Urbana-Champaign",
        "University of Illinois System",
    )
    assert not institutions_match(
        "University of Illinois Urbana-Champaign",
        "Argonne National Laboratory",
    )
