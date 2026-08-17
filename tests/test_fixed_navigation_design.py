from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_participant_navigation_is_viewport_fixed_and_safe_area_aware() -> None:
    # BottomNavigation.tsx was renamed to FloatingNav.tsx by the light/signal
    # redesign (Mini App visual redesign ToR §13) -- same fixed-dock contract,
    # new component name and violet (not red) active-state glow.
    source = _read("frontend/src/components/FloatingNav.tsx")
    layout = _read("frontend/src/layouts/UserLayout.tsx")

    assert 'position: "fixed"' in source
    assert 'bottom: "calc(0.55rem + env(safe-area-inset-bottom, 0px))"' in source
    assert 'left: "50%"' in source
    assert 'transform: "translateX(-50%)"' in source
    assert 'className="era-bottom-nav"' in source
    assert 'className="era-bottom-nav__active-mark"' in source
    assert 'boxShadow: isActive ? "0 0 8px rgba(99,44,255,.55)"' in source
    assert "--era-bottom-nav-clearance" in layout


def test_light_theme_has_restrained_nav_glass_and_visible_noninteractive_grain() -> None:
    # The redesign moved grain/z-index/clearance into tokens.css and kept
    # only nav-specific tokens (FloatingNav's only consumer) in
    # layout-safety.css -- see that file's own header comment. The old
    # --era-cream dark-theme accent no longer exists; the light theme's nav
    # border/glass values are what actually need protecting from regression.
    nav_css = _read("frontend/src/theme/layout-safety.css")
    base_tokens = _read("frontend/src/theme/tokens.css")

    assert "--era-nav-border: rgba(17, 17, 24, 0.06)" in nav_css
    assert "--era-nav-glass: rgba(255, 255, 255, 0.78)" in nav_css
    assert "--era-bottom-nav-clearance:" in base_tokens
    assert "body::before" in base_tokens
    assert "z-index: 9999" in base_tokens
    assert "pointer-events: none" in base_tokens.split("body::before", 1)[1].split("}", 1)[0]
