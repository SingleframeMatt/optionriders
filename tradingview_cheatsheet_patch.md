# TradingView Cheat Sheet Add-On

This patch adds a Barchart-style `Trader's Cheat Sheet` table that can be turned on/off.

Methodology is based on Barchart's published Cheat Sheet formulas for:

- Pivot Point / R1 / R2 / R3 / S1 / S2 / S3
- Target Price

Source:

- https://www.barchart.com/stocks/quotes/RH/cheat-sheet
- https://www.barchart.com/stocks/quotes/GFIG/cheat-sheet

Notes:

- The pivot and target formulas below follow Barchart's published definitions.
- The `1-Month`, `13-Week`, and `52-Week` highs/lows are implemented as rolling lookbacks from completed higher-timeframe bars. Barchart publicly names those levels, but does not publish a separate formula block for them on the Cheat Sheet page, so this part is an inference from the documented labels.

## 1. Add These Inputs

Place this block after your Dashboard inputs.

```pine
// ── 16. Trader's Cheat Sheet ────────────────────────────────────────────────
GCS            = "🧾 Trader's Cheat Sheet"
showCheat      = input.bool(false, "Show Trader's Cheat Sheet", group=GCS, tooltip="Shows a Barchart-style ladder of projected support/resistance levels for the current or next session.")
cheatPos       = input.string("Top Right", "Table Position", options=["Top Left", "Top Right", "Bottom Left", "Bottom Right"], group=GCS)
cheatShowPivots= input.bool(true,  "  └ Show Pivot Ladder", group=GCS)
cheatShowHiLo  = input.bool(true,  "  └ Show 1M / 13W / 52W High-Low", group=GCS)
cheatShowTP    = input.bool(true,  "  └ Show Target Price", group=GCS)
cheatTextSize  = input.string("Small", "Text Size", options=["Tiny", "Small", "Normal"], group=GCS)
```

## 2. Add These Helpers And Calculations

Place this block after your existing key-level calculations, before the Dashboard section is fine.

```pine
// ══════════════════════════════════════════════════════════════════════════════
// ██  TRADER'S CHEAT SHEET (BARCHART-STYLE)
// ══════════════════════════════════════════════════════════════════════════════

cheatPosConst = cheatPos == "Top Left" ? position.top_left : cheatPos == "Bottom Left" ? position.bottom_left : cheatPos == "Bottom Right" ? position.bottom_right : position.top_right
cheatTxtSize  = cheatTextSize == "Tiny" ? size.tiny : cheatTextSize == "Normal" ? size.normal : size.small

// Barchart-documented pivot inputs: prior completed daily H/L/C
// lookahead_off (default) returns the last closed HTF bar — same as lookahead_on + [1], no warning.
csDayH1 = request.security(syminfo.tickerid, "D", high)
csDayL1 = request.security(syminfo.tickerid, "D", low)
csDayC1 = request.security(syminfo.tickerid, "D", close)

// Barchart-documented target-price inputs
csTP0 = request.security(syminfo.tickerid, "D", hlc3)
csTP1 = request.security(syminfo.tickerid, "D", hlc3[1])
csTP2 = request.security(syminfo.tickerid, "D", hlc3[2])
csTP3 = request.security(syminfo.tickerid, "D", hlc3[3])

// Rolling highs/lows from completed bars
cs1mH  = request.security(syminfo.tickerid, "D", ta.highest(high, 21))
cs1mL  = request.security(syminfo.tickerid, "D", ta.lowest(low, 21))
cs13wH = request.security(syminfo.tickerid, "W", ta.highest(high, 13))
cs13wL = request.security(syminfo.tickerid, "W", ta.lowest(low, 13))
cs52wH = request.security(syminfo.tickerid, "W", ta.highest(high, 52))
cs52wL = request.security(syminfo.tickerid, "W", ta.lowest(low, 52))

csPP = (csDayH1 + csDayL1 + csDayC1) / 3.0
csR1 = (2.0 * csPP) - csDayL1
csS1 = (2.0 * csPP) - csDayH1
csR2 = csPP + (csR1 - csS1)
csS2 = csPP - (csR1 - csS1)
csR3 = csDayH1 + (2.0 * (csPP - csDayL1))
csS3 = csDayL1 - (2.0 * (csDayH1 - csPP))
csTarget = csDayC1 + (csTP0 + csTP1 + csTP2) / 3.0 - (csTP1 + csTP2 + csTP3) / 3.0

var table cheatTbl = table.new(cheatPosConst, 2, 16, bgcolor=color.new(#101214, 12), border_width=1, border_color=color.new(#3A3A3A, 0), frame_width=1, frame_color=color.new(#5A5A5A, 0))
var string[] cheatNames = array.new_string()
var float[]  cheatVals  = array.new_float()

cheatPush(float _lvl, string _name) =>
    if not na(_lvl)
        int _at = array.size(cheatVals)
        if array.size(cheatVals) > 0
            for _i = 0 to array.size(cheatVals) - 1
                if _lvl > array.get(cheatVals, _i)
                    _at := _i
                    break
        array.insert(cheatVals, _at, _lvl)
        array.insert(cheatNames, _at, _name)
```

