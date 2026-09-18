import {localDateTimeToUtc, utcToLocalDateTime} from './scheduling';


describe('meeting scheduling conversions', () => {
    it('converts local wall time to UTC across daylight-saving offsets', () => {
        expect(localDateTimeToUtc('2026-03-08T01:30', 300)).toBe('2026-03-08T06:30:00.000Z');
        expect(localDateTimeToUtc('2026-07-08T01:30', 240)).toBe('2026-07-08T05:30:00.000Z');
        expect(localDateTimeToUtc('', 300)).toBeNull();
    });

    it('rejects local values normalized by the browser', () => {
        expect(() => localDateTimeToUtc('2026-02-30T10:00')).toThrowError('Invalid local date and time');
    });

    it('formats a UTC instant for a local datetime input', () => {
        expect(utcToLocalDateTime('2026-03-08T06:30:00Z', 300)).toBe('2026-03-08T01:30');
        expect(utcToLocalDateTime(null, 300)).toBe('');
    });
});