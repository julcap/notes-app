function parts(value: string): [number, number, number, number, number] {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
    if (!match) throw new Error('Invalid local date and time');
    return match.slice(1).map(Number) as [number, number, number, number, number];
}

function sameParts(date: Date, expected: [number, number, number, number, number], utc = false): boolean {
    const actual = utc
        ? [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes()]
        : [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes()];
    return actual.every((value, index) => value === expected[index]);
}

export function localDateTimeToUtc(value: string, offsetMinutes?: number): string | null {
    if (!value) return null;
    const parsed = parts(value);
    const [year, month, day, hour, minute] = parsed;
    const calendarValue = new Date(Date.UTC(year, month - 1, day, hour, minute));
    if (!sameParts(calendarValue, parsed, true)) throw new Error('Invalid local date and time');
    if (offsetMinutes !== undefined) {
        return new Date(calendarValue.getTime() + offsetMinutes * 60_000).toISOString();
    }
    const localValue = new Date(year, month - 1, day, hour, minute);
    if (!sameParts(localValue, parsed)) throw new Error('Invalid local date and time');
    return localValue.toISOString();
}

export function utcToLocalDateTime(value: string | null, offsetMinutes?: number): string {
    if (!value) return '';
    const instant = new Date(value);
    const offset = offsetMinutes ?? instant.getTimezoneOffset();
    return new Date(instant.getTime() - offset * 60_000).toISOString().slice(0, 16);
}
