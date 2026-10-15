"""The red pen (owner, 2026-10-15): ticks, crosses, scores and comments placed on the scanned
page next to the student's answers, as a teacher marks in red.

No model is involved. The AI already says which answer lines earned each point (line-number
evidence); ``ink`` finds where the lines of handwriting are on the image; ``align`` matches the
transcription's lines to them; ``layout`` decides where every mark goes. When the match is not
confident, a page falls back to marks in the margin: a tick is never put in the wrong place.
"""
