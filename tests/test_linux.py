from term.linux import linux_name
from term.errors import TermError
import pytest


def test_linux_name_ok() -> None:
    assert linux_name("Sergey1") == "Sergey1"


def test_linux_name_bad() -> None:
    with pytest.raises(TermError):
        linux_name("../etc")
