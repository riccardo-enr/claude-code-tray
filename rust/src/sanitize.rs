/*
The display trust boundary (D-09 through D-12).

Every string the daemon hands us is untrusted: a session's `dir` is a
filesystem path, and a repository can legally contain a directory named
`$'\e[2J'` (clear screen) or an OSC 52 clipboard write. The daemon reads those
paths and forwards them; nothing between the filesystem and this function
validates them.

The Python oracle closes this at `claude_monitor.core._safe_cell`, which
replaces each non-printable character individually. That is correct but noisy:
a five-byte CSI sequence becomes five `?`. Here we recognise a *complete*
escape sequence and collapse it to one marker, which is both quieter on screen
and a stronger statement -- we are removing a sequence, not censoring bytes and
hoping the remainder is inert.

Two properties this deliberately does NOT have:

  - It does not strip markup. `[bold]repo[/]` survives byte-for-byte (D-11).
    Markup injection is closed at the renderer by using non-markup text APIs;
    mangling printable user content here would make a legitimately-named
    directory unreadable to defend against a threat the renderer already owns.

  - It does not sanitise focus-routing values. Those are opaque and never
    rendered (D-12); truncating or rewriting a pane id would focus the wrong
    window, which is worse than not focusing at all.

Length is counted in Unicode scalar values (`char`), not bytes and not grapheme
clusters. Bytes would let a multi-byte path be cut mid-character; grapheme
clusters would need a Unicode table this crate does not carry. Scalar values
are the honest middle: a truncation never produces invalid UTF-8, and the bound
is a real bound on how much a hostile name can occupy. This is the answer to
the encoding edge probe on RTUI-13.
*/

/* One visible marker per removed sequence or control character. ASCII on
purpose: this repo's output is ASCII-only, and a marker that is itself
non-ASCII would be one more thing for a terminal to interpret. */
pub const REPLACEMENT: char = '?';

/* Appended when a value is cut. Visible, so a truncated path never silently
reads as the whole path. */
pub const TRUNCATION_MARKER: &str = "...";

/* Default ceiling for a rendered display value. Wide enough for a real
project path, narrow enough that a megabyte-long directory name cannot push
the layout around. */
pub const MAX_DISPLAY_CHARS: usize = 512;

/* Ceiling for an opaque focus-routing value. Routing values are validated,
never truncated -- an over-long one rejects its entry instead. */
pub const MAX_ROUTE_CHARS: usize = 256;

/* Sanitize an untrusted string for display at the default bound. */
pub fn sanitize_display(raw: &str) -> String {
    sanitize_display_bounded(raw, MAX_DISPLAY_CHARS)
}

/*
Collapse terminal control sequences and non-printable characters, then bound
the length.

Order matters: sanitize first, truncate second. Truncating first could cut an
escape sequence in half, leaving a fragment that the sequence recogniser no
longer matches and that the terminal might still act on.

An empty input returns an empty string -- no marker, no placeholder. "Nothing
to show" is the caller's decision to render, not this function's to invent.
This is the answer to the empty-input edge probe on RTUI-13.
*/
pub fn sanitize_display_bounded(raw: &str, max_chars: usize) -> String {
    let cleaned = strip_control_sequences(raw);
    truncate_chars(&cleaned, max_chars)
}

/*
Replace every complete terminal control sequence, and every remaining
non-printable or display-hostile character, with a single REPLACEMENT.

Recognised sequence forms:

  - CSI  -- `ESC [` params(0x30-0x3f)* intermediates(0x20-0x2f)* final(0x40-0x7e)
  - OSC  -- `ESC ]` ... terminated by BEL (0x07) or ST (`ESC \`)
  - DCS / SOS / PM / APC -- `ESC P`, `ESC X`, `ESC ^`, `ESC _` ... terminated by ST
  - any other `ESC <byte>` two-character sequence

An unterminated sequence consumes the rest of the input. That is intentional:
if we cannot see where a sequence ends, we cannot know which of the following
bytes are parameters and which are text, and emitting the tail as text is
exactly how a truncated OSC becomes a working OSC once the next value is
concatenated after it.

The 8-bit C1 introducers 0x9b (CSI) and 0x9d (OSC) are handled the same way.
In practice the daemon decodes its input with UTF-8 replacement, so a raw C1
byte usually arrives as U+FFFD -- but this crate does not get to assume that,
because a future caller could hand it a string from elsewhere.

Beyond control characters, three families of printable-but-hostile codepoints
are also replaced:

  - U+2028 / U+2029 line and paragraph separators, which some terminals and
    most text widgets treat as line breaks and which would let a path forge
    extra rows in the sessions table.
  - U+202A-U+202E and U+2066-U+2069, the bidirectional overrides and isolates.
    These are the Trojan Source family: they reorder how the *following* text
    displays without changing what it is, so a directory name can be made to
    render as a different directory name.
  - U+200B-U+200F zero-width and directional marks, which are invisible and so
    make two different paths render identically.
*/
pub fn strip_control_sequences(raw: &str) -> String {
    let chars: Vec<char> = raw.chars().collect();
    let mut out = String::with_capacity(raw.len());
    let mut i = 0usize;

    while i < chars.len() {
        let c = chars[i];

        if c == '\u{1b}' {
            i = skip_escape_sequence(&chars, i);
            out.push(REPLACEMENT);
            continue;
        }
        if c == '\u{9b}' {
            /* 8-bit CSI: parameters and intermediates, then a final byte. */
            i = skip_csi_body(&chars, i + 1);
            out.push(REPLACEMENT);
            continue;
        }
        if c == '\u{9d}' {
            /* 8-bit OSC: runs to a string terminator. */
            i = skip_string_terminated(&chars, i + 1);
            out.push(REPLACEMENT);
            continue;
        }
        if is_display_hostile(c) {
            out.push(REPLACEMENT);
            i += 1;
            continue;
        }

        out.push(c);
        i += 1;
    }

    out
}

