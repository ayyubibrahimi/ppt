import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';

export async function GET(request: NextRequest) {
  const supabase = createRouteHandlerClient({ cookies });
  const searchParams = request.nextUrl.searchParams;
  
  const code = searchParams.get('code');
  const state = searchParams.get('state'); // This is the user_id
  const error = searchParams.get('error');
  
  if (error) {
    // User denied access
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_APP_URL}/dashboard?drive_error=denied`
    );
  }
  
  if (!code || !state) {
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_APP_URL}/dashboard?drive_error=invalid`
    );
  }
  
  try {
    // Exchange code for tokens
    const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: process.env.GOOGLE_OAUTH_CLIENT_ID!,
        client_secret: process.env.GOOGLE_OAUTH_CLIENT_SECRET!,
        redirect_uri: `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/google/callback`,
        grant_type: 'authorization_code',
      }),
    });
    
    if (!tokenResponse.ok) {
      throw new Error('Failed to exchange code for tokens');
    }
    
    const tokens = await tokenResponse.json();

    // Calculate token expiry
    const expiresAt = new Date();
    expiresAt.setSeconds(expiresAt.getSeconds() + tokens.expires_in);

    // Get user's Google account email
    const userinfoResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: { 'Authorization': `Bearer ${tokens.access_token}` }
    });

    if (!userinfoResponse.ok) {
      throw new Error('Failed to fetch user info from Google');
    }

    const userinfo = await userinfoResponse.json();
    const googleEmail = userinfo.email;

    // Save tokens to user record
    const { error: updateError } = await supabase
      .from('users')
      .update({
        google_drive_enabled: true,
        google_drive_access_token: tokens.access_token,
        google_drive_refresh_token: tokens.refresh_token,
        google_drive_token_expiry: expiresAt.toISOString(),
        google_account_email: googleEmail,
        updated_at: new Date().toISOString(),
      })
      .eq('id', state);
    
    if (updateError) {
      console.error('Failed to save tokens:', updateError);
      throw updateError;
    }
    
    // Success! Redirect back to dashboard
    return NextResponse.redirect(
        `${process.env.NEXT_PUBLIC_APP_URL}/?drive_connected=true`
      );
    
  } catch (err) {
    console.error('OAuth callback error:', err);
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_APP_URL}/dashboard?drive_error=failed`
    );
  }
}