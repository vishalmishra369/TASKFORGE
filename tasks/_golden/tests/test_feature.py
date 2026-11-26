from datetime import timedelta

import click
import pytest
from click.testing import CliRunner


def _convert(value, **kw):
    return click.Duration(**kw).convert(value, None, None)


def test_exported_and_name():
    assert click.Duration().name == "duration"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("90s", timedelta(seconds=90)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        ("2d", timedelta(days=2)),
        ("1d2h3m4s", timedelta(days=1, hours=2, minutes=3, seconds=4)),
        ("0s", timedelta(0)),
    ],
)
def test_valid_formats(text, expected):
    assert _convert(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "10", "1.5h", "1 h", "1x", "1m1h", "1h1h"])
def test_invalid_formats(text):
    with pytest.raises(click.BadParameter) as e:
        _convert(text)
    assert e.value.message == (
        f"{text!r} is not a valid duration. Use a combination like '1h30m' (units: d, h, m, s)."
    )


def test_timedelta_passthrough():
    td = timedelta(minutes=5)
    assert _convert(td) == td


def test_timedelta_checked_against_limits():
    with pytest.raises(click.BadParameter):
        _convert(timedelta(seconds=1), min=timedelta(seconds=5))


def test_min_boundary_accepted_and_below_rejected():
    assert _convert("10s", min=timedelta(seconds=10)) == timedelta(seconds=10)
    with pytest.raises(click.BadParameter) as e:
        _convert("9s", min=timedelta(seconds=10))
    assert e.value.message == "'9s' is shorter than the minimum duration of 0:00:10."


def test_max_boundary_accepted_and_above_rejected():
    assert _convert("2h", max=timedelta(hours=2)) == timedelta(hours=2)
    with pytest.raises(click.BadParameter) as e:
        _convert("2h1s", max=timedelta(hours=2))
    assert e.value.message == "'2h1s' is longer than the maximum duration of 2:00:00."


def test_min_greater_than_max_raises():
    with pytest.raises(ValueError) as e:
        click.Duration(min=timedelta(hours=2), max=timedelta(hours=1))
    assert str(e.value) == "min must not be greater than max"


def _cmd():
    @click.command()
    @click.option("--timeout", type=click.Duration(min=timedelta(seconds=10), max=timedelta(hours=2)))
    def run(timeout):
        click.echo(repr(timeout))

    return run


def test_cli_success():
    r = CliRunner().invoke(_cmd(), ["--timeout", "1h30m"])
    assert r.exit_code == 0
    assert r.output.strip() == "datetime.timedelta(seconds=5400)"


def test_cli_too_short():
    r = CliRunner().invoke(_cmd(), ["--timeout", "5s"])
    assert r.exit_code == 2
    assert "Error: Invalid value for '--timeout': '5s' is shorter than the minimum duration of 0:00:10." in r.output


def test_cli_invalid():
    r = CliRunner().invoke(_cmd(), ["--timeout", "abc"])
    assert r.exit_code == 2
    assert (
        "Error: Invalid value for '--timeout': 'abc' is not a valid duration. "
        "Use a combination like '1h30m' (units: d, h, m, s)." in r.output
    )


def test_usable_as_argument():
    @click.command()
    @click.argument("wait", type=click.Duration())
    def run(wait):
        click.echo(str(wait))

    r = CliRunner().invoke(run, ["1d"])
    assert r.exit_code == 0
    assert r.output.strip() == "1 day, 0:00:00"