/* True for anything that must not reach a terminal as itself. Space is
explicitly allowed; it is a control-free, width-one, non-reordering character
and paths contain it. */
fn is_display_hostile(c: char) -> bool {
    if c == ' ' {
        return false;
    }
    if c.is_control() {
        /* C0, DEL, and C1. Covers tab, newline and carriage return, which have
        no business inside a single table cell. */
        return true;
    }
    matches!(
        c,
        '\u{2028}' | '\u{2029}'                    /* line / paragraph separator */
            | '\u{202a}'..='\u{202e}'              /* bidi embedding and override */
            | '\u{2066}'..='\u{2069}'              /* bidi isolates */
            | '\u{200b}'..='\u{200f}'              /* zero-width and directional marks */
    )
}

/*
Given `chars[start] == ESC`, return the index just past the complete sequence.
Always advances by at least one so the caller cannot loop forever.
*/
fn skip_escape_sequence(chars: &[char], start: usize) -> usize {
    let next = match chars.get(start + 1) {
        Some(c) => *c,
        /* A trailing lone ESC. Consume it. */
        None => return start + 1,
    };
    match next {
        '[' => skip_csi_body(chars, start + 2),
        ']' | 'P' | 'X' | '^' | '_' => skip_string_terminated(chars, start + 2),
        /* Every other ESC form is two characters: ESC 7, ESC =, ESC ( B ... */
        _ => start + 2,
    }
}

/*
Consume a CSI body starting at `from`: parameter bytes 0x30-0x3f, then
intermediate bytes 0x20-0x2f, then one final byte 0x40-0x7e. Returns the index
just past the final byte, or the end of input if the sequence never terminates.
*/
fn skip_csi_body(chars: &[char], from: usize) -> usize {
    let mut i = from;
    while i < chars.len() {
        let c = chars[i] as u32;
        if (0x30..=0x3f).contains(&c) || (0x20..=0x2f).contains(&c) {
            i += 1;
            continue;
        }
        if (0x40..=0x7e).contains(&c) {
            return i + 1;
        }
        /* Anything else means the sequence was malformed. Stop here rather
        than swallowing the remainder of a legitimate path. */
        return i;
    }
    i
}

/*
Consume a string-type sequence body (OSC, DCS, SOS, PM, APC) starting at
`from`, up to and including BEL or ST (`ESC \`). Returns the end of input when
the terminator never arrives.
*/
fn skip_string_terminated(chars: &[char], from: usize) -> usize {
    let mut i = from;
    while i < chars.len() {
        if chars[i] == '\u{7}' {
            return i + 1;
        }
        if chars[i] == '\u{9c}' {
            /* 8-bit ST */
            return i + 1;
        }
        if chars[i] == '\u{1b}' && chars.get(i + 1) == Some(&'\\') {
            return i + 2;
        }
        i += 1;
    }
    i
}

