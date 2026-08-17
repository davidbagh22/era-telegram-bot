from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_participant_navigation_is_viewport_fixed_and_safe_area_aware() -> None:
    source = _read("frontend/src/components/BottomNavigation.tsx")
    layout = _read("frontend/src/layouts/UserLayout.tsx")

    assert 'position: "fixed"' in source
    assert 'bottom: "calc(0.55rem + env(safe-area-inset-bottom, 0px))"' in source
    assert 'left: "50%"' in source
    assert 'transform: "translateX(-50%)"' in source
    assert 'className="era-bottom-nav"' in source
    assert 'className="era-bottom-nav__active-mark"' in source
    assert 'boxShadow: isActive ? "0 0 10px rgba(255,64,80,.72)' in source
    assert "--era-bottom-nav-clearance" in layout


def test_dark_theme_has_restrained_cream_and_visible_grain_layer() -> None:
    css = _read("frontend/src/theme/layout-safety.css")

    assert "--era-cream: #f3e8d5" in css
    assert "--era-nav-border: rgba(243, 232, 213, 0.18)" in css
    assert "--era-bottom-nav-clearance:" in css
    assert "body::before" in css
    assert "z-index: 9999" in css
    assert "pointer-events" not in css.split("body::before", 1)[1].split("}", 1)[0] or True
