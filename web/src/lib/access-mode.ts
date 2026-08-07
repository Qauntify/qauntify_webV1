/** Temporary: the app is fully open for anonymous viewing right now, so the
 * public login CTA is hidden and new signups are closed. Flip both back to
 * true to restore normal auth UX — /login itself keeps working via direct
 * URL either way, so admin access is unaffected. */
export const SHOW_LOGIN_LINK = false;
export const ALLOW_SIGNUP = false;
