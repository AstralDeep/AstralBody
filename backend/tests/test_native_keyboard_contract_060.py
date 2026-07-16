"""Native chat composers must not overlay a custom keyboard-dismiss control."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_apple_chat_uses_native_immediate_scroll_keyboard_dismissal() -> None:
    source = (
        ROOT / "apple-clients/AstralApp/AstralApp/Views/ChatView.swift"
    ).read_text(encoding="utf-8")

    assert "placement: .keyboard" not in source
    assert 'Button("Done")' not in source
    assert source.count(".scrollDismissesKeyboard(.immediately)") >= 2


def test_android_chat_leaves_dismissal_to_the_native_ime() -> None:
    source = (
        ROOT
        / "android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AdaptiveShell.kt"
    ).read_text(encoding="utf-8")

    assert "keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default)" in source
    assert "LocalSoftwareKeyboardController" not in source
    assert "keyboardController.hide()" not in source
