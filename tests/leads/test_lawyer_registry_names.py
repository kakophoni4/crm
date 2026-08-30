from app.modules.lawyer_registry.xlsx import director_name_key


def test_director_name_key_collapses_spaces_and_yo() -> None:
    assert director_name_key("Сизова  Светлана\tАлександровна") == (
        "сизова светлана александровна"
    )
    assert director_name_key("Сизёва Светлана Александровна") == (
        "сизева светлана александровна"
    )
