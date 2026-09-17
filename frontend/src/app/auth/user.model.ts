export interface User {
    id: number;
    email: string;
    pending_email: string | null;
    display_name: string;
    email_verified: boolean;
    auth_provider: string;
    has_password: boolean;
    totp_enabled: boolean;
    created_at: string;
}
