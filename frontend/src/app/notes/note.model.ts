export interface Attachment {
    id: string;
    filename: string;
    size: number;
    content_type: string;
}

export interface ActionItem {
    id: string;
    text: string;
    owner_name: string;
    due_date: string | null;
    done: boolean;
    created_at: string;
}

export interface Note {
    id: string;
    title: string;
    content: string;
    attendees: string;
    meeting_date: string;
    scheduled_at: string | null;
    updated_at: string;
    attachments: Attachment[];
    action_items: ActionItem[];
}

export interface NotePage {
    items: Note[];
    total: number;
}
