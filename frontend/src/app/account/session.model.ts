export interface AccountSession {
    id: number;
    current: boolean;
    user_agent: string | null;
    ip_address: string | null;
    created_at: string | null;
    last_used_at: string | null;
    expires_at: string;
}