## 3. Add The Table Renderer

Place this block after your Dashboard block and before Alerts.

```pine
if barstate.islast
    // Clear all rows so old values don't linger when toggles change
    for _r = 0 to 15
        table.cell(cheatTbl, 0, _r, "", bgcolor=color.new(#000000, 100), text_color=color.new(#000000, 100), text_size=cheatTxtSize)
        table.cell(cheatTbl, 1, _r, "", bgcolor=color.new(#000000, 100), text_color=color.new(#000000, 100), text_size=cheatTxtSize)

    if showCheat
        array.clear(cheatNames)
        array.clear(cheatVals)

        if cheatShowHiLo
            cheatPush(cs52wH, "52-Week High")
            cheatPush(cs13wH, "13-Week High")
            cheatPush(cs1mH,  "1-Month High")

        if cheatShowPivots
            cheatPush(csR3, "Pivot Point 3rd Level Resistance")
            cheatPush(csR2, "Pivot Point 2nd Level Resistance")

        if cheatShowTP
            cheatPush(csTarget, "Target Price")

        if cheatShowPivots
            cheatPush(csR1, "Pivot Point 1st Resistance")

        cheatPush(close, "Latest")

        if cheatShowPivots
            cheatPush(csPP, "Pivot Point")
            cheatPush(csS1, "Pivot Point 1st Support")
            cheatPush(csS2, "Pivot Point 2nd Support")
            cheatPush(csS3, "Pivot Point 3rd Support")

        if cheatShowHiLo
            cheatPush(cs1mL,  "1-Month Low")
            cheatPush(cs13wL, "13-Week Low")
            cheatPush(cs52wL, "52-Week Low")

        _hdrBg = color.new(#111111, 20)
        _hdrTx = color.new(#D7D7D7, 0)
        table.cell(cheatTbl, 0, 0, "Trader's Cheat Sheet", text_color=_hdrTx, bgcolor=_hdrBg, text_size=cheatTxtSize)
        table.cell(cheatTbl, 1, 0, "Price", text_color=_hdrTx, bgcolor=_hdrBg, text_size=cheatTxtSize)

        _maxRows = math.min(array.size(cheatVals), 15)
        if _maxRows > 0
            for _i = 0 to _maxRows - 1
                _lvl  = array.get(cheatVals, _i)
                _name = array.get(cheatNames, _i)
                _isLatest = _name == "Latest"
                _above = _lvl > close
                _bg = _isLatest ? color.new(#FFF59D, 70) : _above ? color.new(#FFCDD2, 52) : color.new(#D6EAF8, 50)
                _tx = _isLatest ? color.new(#111111, 0) : _above ? color.new(#B71C1C, 0) : color.new(#0D3B66, 0)
                table.cell(cheatTbl, 0, _i + 1, _name, text_color=_tx, bgcolor=_bg, text_size=cheatTxtSize)
                table.cell(cheatTbl, 1, _i + 1, str.tostring(_lvl, format.mintick), text_color=_tx, bgcolor=_bg, text_size=cheatTxtSize)
```

## 4. What This Adds

- An on/off `Trader's Cheat Sheet` section
- A Barchart-style level ladder for the current ticker
- Daily pivot levels based on the prior completed day
- A target price using Barchart's documented formula
- Rolling 1-month, 13-week, and 52-week highs/lows
- Automatic red-above / blue-below / yellow-latest row coloring

## 5. Notes

- This is table-only, so it will not add more chart clutter.
- If you also want these cheat-sheet levels drawn as horizontal lines on the chart, that can be added as a second toggle.
- Your existing `PDH / PDL / PDC / weekly / monthly / ORB` section already covers some nearby context, so the table is the cleanest first step.
