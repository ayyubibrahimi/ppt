import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';

export async function POST(request: NextRequest) {
  const supabase = createRouteHandlerClient({ cookies });
  
  const { data: { user } } = await supabase.auth.getUser();
  
  if (!user) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }
  
  // Clear Google Drive tokens
  const { error } = await supabase
    .from('users')
    .update({
      google_drive_enabled: false,
      google_drive_access_token: null,
      google_drive_refresh_token: null,
      google_drive_token_expiry: null,
      updated_at: new Date().toISOString(),
    })
    .eq('id', user.id);
  
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  
  return NextResponse.json({ success: true });
}