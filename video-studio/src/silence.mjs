export function parseSilenceDetect(stderr) {
  const events = [];
  let start = null;
  for (const line of stderr.split(/\r?\n/)) {
    const startMatch = line.match(/silence_start:\s*([\d.]+)/);
    if (startMatch) {
      start = Number(startMatch[1]);
      continue;
    }
    const endMatch = line.match(
      /silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)/,
    );
    if (endMatch && start !== null) {
      events.push({
        start,
        end: Number(endMatch[1]),
        duration: Number(endMatch[2]),
      });
      start = null;
    }
  }
  return events;
}

export function assertNarrationDensity(events, maxGapSeconds) {
  for (const event of events) {
    if (event.duration > maxGapSeconds) {
      throw new Error(
        `${event.duration} second silence exceeds ${maxGapSeconds} second narration limit`,
      );
    }
  }
}
