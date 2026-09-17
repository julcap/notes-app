export function validPassword(password: string) {
    return password.length >= 10 && new TextEncoder().encode(password).length <= 72 && /[a-zA-Z]/.test(password) && /[0-9]/.test(password);
}
