from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_participant_navigation_is_viewport_fixed_and_safe_area_aware() -> None:
    # FloatingNav keeps the fixed-dock contract under AURA×ORBIT; active state
    # uses the semantic --era-selected token instead of a hardcoded violet wash.
    source = _read("frontend/src/components/FloatingNav.tsx")
    layout = _read("frontend/src/layouts/UserLayout.tsx")

    assert 'position: "fixed"' in source
    assert 'bottom: "calc(0.55rem + env(safe-area-inset-bottom, 0px))"' in source
    assert 'left: "50%"' in source
    assert 'transform: "translateX(-50%)"' in source
    assert 'className="era-bottom-nav"' in source
    assert 'aria-current={isActive ? "page" : undefined}' in source
    assert 'background: isActive ? "var(--era-selected)" : "transparent"' in source
    assert 'label: "Орбита"' in source
    assert 'label: "Афиша"' in source
    assert "--era-bottom-nav-clearance" in layout


def test_aura_theme_has_dark_nav_glass_and_visible_noninteractive_grain() -> None:
    # AURA dark glass tokens live in layout-safety.css (nav) and tokens.css
    # (grain/clearance). Protect the dark chrome from accidental light-theme
    # regressions.
    nav_css = _read("frontend/src/theme/layout-safety.css")
    base_tokens = _read("frontend/src/theme/tokens.css")

    assert "--era-nav-border: rgba(157, 190, 255, 0.25)" in nav_css
    assert "--era-nav-glass: rgba(10, 18, 35, 0.9)" in nav_css
    assert "--era-bottom-nav-clearance:" in base_tokens
    assert "body::before" in base_tokens
    assert "z-index: 9999" in base_tokens
    assert "pointer-events: none" in base_tokens.split("body::before", 1)[1].split("}", 1)[0]
