import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ requestId: string }> }
) {
  const supabase = createRouteHandlerClient({ cookies });

  // Get current user
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  try {
    const { requestId } = await params;
    
    // Fetch documents for this request that belong to the current user
    const { data: documents, error } = await supabase
      .from('document_downloads')
      .select('*')
      .eq('request_id', requestId)
      .eq('user_id', user.id)
      .eq('download_status', 'uploaded_to_drive')
      .order('created_at', { ascending: false });

    if (error) {
      console.error('Error fetching documents:', error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ documents: documents || [] });
  } catch (err) {
    console.error('Unexpected error fetching documents:', err);
    return NextResponse.json({ error: 'Failed to fetch documents' }, { status: 500 });
  }
}
