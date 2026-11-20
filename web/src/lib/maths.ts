// Maths in text (decision record 24). Formulas are LaTeX between \( and \)
// inline, or \[ and \] displayed on their own line, and nowhere else: a price
// such as "$5" is always prose. The backend's app/maths.py splits text the
// same way.
//
// In prose, \( and \[ open a formula. Inside one, a backslash always takes
// the next character with it, so a row break "\\" is never read as the start
// of a delimiter, and \) or \] closes the formula when it matches the
// opening. A formula that is never closed is shown as prose.

export type Segment = {
  kind: "prose" | "inline" | "display";
  start: number; // text.slice(start, end) is the segment, delimiters included
  end: number;
  body: string; // a formula's LaTeX, or the prose itself
};

const CLOSE: Record<string, string> = { "(": ")", "[": "]" };

export function split(text: string): Segment[] {
  const segments: Segment[] = [];
  let i = 0;
  let proseStart = 0;
  while (i < text.length) {
    const close = text[i] === "\\" ? CLOSE[text[i + 1]] : undefined;
    if (close === undefined) {
      i += text[i] === "\\" ? 2 : 1;
      continue;
    }
    let j = i + 2;
    let end = -1;
    while (j < text.length) {
      if (text[j] === "\\" && j + 1 < text.length) {
        if (text[j + 1] === close) {
          end = j;
          break;
        }
        j += 2;
      } else {
        j += 1;
      }
    }
    if (end < 0) {
      i += 2;
      continue;
    }
    if (proseStart < i) {
      segments.push(prose(text, proseStart, i));
    }
    segments.push({
      kind: close === "]" ? "display" : "inline",
      start: i,
      end: end + 2,
      body: text.slice(i + 2, end),
    });
    i = proseStart = end + 2;
  }
  if (proseStart < text.length) {
    segments.push(prose(text, proseStart, text.length));
  }
  return segments;
}

function prose(text: string, start: number, end: number): Segment {
  return { kind: "prose", start, end, body: text.slice(start, end) };
}

// A highlight from start to end, moved outwards so that it never cuts a
// formula in two: a formula is highlighted whole or not at all.
export function widen(text: string, start: number, end: number): [number, number] {
  for (const segment of split(text)) {
    if (segment.kind === "prose") continue;
    if (segment.start < start && start < segment.end) start = segment.start;
    if (segment.start < end && end < segment.end) end = segment.end;
  }
  return [start, end];
}
