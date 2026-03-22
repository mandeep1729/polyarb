from app.matching.text import preprocess


def test_shut_down_replaced_in_politics():
    result = preprocess("Will the government shut down in March", category="politics")
    assert "shutdown" in result
    assert "shut" not in result.split() or "down" not in result.split()


def test_shut_down_not_replaced_without_politics():
    result = preprocess("Will the government shut down in March")
    # Without politics category, "shut down" stays as separate tokens
    assert "shut" in result.split()


def test_shut_down_not_replaced_for_other_category():
    result = preprocess("Will the government shut down in March", category="economics")
    assert "shut" in result.split()


def test_shut_down_replaced_case_insensitive():
    result = preprocess("Government Shut Down deadline", category="politics")
    assert "shutdown" in result


def test_shutdown_already_one_word():
    result = preprocess("government shutdown deadline", category="politics")
    assert "shutdown" in result
