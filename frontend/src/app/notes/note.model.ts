export interface Attachment {
    id: string;
    filename: string;
    size: number;
}

export interface Note {
    id: string;
    title: string;
    content: string;
    attendees: string;
    meeting_date: string;
    updated_at: string;
    attachments: Attachment[];
}
