"""
Result type for explicit error handling.

Provides a Result[T, E] type inspired by Rust's Result, enabling
explicit error handling without exceptions for expected error cases.
"""

from dataclasses import dataclass
from typing import TypeVar, Generic, Optional, Callable, Union

T = TypeVar("T")  # Success value type
E = TypeVar("E")  # Error value type
U = TypeVar("U")  # Mapped success type


@dataclass(frozen=True)
class Ok(Generic[T]):
    """
    Represents a successful result containing a value.

    Usage:
        result = Ok(42)
        if result.is_ok():
            print(result.value)  # 42
    """

    value: T

    def is_ok(self) -> bool:
        """Returns True if this is an Ok result."""
        return True

    def is_err(self) -> bool:
        """Returns False since this is an Ok result."""
        return False

    def unwrap(self) -> T:
        """Returns the contained value."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Returns the contained value (ignores default)."""
        return self.value

    def unwrap_or_else(self, f: Callable[[], T]) -> T:
        """Returns the contained value (ignores callable)."""
        return self.value

    def map(self, f: Callable[[T], U]) -> "Ok[U]":
        """Maps Ok value using the provided function."""
        return Ok(f(self.value))

    def map_err(self, f: Callable) -> "Ok[T]":
        """Returns self unchanged since there's no error to map."""
        return self

    def and_then(self, f: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        """Chains another result-returning operation."""
        return f(self.value)

    def or_else(self, f: Callable) -> "Ok[T]":
        """Returns self unchanged since there's no error."""
        return self

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True)
class Err(Generic[E]):
    """
    Represents a failed result containing an error.

    Usage:
        result = Err("something went wrong")
        if result.is_err():
            print(result.error)  # "something went wrong"
    """

    error: E

    def is_ok(self) -> bool:
        """Returns False since this is an Err result."""
        return False

    def is_err(self) -> bool:
        """Returns True if this is an Err result."""
        return True

    def unwrap(self) -> None:
        """Raises ValueError since this is an Err result."""
        raise ValueError(f"Called unwrap on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        """Returns the default value."""
        return default

    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        """Returns the result of calling f with the error."""
        return f(self.error)

    def map(self, f: Callable) -> "Err[E]":
        """Returns self unchanged since there's no value to map."""
        return self

    def map_err(self, f: Callable[[E], U]) -> "Err[U]":
        """Maps the error using the provided function."""
        return Err(f(self.error))

    def and_then(self, f: Callable) -> "Err[E]":
        """Returns self unchanged since there's no value to chain."""
        return self

    def or_else(self, f: Callable[[E], "Result[T, U]"]) -> "Result[T, U]":
        """Chains another result-returning operation on the error."""
        return f(self.error)

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# Type alias for the Result union type
Result = Union[Ok[T], Err[E]]


def is_ok(result: Result[T, E]) -> bool:
    """Check if a result is Ok."""
    return isinstance(result, Ok)


def is_err(result: Result[T, E]) -> bool:
    """Check if a result is Err."""
    return isinstance(result, Err)


def unwrap(result: Result[T, E]) -> T:
    """Unwrap a result, raising if Err."""
    return result.unwrap()


def unwrap_or(result: Result[T, E], default: T) -> T:
    """Unwrap a result or return default."""
    return result.unwrap_or(default)


# Utility functions for working with Results


def collect_results(results: list[Result[T, E]]) -> Result[list[T], E]:
    """
    Collect a list of Results into a Result of a list.

    If any result is Err, returns that Err.
    If all results are Ok, returns Ok with list of values.

    Example:
        results = [Ok(1), Ok(2), Ok(3)]
        collected = collect_results(results)  # Ok([1, 2, 3])

        results = [Ok(1), Err("failed"), Ok(3)]
        collected = collect_results(results)  # Err("failed")
    """
    values = []
    for result in results:
        if result.is_err():
            return result
        values.append(result.unwrap())
    return Ok(values)


def try_except(
    f: Callable[[], T],
    exception_types: tuple = (Exception,),
) -> Result[T, Exception]:
    """
    Wrap a function call in try/except and return a Result.

    Example:
        result = try_except(lambda: int("not a number"))
        if result.is_err():
            print(f"Failed: {result.error}")
    """
    try:
        return Ok(f())
    except exception_types as e:
        return Err(e)


def from_optional(
    value: Optional[T],
    error: E,
) -> Result[T, E]:
    """
    Convert an Optional to a Result.

    Example:
        result = from_optional(some_dict.get("key"), "key not found")
    """
    if value is None:
        return Err(error)
    return Ok(value)