/*
Bound a string to `max_chars` Unicode scalar values, marking the cut.

The marker is included in the budget, so the result never exceeds `max_chars`.
A `max_chars` smaller than the marker degrades to a bare prefix rather than
returning something longer than asked for.
*/
pub fn truncate_chars(s: &str, max_chars: usize) -> String {
    if s.chars().count() <= max_chars {
        return s.to_string();
    }
    let marker_len = TRUNCATION_MARKER.chars().count();
    if max_chars <= marker_len {
        return s.chars().take(max_chars).collect();
    }
    let mut out: String = s.chars().take(max_chars - marker_len).collect();
    out.push_str(TRUNCATION_MARKER);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_stays_empty_with_no_marker() {
        assert_eq!(sanitize_display(""), "");
    }

    #[test]
    fn ordinary_path_is_untouched() {
        assert_eq!(sanitize_display("~/code/claude/claude-code-tray"), "~/code/claude/claude-code-tray");
    }

    #[test]
    fn printable_unicode_survives() {
        assert_eq!(sanitize_display("~/proyectos/caf\u{e9}"), "~/proyectos/caf\u{e9}");
    }

    #[test]
    fn markup_looking_text_is_preserved_literally() {
        /* D-11: the renderer closes markup injection by using non-markup APIs.
        Mangling it here would corrupt a legitimately-named directory. */
        assert_eq!(sanitize_display("[bold]repo[/]"), "[bold]repo[/]");
    }

    #[test]
    fn a_whole_csi_sequence_collapses_to_one_marker() {
        /* ESC [ 2 J -- clear screen. Four chars in, one marker out. */
        assert_eq!(sanitize_display("a\u{1b}[2Jb"), "a?b");
    }

    #[test]
    fn a_csi_with_parameters_and_intermediates_collapses_to_one_marker() {
        assert_eq!(sanitize_display("\u{1b}[38;5;196mred"), "?red");
    }

    #[test]
    fn an_osc_clipboard_write_collapses_to_one_marker() {
        /* OSC 52 with a BEL terminator: the clipboard-hijack payload. */
        assert_eq!(sanitize_display("x\u{1b}]52;c;aGk=\u{7}y"), "x?y");
    }

    #[test]
    fn an_osc_with_st_terminator_collapses_to_one_marker() {
        assert_eq!(sanitize_display("x\u{1b}]0;title\u{1b}\\y"), "x?y");
    }

    #[test]
    fn an_unterminated_osc_consumes_the_tail() {
        /* No terminator: we cannot tell parameters from text, so nothing after
        it may be emitted as text. */
        assert_eq!(sanitize_display("safe\u{1b}]52;c;never-shown"), "safe?");
    }

    #[test]
    fn a_lone_trailing_escape_is_consumed() {
        assert_eq!(sanitize_display("tail\u{1b}"), "tail?");
    }

    #[test]
    fn eight_bit_csi_is_recognised() {
        assert_eq!(sanitize_display("a\u{9b}2Jb"), "a?b");
    }

    #[test]
    fn bare_control_characters_are_replaced_individually() {
        assert_eq!(sanitize_display("a\u{7}\u{8}b"), "a??b");
        assert_eq!(sanitize_display("line\nbreak"), "line?break");
        assert_eq!(sanitize_display("carriage\rreturn"), "carriage?return");
        assert_eq!(sanitize_display("tab\there"), "tab?here");
    }

    #[test]
    fn space_is_not_a_control_character() {
        assert_eq!(sanitize_display("my project"), "my project");
    }

    #[test]
    fn bidi_override_is_replaced() {
        /* Trojan Source: reorders how the following text renders. */
        assert_eq!(sanitize_display("gj\u{202e}pj.txt"), "gj?pj.txt");
    }

    #[test]
    fn zero_width_characters_are_replaced() {
        assert_eq!(sanitize_display("re\u{200b}po"), "re?po");
    }

    #[test]
    fn line_separator_is_replaced() {
        assert_eq!(sanitize_display("a\u{2028}b"), "a?b");
    }

    #[test]
    fn no_raw_escape_byte_ever_survives() {
        /* The single property that matters most: whatever the input, the
        output contains no ESC and no C1 introducer. */
        let hostile = "\u{1b}[2J\u{1b}]52;c;x\u{7}\u{9b}0m\u{1b}Pq\u{1b}\\plain";
        let out = sanitize_display(hostile);
        assert!(!out.contains('\u{1b}'), "ESC survived: {:?}", out);
        assert!(!out.contains('\u{9b}'), "C1 CSI survived: {:?}", out);
        assert!(out.ends_with("plain"), "legitimate tail was lost: {:?}", out);
    }

    #[test]
    fn truncation_marks_the_cut_and_respects_the_bound() {
        let long = "a".repeat(40);
        let out = sanitize_display_bounded(&long, 10);
        assert_eq!(out, "aaaaaaa...");
        assert_eq!(out.chars().count(), 10);
    }

    #[test]
    fn truncation_counts_scalar_values_not_bytes() {
        /* Each char is 2 bytes; a byte-based bound would cut one in half. */
        let long = "\u{e9}".repeat(40);
        let out = sanitize_display_bounded(&long, 10);
        assert_eq!(out.chars().count(), 10);
        assert!(out.ends_with(TRUNCATION_MARKER));
    }

    #[test]
    fn a_value_at_the_bound_is_not_marked() {
        let exact = "a".repeat(10);
        assert_eq!(sanitize_display_bounded(&exact, 10), exact);
    }

    #[test]
    fn a_bound_smaller_than_the_marker_degrades_to_a_prefix() {
        assert_eq!(sanitize_display_bounded("abcdef", 2), "ab");
    }

    #[test]
    fn sanitizing_is_idempotent() {
        /* Running the boundary twice must not accumulate markers -- Phase 12
        renderers will re-handle these strings. */
        let once = sanitize_display("a\u{1b}[2J\u{7}b");
        assert_eq!(sanitize_display(&once), once);
    }
}
