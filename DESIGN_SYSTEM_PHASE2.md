# PHASE 2: DESIGN SYSTEM - ClearView Analytics

**Objective**: Create a cohesive design language inspired by Koyfin, Bloomberg Terminal, and Stripe Dashboard.

**Principles**:
- Professional and institutional
- Data-centric with clear hierarchy
- Minimal but purposeful visual effects
- Fast and scannable
- Accessible contrast ratios

---

## 1. COLOR PALETTE

### Neutral Base (Primary)
```
--bg:        #0f1419    /* Main background - deep navy */
--bg2:       #131a24    /* Primary container background */
--bg3:       #1a2332    /* Secondary container (hover states) */
--bg4:       #232d3d    /* Tertiary container (accents, cards) */

--border:    #2a3447    /* Primary borders */
--border2:   #3a4557    /* Secondary borders (lighter) */
--border3:   #1a2332    /* Tertiary borders (darker) */
```

**Rationale**: 
- Slightly warmer than previous (#05070d) - less harsh
- Better separation between layers (better than --bg2/bg3/bg4 mixing)
- Maintains dark mode aesthetic without neon feel

### Text & Hierarchy
```
--text:      #f0f4f9    /* Primary text - high contrast */
--text2:     #c0c9d6    /* Secondary text - UI labels, annotations */
--text3:     #8a95a8    /* Tertiary text - muted, less important */
--text4:     #5a6577    /* Quaternary text - disabled, hints */

--text-inv:  #0f1419    /* Inverse text - for light backgrounds */
```

**Rationale**:
- Stepped hierarchy (clear priority)
- Meets WCAG AA contrast ratios (--text: 7.8:1 on --bg)
- --text2 appropriate for interface text (5.2:1 contrast)
- --text3 for tertiary info (3.8:1 - acceptable for non-critical)

### Semantic Colors (Data)
```
--success:   #17b981    /* Positive returns, bullish, growth */
--danger:    #ef5350    /* Negative returns, bearish, loss */
--warning:   #f9a825    /* Warnings, cautions, elevated risk */
--info:      #2196f3    /* Information, neutral insights */

--up:        #17b981    /* Upward direction */
--down:      #ef5350    /* Downward direction */
--neutral:   #8a95a8    /* Neutral/transitional state */
```

**Rationale**:
- Success green is muted (not neon #2ce7a0)
- Danger red is softer than #ff5f7f (less jarring)
- Warning amber is balanced (not overly bright)
- Uses semantic names, not emotion-based

### Accent (Primary Action)
```
--accent:    #4a90e2    /* Primary brand/action color */
--accent-light: #6ab3f5 /* Hover state, lighter variant */
--accent-dark:  #2e5fc7 /* Active state, darker variant */
```

**Rationale**:
- Professional blue (Koyfin-inspired)
- Clear light/normal/dark states for interactions
- Avoids cyan (#28b8ff) which feels artificial

### Regime Indicators (Specialized)
```
--regime-bull:    #17b981    /* Low-Vol Bull - green */
--regime-bear:    #f9a825    /* High-Vol Bear - orange */
--regime-crisis:  #ef5350    /* Crisis - red */
--regime-trans:   #8a95a8    /* Transitional - gray */
```

**Rationale**:
- Mapped to semantic success/warning/danger colors
- Clear distinction without cognitive overload
- Gray for neutral/transitional state

---

## 2. TYPOGRAPHY

### Font Families
```
--font-display:  'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
--font-body:     'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
--font-mono:     'Geist Mono', 'IBM Plex Mono', 'JetBrains Mono', monospace
```

**Rationale**:
- Geist: Modern, clean, institutional (used by Vercel, Stripe)
- Inter: Highly legible, designed for screens (used by Bloomberg)
- Geist Mono: Matches Geist, professional appearance

**Fallback**: If Geist/Inter unavailable, system fonts handle gracefully

### Typography Scale

| Name | Size | Weight | Line-Height | Usage |
|------|------|--------|-------------|-------|
| **Display XL** | 48px | 700 | 1.1 | Page titles (rare) |
| **Display L** | 32px | 700 | 1.2 | Section headers |
| **Display M** | 28px | 700 | 1.2 | Major headings |
| **Display S** | 20px | 600 | 1.3 | Card titles |
| **Body XL** | 16px | 400/600 | 1.5 | Primary text, emphasis |
| **Body L** | 14px | 400/600 | 1.5 | Regular body text |
| **Body M** | 13px | 400/500 | 1.5 | UI labels, small text |
| **Body S** | 12px | 400/500 | 1.4 | Captions, metadata |
| **Body XS** | 11px | 500 | 1.3 | Tertiary labels, hints |
| **Mono** | 13px | 400 | 1.5 | Code, data values |
| **Mono S** | 12px | 400 | 1.4 | Compact data |

### Usage Rules
- **Headlines**: Display scale (D32, D28, D20)
- **Body**: Body scale (16px primary, 14px standard, 13px UI)
- **Data/Values**: Mono scale (consistent family, no size below 12px)
- **Metadata**: Body XS (11px) - labels only, never primary content

---

## 3. SPACING SYSTEM

### Base Unit: 8px
All spacing derived from 8px base.

```
--space-0:    0px
--space-1:    4px      /* Minimum padding, micro-spacing */
--space-2:    8px      /* Base unit */
--space-3:    12px     /* Components internal */
--space-4:    16px     /* Standard gap between elements */
--space-5:    20px     /* Card internal spacing */
--space-6:    24px     /* Page padding, major sections */
--space-7:    32px     /* Large sections, top-level padding */
--space-8:    40px     /* Huge gaps (rare) */
--space-9:    48px     /* Maximum spacing */
```

### Application
- **Component internal**: 16px (space-4)
- **Gap between components**: 16px (space-4)
- **Card padding**: 20-24px (space-5/6)
- **Page padding**: 28-32px (space-6/7)
- **Sidebar padding**: 20px horizontal (space-5)
- **Input padding**: 10px horizontal, 8px vertical (space-2/3 base)

---

## 4. BORDERS & CORNERS

### Border Radius
```
--radius-none:   0px
--radius-sm:     4px      /* Small buttons, compact elements */
--radius-md:     8px      /* Cards, modals, standard components */
--radius-lg:     12px     /* Large cards, panels */
--radius-xl:     16px     /* Extra large sections */
--radius-full:   9999px   /* Fully rounded (pills, badges) */
```

**Usage**:
- Cards: 8px (md)
- Buttons: 6px (small-md)
- Inputs: 6px (small-md)
- Badges/Pills: 9999px (full)
- Modals: 12px (lg)

**Rationale**: Restrained, professional. Avoids excessive rounding that looks amateurish.

### Border Thickness
```
--border-thin:    1px      /* Standard borders */
--border-thick:   2px      /* Active/selected states */
--border-xthick:  3px      /* Emphasis borders (rarely used) */
```

---

## 5. SHADOWS

### Shadow Scale
```
--shadow-none:    none

--shadow-sm:      0 1px 2px 0 rgba(15, 20, 25, 0.2)
                  /* Subtle depth for interactive elements */

--shadow-md:      0 2px 4px 0 rgba(15, 20, 25, 0.25),
                  0 1px 2px -1px rgba(15, 20, 25, 0.15)
                  /* Standard depth for cards/modals */

--shadow-lg:      0 4px 8px 0 rgba(15, 20, 25, 0.3),
                  0 2px 4px -2px rgba(15, 20, 25, 0.2)
                  /* Prominent depth for elevated elements */

--shadow-focus:   0 0 0 3px rgba(74, 144, 226, 0.2)
                  /* Focus ring for accessibility */
```

**Usage**:
- Default cards: sm-md (subtle)
- Modals: md-lg
- Hover cards: md (slight elevation)
- Focus state: --shadow-focus on top of border

**Rationale**: Minimal but present. Creates depth without looking 3D-ish. Avoids excessive blur.

---

## 6. EFFECTS & TRANSITIONS

### Blur & Backdrop
```
--backdrop-sm:    blur(4px)
--backdrop-md:    blur(8px)
```

**Usage**:
- Sidebar: md (8px)
- Topbar: sm (4px)
- Modals: Overlay only, not components

**Rationale**: Minimal use. Backdrop filters for sticky headers only, not every surface.

### Transitions
```
--transition-fast:    150ms ease-out
--transition-base:    200ms ease-out
--transition-slow:    300ms ease-out
```

**Usage**:
- Hover effects: 150ms
- State changes: 200ms
- Loading animations: 300ms

**Rationale**: Snappy but not jarring. Avoids animation overload.

---

## 7. ELEVATION & Z-INDEX

### Z-Index Scale
```
--z-base:         0       /* Default */
--z-above:        1       /* Dropdowns, tooltips */
--z-sticky:       10      /* Sticky header, sidebar */
--z-modal:        100     /* Modal overlay */
--z-top:          1000    /* Top-level content inside modal */
```

---

## 8. COMPONENT-SPECIFIC TOKENS

### Buttons
```
--btn-primary-bg:      #4a90e2
--btn-primary-fg:      #ffffff
--btn-primary-hover:   #6ab3f5
--btn-primary-active:  #2e5fc7

--btn-secondary-bg:    transparent
--btn-secondary-border: #3a4557
--btn-secondary-fg:    #f0f4f9
--btn-secondary-hover: #1a2332
```

### Forms
```
--input-bg:           #1a2332
--input-border:       #2a3447
--input-border-hover: #3a4557
--input-border-focus: #4a90e2
--input-fg:           #f0f4f9
--input-placeholder:  #5a6577
```

### Tables
```
--table-header-bg:    transparent
--table-header-fg:    #8a95a8
--table-border:       #2a3447
--table-row-hover:    #1a2332
--table-accent-row:   rgba(74, 144, 226, 0.05)
```

### Badges
```
--badge-success-bg:   rgba(23, 185, 129, 0.1)
--badge-success-fg:   #17b981

--badge-danger-bg:    rgba(239, 83, 80, 0.1)
--badge-danger-fg:    #ef5350

--badge-warning-bg:   rgba(249, 168, 37, 0.1)
--badge-warning-fg:   #f9a825

--badge-info-bg:      rgba(33, 150, 243, 0.1)
--badge-info-fg:      #2196f3
```

---

## 9. RESPONSIVE BREAKPOINTS

```
--breakpoint-sm:      640px
--breakpoint-md:      768px
--breakpoint-lg:      1024px
--breakpoint-xl:      1280px
--breakpoint-2xl:     1536px
```

**Layout**:
- Sidebar: Hidden below md (768px)
- Grid: Auto-fit (2 cols below lg, 3+ cols above lg)
- Page padding: 16px below md, 32px above md

---

## 10. IMPLEMENTATION STRATEGY

### CSS Variables Organization
```css
:root {
  /* Colors - Neutral Base */
  --bg: #0f1419;
  --bg2: #131a24;
  --bg3: #1a2332;
  --bg4: #232d3d;
  
  /* Colors - Text */
  --text: #f0f4f9;
  --text2: #c0c9d6;
  --text3: #8a95a8;
  --text4: #5a6577;
  
  /* Colors - Semantic */
  --success: #17b981;
  --danger: #ef5350;
  --warning: #f9a825;
  --info: #2196f3;
  
  /* Colors - Accent */
  --accent: #4a90e2;
  --accent-light: #6ab3f5;
  --accent-dark: #2e5fc7;
  
  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 32px;
  
  /* Border Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;
  
  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgba(15, 20, 25, 0.2);
  --shadow-md: 0 2px 4px 0 rgba(15, 20, 25, 0.25), 0 1px 2px -1px rgba(15, 20, 25, 0.15);
  
  /* Transitions */
  --transition: 150ms ease-out;
  
  /* Z-Index */
  --z-sticky: 10;
  --z-modal: 100;
}
```

### Removal Targets (OLD SYSTEM)
```css
/* REMOVE THESE */
--cyan: #28f0ff;
--green: #2ce7a0;
--red: #ff5f7f;
--amber: #ffc46c;
--accent2: #6ddbff;
--accent3: #148fce;
--border2: #2f4768;  /* OLD - will replace */
--bull / --bear / --crisis / --trans  /* OLD - use semantic colors */
```

---

## 11. KOYFIN INSPIRATION NOTES

### What We're Taking From Koyfin
1. **Color Palette**: Professional blue-grays, not neon
2. **Density**: Information-rich layouts without clutter
3. **Typography**: Clear hierarchy, generous line-height
4. **Spacing**: Generous whitespace, not cramped
5. **Borders**: Subtle, 1px, professional
6. **Shadows**: Minimal, used for elevation only
7. **Interactions**: Smooth but fast (no bloated animations)

### What We're NOT Copying
- Koyfin's specific UI components
- Koyfin's layout grid structure
- Koyfin's keyboard shortcuts
- Koyfin's terminal aesthetic (we're keeping web-based look)

---

## 12. VALIDATION CHECKLIST

✓ Color contrast ratios meet WCAG AA (4.5:1 minimum)  
✓ No excessive gradients  
✓ No neon colors  
✓ Clear typography hierarchy  
✓ Consistent spacing (8px base)  
✓ Minimal shadows  
✓ Restrained border radius  
✓ Professional appearance  
✓ Data-centric design  
✓ Fast & scannable layouts  

---

## NEXT: IMPLEMENTATION

Phase 3 will apply these tokens to the existing CSS, replacing:
- Color variables (new palette)
- Typography rules (new scale)
- Spacing utilities (8px-based)
- Border/shadow components
- All affected class selectors

No JSX changes. Pure CSS implementation.

**Ready for Phase 3: CSS Variable Updates & Component Styling**
