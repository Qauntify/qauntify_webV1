import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/server";

// Lands here from the confirmation email. Supports both link styles:
// PKCE (?code=...) and customized templates (?token_hash=...&type=...).
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;

  const supabase = await createClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/dashboard", request.url));
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.redirect(
    new URL(
      `/login?error=${encodeURIComponent(
        "តំណភ្ជាប់បញ្ជាក់មិនត្រឹមត្រូវ ឬផុតកំណត់។ សូមព្យាយាមចូលគណនី — អ៊ីមែលរបស់បងប្អូនប្រហែលបានបញ្ជាក់រួចហើយ។",
      )}`,
      request.url,
    ),
  );
}
