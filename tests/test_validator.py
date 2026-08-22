from pydantic import ValidationError

from backend.browser.schemas import BrowserAction
from backend.browser.validator import ActionValidator


def test_valid_navigate():
    validator = ActionValidator()

    action = BrowserAction(
        action="navigate",
        url="https://example.com",
    )

    validator.validate(action)


def test_valid_click():
    validator = ActionValidator()

    action = BrowserAction(
        action="click",
        selector="#submit",
    )

    validator.validate(action)


def test_valid_type():
    validator = ActionValidator()

    action = BrowserAction(
        action="type",
        selector="#search",
        text="hello",
    )

    validator.validate(action)


def test_missing_selector():
    validator = ActionValidator()

    action = BrowserAction(
        action="click",
    )

    try:
        validator.validate(action)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_missing_type_text():
    validator = ActionValidator()

    action = BrowserAction(
        action="type",
        selector="#search",
    )

    try:
        validator.validate(action)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_blocks_javascript_url():
    validator = ActionValidator()

    action = BrowserAction(
        action="navigate",
        url="javascript:alert(1)",
    )

    try:
        validator.validate(action)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_blocks_file_url():
    validator = ActionValidator()

    action = BrowserAction(
        action="navigate",
        url="file:///etc/passwd",
    )

    try:
        validator.validate(action)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_rejects_invalid_url():
    validator = ActionValidator()

    action = BrowserAction(
        action="navigate",
        url="not-a-url",
    )

    try:
        validator.validate(action)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_invalid_action_schema():
    try:
        BrowserAction(
            action="delete_database"
        )

        assert False, "Expected ValidationError"

    except ValidationError:
        pass


if __name__ == "__main__":
    test_valid_navigate()
    test_valid_click()
    test_valid_type()
    test_missing_selector()
    test_missing_type_text()
    test_blocks_javascript_url()
    test_blocks_file_url()
    test_rejects_invalid_url()
    test_invalid_action_schema()

    print("✓ Validator tests passed")
