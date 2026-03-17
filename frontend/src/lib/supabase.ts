import { createClient } from '@supabase/supabase-js'
import { Request, MessageDraft } from '@/types/requests'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

// Create Supabase client
export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// ============================================================================
// CORE DATA FETCHING FUNCTIONS
// ============================================================================

/**
 * Get all requests flagged for attention (agent_attention_needed = true)
 * This is the core function for the attention queue
 */
export async function getFlaggedRequests(userId: string): Promise<Request[]> {
  try {
    const { data, error } = await supabase
      .from('requests')
      .select('*')
      .eq('user_id', userId)
      .eq('agent_attention_needed', true)
      .order('agent_attention_priority', { ascending: false }) // High priority first
      .order('last_analyzed', { ascending: false }) // Most recent first

    if (error) {
      console.error('Error fetching flagged requests:', error)
      throw error
    }

    return (data as Request[]) || []
  } catch (error) {
    console.error('Failed to fetch flagged requests:', error)
    return []
  }
}

/**
 * Get dashboard metrics for overview
 */
export async function getDashboardMetrics(userId: string) {
  try {
    // Get total active requests (not closed/completed)
    const { data: activeRequests, error: activeError } = await supabase
      .from('requests')
      .select('id', { count: 'exact' })
      .eq('user_id', userId)
      .neq('current_status', 'Closed')
      .neq('current_status', 'Completed')

    // Get flagged requests count
    const { data: flaggedRequests, error: flaggedError } = await supabase
      .from('requests')
      .select('id', { count: 'exact' })
      .eq('user_id', userId)
      .eq('agent_attention_needed', true)

    // Get message statistics (last 7 days)
    const sevenDaysAgo = new Date()
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)
    
    const { data: messagesSent, error: messagesError } = await supabase
      .from('message_drafts')
      .select('id', { count: 'exact' })
      .eq('draft_status', 'sent')
      .gte('sent_at', sevenDaysAgo.toISOString())

    if (activeError || flaggedError || messagesError) {
      throw new Error('Error fetching dashboard metrics')
    }

    return {
      totalActive: activeRequests?.length || 0,
      needingAttention: flaggedRequests?.length || 0,
      messagesSent: messagesSent?.length || 0,
      // These will be calculated later with more data
      averageResponseTime: '2.3 hrs',
      successRate: 94
    }
  } catch (error) {
    console.error('Failed to fetch dashboard metrics:', error)
    return {
      totalActive: 0,
      needingAttention: 0,
      messagesSent: 0,
      averageResponseTime: '0 hrs',
      successRate: 0
    }
  }
}

/**
 * Get all requests for portfolio view (with optional filtering)
 */
export async function getAllRequests(userId: string, filters?: {
  status?: string
  portal?: string
  dateRange?: { start: string; end: string }
}): Promise<Request[]> {
  try {
    let query = supabase
      .from('requests')
      .select('*')
      .eq('user_id', userId)
      .order('last_analyzed', { ascending: false })

    // Apply filters if provided
    if (filters?.status && filters.status !== 'all') {
      query = query.eq('current_status', filters.status)
    }

    if (filters?.portal && filters.portal !== 'all') {
      query = query.eq('portal_name', filters.portal)
    }

    if (filters?.dateRange) {
      query = query
        .gte('created_at', filters.dateRange.start)
        .lte('created_at', filters.dateRange.end)
    }

    const { data, error } = await query

    if (error) {
      console.error('Error fetching all requests:', error)
      throw error
    }

    return (data as Request[]) || []
  } catch (error) {
    console.error('Failed to fetch all requests:', error)
    return []
  }
}

/**
 * Get a specific request by ID
 */
export async function getRequestById(requestId: string): Promise<Request | null> {
  try {
    const { data, error } = await supabase
      .from('requests')
      .select('*')
      .eq('id', requestId)
      .single()

    if (error) {
      console.error('Error fetching request:', error)
      throw error
    }

    return data as Request
  } catch (error) {
    console.error('Failed to fetch request:', error)
    return null
  }
}

// ============================================================================
// MESSAGE DRAFTING FUNCTIONS
// ============================================================================

/**
 * Save a message draft to the database
 */
