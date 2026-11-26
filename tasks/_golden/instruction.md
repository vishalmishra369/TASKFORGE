# Add a `click.Duration` parameter type

## Background
CLI authors often need a timeout, interval or TTL from the command line. Today they must parse
strings like `90s` or `1h30m` themselves. Add a built-in parameter type that turns such text into a
`datetime.timedelta` and can enforce a minimum and maximum.

## Requirements
1. Add a public class `click.Duration(min=None, max=None)`, importable as `click.Duration` and usable
   as `type=click.Duration()` on options and arguments. Its `name` attribute is `"duration"`.
2. A duration string is one or more `<integer><unit>` parts written without spaces. Units are `d`
   (days), `h` (hours), `m` (minutes) and `s` (seconds). Each unit may appear at most once and units
   must be written from largest to smallest, so `1d2h3m4s`, `1h30m`, `90s` and `2d` are valid.
3. Conversion returns a `datetime.timedelta` (`"1h30m"` gives `timedelta(hours=1, minutes=30)`; `"90s"`
   gives `timedelta(seconds=90)`; `"0s"` gives `timedelta(0)`).
4. If the value passed to the type is already a `timedelta`, it is accepted as-is and only checked
   against the limits.
5. `min` and `max` are `timedelta` objects or `None` (no limit). A duration equal to a limit is accepted.
6. Constructing `Duration` with `min` greater than `max` raises `ValueError("min must not be greater than max")`.

## Errors
All conversion errors raise `click.BadParameter` (via the usual `fail` mechanism). `{value!r}` is the
original input, `{limit}` is `str()` of the limit `timedelta`.
- Text that does not match the format above (including the empty string, spaces, unknown units, wrong
  unit order, repeated units, bare numbers like `"10"`):
  `{value!r} is not a valid duration. Use a combination like '1h30m' (units: d, h, m, s).`
- Shorter than `min`: `{value!r} is shorter than the minimum duration of {limit}.`
- Longer than `max`: `{value!r} is longer than the maximum duration of {limit}.`

## Examples
```python
@click.command()
@click.option("--timeout", type=click.Duration(min=timedelta(seconds=10), max=timedelta(hours=2)))
def run(timeout):
    click.echo(repr(timeout))
```
- `run --timeout 1h30m` prints `datetime.timedelta(seconds=5400)` and exits with code 0.
- `run --timeout 5s` exits with code 2 and prints
  `Error: Invalid value for '--timeout': '5s' is shorter than the minimum duration of 0:00:10.`
- `run --timeout abc` exits with code 2 and prints
  `Error: Invalid value for '--timeout': 'abc' is not a valid duration. Use a combination like '1h30m' (units: d, h, m, s).`

## Out of scope
Fractional amounts (`1.5h`), weeks/months/years, whitespace or case-insensitive units, shell
completion, and any change to existing types or their behaviour.
