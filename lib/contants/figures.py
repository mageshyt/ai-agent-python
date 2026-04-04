import sys
BLACK_CIRCLE = '⏺' if sys.platform == 'darwin' else '●'
BULLET_OPERATOR = '∙'
TEARDROP_ASTERISK = '✻'
UP_ARROW = '↑' # ↑ - used for opus 1m merge notice
DOWN_ARROW = '↓' # ↓ - used for scroll hint
LIGHTNING_BOLT = '↯' # ↯ - used for fast mode indicator
EFFORT_LOW = '○' # ○ - effort level: low
EFFORT_MEDIUM = '◐' # ◐ - effort level: medium
EFFORT_HIGH = '●' # ● - effort level: high
EFFORT_MAX = '◉' # ◉ - effort level: max (Opus 4.6 only)

# Media/trigger status indicators
PLAY_ICON = '▶' # ▶
PAUSE_ICON = '⏸' # ⏸

# MCP subscription indicators
REFRESH_ARROW = '↻' # ↻ - used for resource update indicator
CHANNEL_ARROW = '←' # ← - inbound channel message indicator
INJECTED_ARROW = '→' # → - cross-session injected message indicator
FORK_GLYPH = '⑂' # ⑂ - fork directive indicator

# Review status indicators (ultrareview diamond states)
DIAMOND_OPEN = '◇' # ◇ - running
DIAMOND_FILLED = '◆' # ◆ - completed/failed
REFERENCE_MARK = '※' # ※ - komejirushi, away-summary recap marker

# Issue flag indicator
FLAG_ICON = '⚑' # ⚑ - used for issue flag banner

# Blockquote indicator
BLOCKQUOTE_BAR = '▎' # ▎ - left one-quarter block, used as blockquote line prefix
HEAVY_HORIZONTAL = '━' # ━ - heavy box-drawing horizontal

# Bridge status indicators
BRIDGE_SPINNER_FRAMES = [
    '·|·',
    '·/·',
    '·—·',
    '·\·',
]
BRIDGE_READY_INDICATOR = '·✔︎·'
BRIDGE_FAILED_INDICATOR = '×'