export async function saveMessageDraft(draftData: {
  request_id: string
  draft_subject: string
  draft_message: string
  message_type: string
  change_context: Record<string, unknown>
}): Promise<MessageDraft | null> {
  try {
    const { data, error } = await supabase
      .from('message_drafts')
      .insert({
        ...draftData,
        draft_status: 'drafted',
        user_approved: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      })
      .select()
      .single()

    if (error) {
      console.error('Error saving message draft:', error)
      throw error
    }

    return data as MessageDraft
  } catch (error) {
    console.error('Failed to save message draft:', error)
    return null
  }
}

/**
 * Update draft status (when user approves, edits, or skips)
 */
export async function updateDraftStatus(
  draftId: string, 
  status: 'drafted' | 'edited' | 'sent' | 'cancelled' | 'skipped',
  userApproved?: boolean
): Promise<MessageDraft | null> {
  try {
    const updateData: Record<string, unknown> = {
      draft_status: status,
      updated_at: new Date().toISOString()
    }

    if (userApproved !== undefined) {
      updateData.user_approved = userApproved
    }

    if (status === 'sent') {
      updateData.sent_at = new Date().toISOString()
    }

    const { data, error } = await supabase
      .from('message_drafts')
      .update(updateData)
      .eq('id', draftId)
      .select()
      .single()

    if (error) {
      console.error('Error updating draft status:', error)
      throw error
    }

    return data as MessageDraft
  } catch (error) {
    console.error('Failed to update draft status:', error)
    return null
  }
}

/**
 * Clear attention flag after successful message sending
 */
export async function clearAttentionFlag(requestId: string): Promise<Request | null> {
  try {
    const { data, error } = await supabase
      .from('requests')
      .update({
        agent_attention_needed: false,
        agent_attention_reason: null,
        updated_at: new Date().toISOString()
      })
      .eq('id', requestId)
      .select()
      .single()

    if (error) {
      console.error('Error clearing attention flag:', error)
      throw error
    }

    return data as Request
  } catch (error) {
    console.error('Failed to clear attention flag:', error)
    return null
  }
}

// ============================================================================
// REAL-TIME SUBSCRIPTIONS
// ============================================================================

/**
 * Subscribe to real-time updates for flagged requests
 */
export function subscribeToFlaggedRequests(userId: string, callback: (requests: Request[]) => void) {
  const subscription = supabase
    .channel('flagged-requests')
    .on(
      'postgres_changes',
      {
        event: '*',
        schema: 'public',
        table: 'requests',
        filter: `user_id=eq.${userId} AND agent_attention_needed=eq.true`
      },
      async () => {
        // Refetch flagged requests when there's a change
        const updatedRequests = await getFlaggedRequests(userId)
        callback(updatedRequests)
      }
    )
    .subscribe()

  return subscription
}

/**
 * Subscribe to real-time updates for message drafts
 */
export function subscribeToMessageDrafts(callback: (draft: MessageDraft) => void) {
  const subscription = supabase
    .channel('message-drafts')
    .on(
      'postgres_changes',
      {
        event: '*',
        schema: 'public',
        table: 'message_drafts'
      },
      (payload) => {
        callback(payload.new as MessageDraft)
      }
    )
    .subscribe()

  return subscription
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format time ago for display (e.g., "2 hours ago")
 */
export function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60))

  if (diffInHours < 1) {
    const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / (1000 * 60))
    return `${diffInMinutes} min ago`
  } else if (diffInHours < 24) {
    return `${diffInHours} hr${diffInHours > 1 ? 's' : ''} ago`
  } else {
    const diffInDays = Math.floor(diffInHours / 24)
    return `${diffInDays} day${diffInDays > 1 ? 's' : ''} ago`
  }
}

/**
 * Get priority color for UI display
 */
export function getPriorityColor(priority: string): string {
  switch (priority?.toLowerCase()) {
    case 'high':
      return 'text-red-600 bg-red-50 border-red-200'
    case 'medium':
      return 'text-yellow-600 bg-yellow-50 border-yellow-200'
    case 'low':
      return 'text-blue-600 bg-blue-50 border-blue-200'
    default:
      return 'text-gray-600 bg-gray-50 border-gray-200'
  }
}

/**
 * Get status color for UI display
 */
export function getStatusColor(status: string): string {
  switch (status?.toLowerCase()) {
    case 'open':
      return 'text-green-600 bg-green-50'
    case 'closed':
      return 'text-gray-600 bg-gray-50'
    case 'pending':
      return 'text-yellow-600 bg-yellow-50'
    case 'completed':
      return 'text-blue-600 bg-blue-50'
    default:
      return 'text-gray-600 bg-gray-50'
  }
}