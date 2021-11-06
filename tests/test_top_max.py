from copy import copy

import pytest

from kks.ejudge import Deadlines, ProblemInfo, StandingsRow, Status, TaskScore
from kks.cmd.top import recalc_task_score


class FrozenProblemInfo(ProblemInfo):
    def __init__(self, past_deadline, full_score, run_penalty, current_penalty):
        super().__init__(full_score, run_penalty, current_penalty, Deadlines(None, None))
        self._past_deadline = past_deadline

    def past_deadline(self):
        return self._past_deadline


def contest_name(is_kr):
    return 'kr123' if is_kr else 'sm123'


# ---------- SCORE GENERATORS ----------


def score_ok():
    return TaskScore(contest_name(False), '100', Status.OK)


def score_review():
    return TaskScore(contest_name(False), '100', Status.REVIEW)


def score_partial():
    return TaskScore(contest_name(False), '0', Status.PARTIAL)


def score_testing(has_partial=False, is_kr=False):
    return TaskScore(contest_name(is_kr), '0' if has_partial else None, Status.TESTING)


def score_rejected(has_partial=False):
    return TaskScore(contest_name(False), '0' if has_partial else None, Status.REJECTED)


def score_not_submitted(is_kr=False):
    return TaskScore(contest_name(is_kr), None, Status.NOT_SUBMITTED)


# ---------- PROBLEM INFO GENERATORS ----------


def problem_past_deadline(full_score=100, run_penalty=10, current_penalty=100):
    return FrozenProblemInfo(True, full_score, run_penalty, current_penalty)


def normal_problem(full_score=100, run_penalty=10, current_penalty=50):
    return FrozenProblemInfo(False, full_score, run_penalty, current_penalty)


# ---------- TESTING ----------


class BaseRecalcTest:
    @pytest.fixture(autouse=True)
    def create_row(self):
        self._row = StandingsRow(1, 'user', [], 0, 0, False)

    def recalc_task_score(self, task_score, problem_info):
        recalc_task_score(self._row, task_score, problem_info)

    def assert_unchanged(self, task_score, problem_info):
        orig_score = copy(task_score)
        self.recalc_task_score(task_score, problem_info)
        assert orig_score.score == task_score.score
        assert orig_score.status == task_score.status

    def assert_updated(self, task_score, problem_info, expected_score):
        self.recalc_task_score(task_score, problem_info)
        assert task_score.score == str(expected_score)
        assert task_score.status == Status.REVIEW


class TestNormal(BaseRecalcTest):
    # Status.TESTING and past_deadline() - should never happen

    @pytest.mark.parametrize('problem_info_gen', [problem_past_deadline, normal_problem])
    @pytest.mark.parametrize('task_score_gen', [score_ok, score_review])
    def test_solved(self, problem_info_gen, task_score_gen):
        """already solved - shouldn't recalculate"""
        self.assert_unchanged(task_score_gen(), problem_info_gen())

    @pytest.mark.parametrize('task_score_gen', [score_partial, score_not_submitted])
    def test_frozen(self, task_score_gen):
        """will never be solved - shouldn't recalculate"""
        self.assert_unchanged(task_score_gen(), problem_past_deadline())

    def test_partial(self):
        task_score = score_partial()
        problem_info = normal_problem(full_score=100, run_penalty=10, current_penalty=50)
        self.assert_updated(task_score, problem_info, 40)

    def test_not_submitted(self):
        task_score = score_not_submitted()
        problem_info = normal_problem(full_score=100, current_penalty=50)
        self.assert_updated(task_score, problem_info, 50)

    @pytest.mark.parametrize('has_partial', [False, True])
    def test_testing(self, has_partial):
        task_score = score_testing(has_partial)
        problem_info = normal_problem(full_score=100, run_penalty=10, current_penalty=50)
        if has_partial:
            self.assert_updated(task_score, problem_info, 40)
        else:
            self.assert_updated(task_score, problem_info, 50)

    @pytest.mark.parametrize('problem_info_gen', [problem_past_deadline, normal_problem])
    @pytest.mark.parametrize('has_partial', [False, True])
    def test_rejected(self, problem_info_gen, has_partial):
        task_score = score_rejected(has_partial)
        problem_info = problem_info_gen(full_score=100, run_penalty=10)
        if has_partial:
            self.assert_updated(task_score, problem_info, 90)
        else:
            self.assert_updated(task_score, problem_info, 100)

    @pytest.mark.parametrize('task_score_gen', [score_partial, score_not_submitted])
    def test_min_score(self, task_score_gen):
        task_score = task_score_gen()
        problem_info = normal_problem(full_score=100, run_penalty=10, current_penalty=300)
        self.assert_updated(task_score, problem_info, 20)


class TestKr(BaseRecalcTest):
    class MockConfig:
        class options:
            max_kr = None

    @pytest.fixture(autouse=True)
    def mock_config(self, monkeypatch):
        monkeypatch.setattr('kks.cmd.top.Config', TestKr.MockConfig)

    def test_testing_maxkr(self):
        TestKr.MockConfig.options.max_kr = True
        task_score = score_testing(is_kr=True)
        self.assert_updated(task_score, problem_past_deadline(), 200)

    def test_testing_nomaxkr(self):
        TestKr.MockConfig.options.max_kr = False
        task_score = score_testing(is_kr=True)
        self.assert_unchanged(task_score, problem_past_deadline())

    @pytest.mark.parametrize('max_kr', [True, False])
    @pytest.mark.parametrize('task_score_gen', [score_testing, score_not_submitted])
    def test_running_kr(self, max_kr, task_score_gen):
        TestKr.MockConfig.options.max_kr = max_kr
        task_score = task_score_gen(is_kr=True)
        self.assert_unchanged(task_score, normal_problem())
