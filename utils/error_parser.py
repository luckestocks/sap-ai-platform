# utils/error_parser.py
# SAP AI Platform — Phase 2
# Error pattern clustering: parses multi-line SAP log dumps into structured,
# classified error lines before sending to the LLM.
#
# WHY THIS EXISTS:
#   Raw SAP logs contain a mix of root causes, cascading failures, warnings,
#   and noise (retries, timestamps, job headers). Sending the full blob to the
#   LLM wastes tokens and can confuse root cause identification.
#   This module separates them so the LLM gets a clean, structured view.
#
# OUTPUT STRUCTURE:
#   {
#     "root_causes":   [ list of ErrorLine ],   # the actual problems to fix
#     "cascading":     [ list of ErrorLine ],   # happened because of root cause
#     "warnings":      [ list of ErrorLine ],   # non-fatal, worth noting
#     "noise":         [ list of ErrorLine ],   # retries, timestamps, headers
#     "clusters":      [ list of Cluster ],     # grouped by error pattern
#     "raw_lines":     int,                     # total lines in input
#     "is_multiline":  bool,                    # True if input has >2 lines
#   }

import re
from dataclasses import dataclass, field


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ErrorLine:
    raw: str            # original text
    classification: str # ROOT | CASCADING | WARNING | NOISE
    error_code: str     # e.g. E0001, W001, or "" if none
    sap_area: str       # e.g. IDoc, BODS, BAPI, RFC, or "General"
    line_num: int       # position in original input


@dataclass
class Cluster:
    pattern: str        # the common pattern label
    sap_area: str
    lines: list = field(default_factory=list)   # list of ErrorLine

    @property
    def count(self) -> int:
        return len(self.lines)

    @property
    def sample(self) -> str:
        return self.lines[0].raw if self.lines else ""


# ── SAP error code patterns ───────────────────────────────────────────────────

# Matches: E0001, W001, E001, BRAIN123, ME001, etc.
_ERROR_CODE_RE = re.compile(r'\b([A-Z]{1,5}\d{3,5})\b')

# Matches severity prefix: E: / W: / I: / E / W at line start
_SEVERITY_PREFIX_RE = re.compile(r'^\s*[EWI]\s*:\s*', re.IGNORECASE)

# Noise patterns — lines that carry no actionable info
_NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'retry attempt \d+',
        r'attempt \d+ of \d+',
        r'^\s*\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}',   # bare timestamp lines
        r'job\s+\w+\s+(started|triggered|scheduled)',
        r'^\s*-{3,}',                                  # separator lines
        r'^\s*={3,}',
        r'^\s*\*{3,}',
        r'elapsed time',
        r'execution time',
        r'log written to',
        r'spool request',
        r'^\s*$',                                       # blank lines
    ]
]

# Cascading error indicators — downstream failures caused by something else
_CASCADING_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'downstream',
        r'dependency\s+(on|not\s+met)',
        r'aborted\s+due\s+to',
        r'skipped\s+due\s+to',
        r'cancelled\s+due\s+to',
        r'because\s+of\s+(previous|above|earlier)',
        r'prerequisite\s+(not\s+met|failed|missing)',
        r'waiting\s+for\s+\w+\s+to\s+complete',
        r'parent\s+(job|step|task)\s+failed',
        r'reference\s+missing',
        r'foreign\s+key',
        r'not\s+found.*due\s+to',
    ]
]

# Root cause indicators — the actual problem to fix
_ROOT_CAUSE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bE\d{4}\b',                          # classic SAP E-codes: E0001, E1234
        r'partner\s+profile\s+not\s+found',
        r'not\s+configured',
        r'missing\s+configuration',
        r'connection\s+(timeout|refused|failed)',
        r'authentication\s+failed',
        r'authorization\s+(check\s+)?failed',
        r'table\s+\w+\s+(not\s+found|does\s+not\s+exist)',
        r'field\s+\w+\s+(mandatory|required|missing)',
        r'duplicate\s+(key|entry|record)',
        r'lock\s+(wait\s+)?timeout',
        r'RFC\s+destination\s+\w+\s+not\s+found',
        r'IDoc\s+status\s+set\s+to\s+5[12]',
        r'BODS\s+job\s+failed',
        r'datastore\s+(connection\s+)?error',
    ]
]

# Warning indicators
_WARNING_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'^\s*W\s*:',
        r'\bwarning\b',
        r'status\s+set\s+to\s+5[12]',           # IDoc 51/52 = warning-level
        r'check\s+\w+\s+for',                    # "Check WE20 for..."
        r'recommended\s+to',
        r'consider\s+',
    ]
]

