import cfb_ticket as ct


def test_home_favorite_with_hyphenated_abbreviation_keeps_negative_sign():
    assert ct.home_spread("M-OH -6.5", "Miami (OH) RedHawks", "M-OH", "BUFF") == -6.5


def test_away_favorite_flips_to_positive_home_spread():
    assert ct.home_spread("OHIO -12.5", "Akron Zips", "AKR", "OHIO") == 12.5


def test_even_or_missing_details_return_none():
    assert ct.home_spread("EVEN", "Akron Zips", "AKR", "OHIO") is None
    assert ct.home_spread(None, "Akron Zips", "AKR", "OHIO") is None


def test_falls_back_to_name_tokens_when_abbreviation_differs():
    assert ct.home_spread("Akron -3", "Akron Zips", "AKRN", "OHIO") == -3.0
