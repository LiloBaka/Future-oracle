from app.services.evaluation import calculate_evaluation


def test_correct_rain_evaluation():
    result = calculate_evaluation(72.0, "rain", 1.4)
    assert result.actual_rain is True
    assert result.status == "correct"
    assert result.absolute_probability_error == 0.28
    assert result.brier_score == 0.0784


def test_incorrect_no_rain_evaluation():
    result = calculate_evaluation(35.0, "no_rain", 0.4)
    assert result.actual_rain is True
    assert result.status == "incorrect"
    assert result.absolute_probability_error == 0.65
    assert result.brier_score == 0.4225