# SAP area detection
_SAP_AREA_PATTERNS = [
    ("IDoc",  re.compile(r'\b(IDoc|WE\d{2}|BD\d{2}|ALE|partner\s+profile|logical\s+system)\b', re.IGNORECASE)),
    ("BODS",  re.compile(r'\b(BODS|Data\s+Services|DataStore|DS_|job\s+server|repository)\b', re.IGNORECASE)),
    ("BAPI",  re.compile(r'\b(BAPI_\w+|BAPI\s+call|function\s+module)\b', re.IGNORECASE)),
    ("RFC",   re.compile(r'\b(RFC|SM59|remote\s+function|RFC\s+destination)\b', re.IGNORECASE)),
    ("LTMC",  re.compile(r'\b(LTMC|LTMOM|migration\s+object|migration\s+project)\b', re.IGNORECASE)),
    ("LSMW",  re.compile(r'\b(LSMW|legacy\s+system\s+migration)\b', re.IGNORECASE)),
    ("SM21",  re.compile(r'\b(SM21|system\s+log|syslog)\b', re.IGNORECASE)),
    ("SDI",   re.compile(r'\b(SDI|Smart\s+Data\s+Integration|flowgraph|replication\s+task)\b', re.IGNORECASE)),
]


# ── Core classification ───────────────────────────────────────────────────────

def _detect_sap_area(text: str) -> str:
    for area, pattern in _SAP_AREA_PATTERNS:
        if pattern.search(text):
            return area
    return "General"


def _extract_error_code(text: str) -> str:
    match = _ERROR_CODE_RE.search(text)
    return match.group(1) if match else ""


def _classify_line(text: str) -> str:
    """Return ROOT | CASCADING | WARNING | NOISE for a single line."""
    # Noise first — skip immediately
    for p in _NOISE_PATTERNS:
        if p.search(text):
            return "NOISE"

    # Cascading — downstream failure caused by something else
    for p in _CASCADING_PATTERNS:
        if p.search(text):
            return "CASCADING"

    # Warning
    for p in _WARNING_PATTERNS:
        if p.search(text):
            return "WARNING"

    # Root cause
    for p in _ROOT_CAUSE_PATTERNS:
        if p.search(text):
            return "ROOT"

    # Lines with explicit E: prefix but no other match → root
    if _SEVERITY_PREFIX_RE.match(text):
        return "ROOT"

    # Anything else with content → noise
    return "NOISE"


# ── Clustering ────────────────────────────────────────────────────────────────

def _cluster_lines(lines: list[ErrorLine]) -> list[Cluster]:
    """
    Group ErrorLines by (sap_area, error_code_prefix).
    Lines with no error code are grouped by sap_area alone.
    """
    buckets: dict[str, Cluster] = {}

    for line in lines:
        if line.classification == "NOISE":
            continue

        # Build cluster key
        code_prefix = line.error_code[:2] if line.error_code else ""
        key = f"{line.sap_area}::{code_prefix}" if code_prefix else line.sap_area

        # Human-readable pattern label
        if line.error_code:
            pattern = f"{line.sap_area} — {line.error_code[:2]}xxx series"
        else:
            pattern = f"{line.sap_area} — general errors"

        if key not in buckets:
            buckets[key] = Cluster(pattern=pattern, sap_area=line.sap_area)
        buckets[key].lines.append(line)

    # Sort clusters: most lines first
    return sorted(buckets.values(), key=lambda c: c.count, reverse=True)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_error_input(raw_input: str) -> dict:
    """
    Parse a raw SAP error paste (single line or multi-line log dump).
    Returns structured classification and clusters.

    If input is a single line or two lines, is_multiline=False and the
    caller should skip showing the clustering UI (nothing to cluster).
    """
    lines_raw = [l for l in raw_input.splitlines()]
    non_empty = [l for l in lines_raw if l.strip()]

    is_multiline = len(non_empty) > 2

    classified: list[ErrorLine] = []
    for i, line in enumerate(non_empty):
        classification = _classify_line(line)
        classified.append(ErrorLine(
            raw=line.strip(),
            classification=classification,
            error_code=_extract_error_code(line),
            sap_area=_detect_sap_area(line),
            line_num=i + 1,
        ))

    root_causes = [l for l in classified if l.classification == "ROOT"]
    cascading   = [l for l in classified if l.classification == "CASCADING"]
    warnings    = [l for l in classified if l.classification == "WARNING"]
    noise       = [l for l in classified if l.classification == "NOISE"]
    clusters    = _cluster_lines(classified)

    return {
        "root_causes":  root_causes,
        "cascading":    cascading,
        "warnings":     warnings,
        "noise":        noise,
        "clusters":     clusters,
        "all_lines":    classified,
        "raw_lines":    len(non_empty),
        "is_multiline": is_multiline,
    }


def build_clean_error_for_llm(parsed: dict) -> str:
    """
    Build a clean, structured error string from parsed results to send to the LLM.
    Strips noise, labels root causes and cascading errors explicitly.
    This replaces the raw paste as the LLM input.
    """
    parts = []

    if parsed["root_causes"]:
        parts.append("ROOT CAUSE(S):")
        for l in parsed["root_causes"]:
            parts.append(f"  {l.raw}")

    if parsed["cascading"]:
        parts.append("\nCASCADING ERRORS (caused by root cause above):")
        for l in parsed["cascading"]:
            parts.append(f"  {l.raw}")

    if parsed["warnings"]:
        parts.append("\nWARNINGS:")
        for l in parsed["warnings"]:
            parts.append(f"  {l.raw}")

    # If parser found nothing actionable, fall back to full input
    if not parts:
        return "\n".join(l.raw for l in parsed["all_lines"])

    return "\n".join(parts)
