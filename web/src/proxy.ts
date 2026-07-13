import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

import { isAdminEmail } from "@/lib/admin-emails";

// Refreshes the Supabase session cookie on every page request so Server
// Components always see a valid (non-expired) access token. Also gates
// /admin so pages do not need a second Auth API round-trip.
export async function proxy(request: NextRequest) {
  try {
    let response = NextResponse.next({ request });

    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !anonKey) return response;

    const supabase = createServerClient(url, anonKey, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    });

    // Triggers a token refresh if the access token has expired.
    const { data: { user } } = await supabase.auth.getUser();

    const path = request.nextUrl.pathname;
    if (path === "/admin" || path.startsWith("/admin/")) {
      if (!user?.email) {
        return NextResponse.redirect(new URL("/login", request.url));
      }
      if (!isAdminEmail(user.email)) {
        const denied = new URL("/dashboard", request.url);
        denied.searchParams.set("admin", "denied");
        return NextResponse.redirect(denied);
      }
    }

    return response;
  } catch {
    // Never take down the whole site if session refresh fails.
    return NextResponse.next({ request });
  }
}

export const config = {
  // Skip static assets; run on all pages and route handlers.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
