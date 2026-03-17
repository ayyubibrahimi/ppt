// src/services/MessageDraftService.ts

import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'

interface DocumentInfo {
  id?: string
  name?: string
  type?: string
  url?: string
  [key: string]: unknown
}

interface PaymentInfo {
  id?: string
  amount?: number
  status?: string
  due_date?: string
  [key: string]: unknown
}

interface Request {
  id: string
  request_number: string
  current_status: string
  agent_attention_reason: string | null
  agent_attention_priority: string
  latest_analysis: {
    all_timeline_events?: string[]
    documents_available?: DocumentInfo[]
    outstanding_payments?: PaymentInfo[]
    staff_contact?: string
    stated_deadlines?: string[]
    current_status: string
  }
}

interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

interface GenerateResponseOptions {
  request: Request
  conversationId?: string | null
  userInput: string
  messageType?: string
  tone?: string
}

interface GenerateResponseResult {
  conversationId: string
  conversationResponse: string
  draft?: {
    subject: string
    message: string
  }
}

interface ConversationRecord {
  id: string
  request_id: string
  status: string
  conversation_history: ConversationMessage[]
  created_at: string
  updated_at: string
}

interface MessageDraftRecord {
  id: string
  request_id: string
  draft_subject: string
  draft_message: string
  draft_status: string
  message_type: string
  user_approved: boolean
  created_at: string
  updated_at: string
}

interface CreateDraftParams {
  requestId: string
  subject: string
  message: string
  messageType: string
  status: string
}

interface CreateDraftResult {
  success: boolean
  draft?: MessageDraftRecord
  error?: string
}

export class MessageDraftService {
  private supabase = createClientComponentClient()

  constructor() {
    // No longer need to initialize Azure OpenAI client - handled server-side
  }

  // ============================================================================
  // DRAFT GENERATION CHECKS
  // ============================================================================

  /**
   * Check if a new draft should be generated based on request_changes
   * Returns true if there have been changes since the last draft was created
   */
  async shouldGenerateNewDraft(requestId: string): Promise<{ shouldGenerate: boolean; reason: string }> {
    try {
      // Get the most recent draft for this request
      const { data: latestDraft, error: draftError } = await this.supabase
        .from('message_drafts')
        .select('created_at')
        .eq('request_id', requestId)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()

      if (draftError) {
        console.error('Error fetching latest draft:', draftError)
        // If we can't check, allow generation
        return { shouldGenerate: true, reason: 'Unable to check draft history' }
      }

      // If no draft exists, we should generate one
      if (!latestDraft) {
        return { shouldGenerate: true, reason: 'No existing draft for this request' }
      }

      const lastDraftTime = new Date(latestDraft.created_at)

      // Get the most recent change for this request
      const { data: latestChange, error: changeError } = await this.supabase
        .from('request_changes')
        .select('detected_at')
        .eq('request_id', requestId)
        .order('detected_at', { ascending: false })
        .limit(1)
        .maybeSingle()

      if (changeError) {
        console.error('Error fetching latest change:', changeError)
        // If we can't check changes, allow generation
        return { shouldGenerate: true, reason: 'Unable to check change history' }
      }

      // If no changes recorded, check if draft is recent (within last 24 hours)
      if (!latestChange) {
        const hoursSinceDraft = (Date.now() - lastDraftTime.getTime()) / (1000 * 60 * 60)
        if (hoursSinceDraft < 24) {
          return { shouldGenerate: false, reason: 'Recent draft exists and no changes detected' }
        }
        return { shouldGenerate: true, reason: 'No changes recorded but draft is old' }
      }

      const lastChangeTime = new Date(latestChange.detected_at)

      // Compare timestamps - generate new draft only if change is newer than draft
      if (lastChangeTime > lastDraftTime) {
        return {
          shouldGenerate: true,
          reason: `Request changed on ${lastChangeTime.toLocaleString()}, after last draft on ${lastDraftTime.toLocaleString()}`
        }
      }

      return {
        shouldGenerate: false,
        reason: `No changes since last draft (${lastDraftTime.toLocaleString()})`
      }

    } catch (error) {
      console.error('Error checking if draft should be generated:', error)
      // On error, allow generation to avoid blocking the user
      return { shouldGenerate: true, reason: 'Error checking draft status' }
    }
  }

  // ============================================================================
  // UNIFIED AI RESPONSE GENERATION
  // ============================================================================

  /**
   * Generate AI response for draft refinement (unified method)
   */
  async generateResponse(
    options: GenerateResponseOptions
  ): Promise<GenerateResponseResult | { error: string }> {
    try {
      const response = await fetch('/api/ai/draft-assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options)
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.error || 'Failed to generate response')
      }

      return {
        conversationId: result.conversationId,
        conversationResponse: result.conversationResponse, 
        draft: result.draft
      }

    } catch (error) {
      console.error('Failed to generate AI response:', error)
      return { error: 'Failed to generate response. Please try again.' }
    }
  }

  /**
   * Get conversation history for display
   */
  async getConversationHistory(conversationId: string): Promise<ConversationMessage[] | null> {
    try {
      const { data: conversation, error } = await this.supabase
        .from('draft_conversations')
        .select('conversation_history')
        .eq('id', conversationId)
        .single()

      if (error || !conversation) {
        return null
      }

      return conversation.conversation_history || []
    } catch (error) {
      console.error('Failed to get conversation history:', error)
      return null
    }
  }

  // ============================================================================
  // DRAFT MANAGEMENT METHODS
  // ============================================================================

  /**
   * Delete existing unsent drafts for a request (one draft per request architecture)
   */
  async deleteExistingDrafts(requestId: string): Promise<{ success: boolean; error?: string }> {
    try {
      // First, let's see what we're about to delete
      const { data: existingDrafts, error: selectError } = await this.supabase
        .from('message_drafts')
        .select('id, draft_subject, sent_at')
        .eq('request_id', requestId)
        .is('sent_at', null)
  
      if (selectError) {
        console.error('Error selecting existing drafts:', selectError)
        return { success: false, error: selectError.message }
      }
  
      console.log(`Found ${existingDrafts?.length || 0} unsent drafts to delete for request ${requestId}`)
  
      if (existingDrafts && existingDrafts.length > 0) {
        const { error: deleteError } = await this.supabase
          .from('message_drafts')
          .delete()
          .eq('request_id', requestId)
          .is('sent_at', null)
        
        if (deleteError) {
          console.error('Error deleting existing drafts:', deleteError)
          return { success: false, error: deleteError.message }
        }
  
        console.log(`Successfully deleted ${existingDrafts.length} unsent drafts`)
      }
  
      return { success: true }
  
    } catch (error) {
      console.error('Failed to delete existing drafts:', error)
      return { 
        success: false, 
        error: error instanceof Error ? error.message : 'Unknown error occurred' 
      }
    }
  }

  /**
   * Create a new draft (with automatic cleanup of existing unsent drafts)
   */
  async createDraft(params: CreateDraftParams): Promise<CreateDraftResult> {
    try {
    
      // Then create the new draft
      const { data: newDraft, error } = await this.supabase
        .from('message_drafts')
        .insert({
          request_id: params.requestId,
          draft_subject: params.subject,
          draft_message: params.message,
          message_type: params.messageType,
          draft_status: params.status,
          user_approved: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
        .select()
        .single()

      if (error) {
        console.error('Error creating draft:', error)
        return { success: false, error: error.message }
      }

      return { success: true, draft: newDraft as MessageDraftRecord }

    } catch (error) {
      console.error('Failed to create draft:', error)
      return { 
        success: false, 
        error: error instanceof Error ? error.message : 'Unknown error occurred' 
      }
    }
  }

  /**
   * Update draft content
   */
  async updateDraft(draftId: string, updates: { subject?: string; message?: string }): Promise<{ success: boolean; error?: string }> {
    try {
      const updateData: Record<string, unknown> = { updated_at: new Date().toISOString() }
      if (updates.subject !== undefined) updateData.draft_subject = updates.subject.substring(0, 500)
      if (updates.message !== undefined) updateData.draft_message = updates.message.substring(0, 5000)

      const { error } = await this.supabase
        .from('message_drafts')
        .update(updateData)
        .eq('id', draftId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Failed to update draft:', error)
      return { success: false, error: 'Failed to update draft' }
    }
  }

  /**
 * Approve a draft for sending (multi-draft approach with single approval constraint)
 */
async approveDraft(draftId: string): Promise<{ success: boolean; error?: string }> {
  try {
    console.log(`=== APPROVING DRAFT ${draftId} ===`)
    
    // First get the request_id for this draft
    const { data: draft, error: fetchError } = await this.supabase
      .from('message_drafts')
      .select('request_id')
      .eq('id', draftId)
      .single()

    if (fetchError) {
      console.error('Error fetching draft:', fetchError)
      throw fetchError
    }

    console.log(`Draft belongs to request: ${draft.request_id}`)

    // Find any other approved drafts for this request (that haven't been actually sent)
    const { data: otherApprovedDrafts, error: findError } = await this.supabase
      .from('message_drafts')
      .select('id, draft_subject')
      .eq('request_id', draft.request_id)
      .neq('id', draftId)
      .eq('draft_status', 'approved')
      .is('sent_at', null) // Only unsent approved drafts

    if (findError) {
      console.error('Error finding other approved drafts:', findError)
      throw findError
    }

    console.log(`Found ${otherApprovedDrafts?.length || 0} other approved drafts to unapprove:`, otherApprovedDrafts)

    // Unapprove other approved drafts (change them back to 'drafted')
    if (otherApprovedDrafts && otherApprovedDrafts.length > 0) {
      const { error: unapproveError } = await this.supabase
        .from('message_drafts')
        .update({
          user_approved: false,
          draft_status: 'drafted',
          updated_at: new Date().toISOString()
        })
        .eq('request_id', draft.request_id)
        .neq('id', draftId)
        .eq('draft_status', 'approved')
        .is('sent_at', null)

      if (unapproveError) {
        console.error('Error unapproving other drafts:', unapproveError)
        throw unapproveError
      }
      console.log(`Successfully unapproved ${otherApprovedDrafts.length} other drafts`)
    }

    // Now approve the selected draft (WITHOUT setting sent_at)
    console.log(`Approving specific draft: ${draftId}`)
    const { error } = await this.supabase
      .from('message_drafts')
      .update({
        user_approved: true,
        draft_status: 'approved',
        // DO NOT set sent_at here - only backend should set this when actually sending
        updated_at: new Date().toISOString()
      })
      .eq('id', draftId)

    if (error) {
      console.error('Error approving draft:', error)
      throw error
    }

    console.log(`Successfully approved draft: ${draftId}`)

    // Mark the request as having an approved message
    console.log(`Marking request ${draft.request_id} as having an approved message`)
    const { error: requestError } = await this.supabase
      .from('requests')
      .update({
        message_approved: true,
        updated_at: new Date().toISOString()
      })
      .eq('id', draft.request_id)

    if (requestError) {
      console.error('Error updating request message_approved flag:', requestError)
      // Don't fail the approval if we can't update the request
      // The draft is still approved, just log the error
      console.warn('Draft was approved but request message_approved flag could not be set')
    } else {
      console.log(`Successfully marked request as having approved message`)
    }

    console.log('=== END APPROVAL ===')
    return { success: true }
  } catch (error) {
    console.error('Failed to approve draft:', error)
    return { success: false, error: 'Failed to approve draft' }
  }
}

  /**
   * Reject or skip a draft
   */
  async rejectDraft(draftId: string, status: 'rejected' | 'skipped'): Promise<{ success: boolean; error?: string }> {
    try {
      const { error } = await this.supabase
        .from('message_drafts')
        .update({
          draft_status: status,
          updated_at: new Date().toISOString()
        })
        .eq('id', draftId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error(`Failed to ${status} draft:`, error)
      return { success: false, error: `Failed to ${status} draft` }
    }
  }

  // ============================================================================
  // CONVERSATION MANAGEMENT METHODS
  // ============================================================================

  /**
   * Get all active conversations for a request
   */
  async getActiveConversations(requestId: string): Promise<ConversationRecord[] | null> {
    try {
      const { data: conversations, error } = await this.supabase
        .from('draft_conversations')
        .select('*')
        .eq('request_id', requestId)
        .eq('status', 'active')
        .order('created_at', { ascending: false })

      if (error) {
        throw error
      }

      return (conversations as ConversationRecord[]) || []
    } catch (error) {
      console.error('Failed to get active conversations:', error)
      return null
    }
  }

  /**
   * Abandon a conversation
   */
  async abandonConversation(conversationId: string): Promise<{ success: boolean; error?: string }> {
    try {
      const { error } = await this.supabase
        .from('draft_conversations')
        .update({
          status: 'abandoned',
          updated_at: new Date().toISOString()
        })
        .eq('id', conversationId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Failed to abandon conversation:', error)
      return { success: false, error: 'Failed to abandon conversation' }
    }
  }

  /**
   * Get conversation details by ID
   */
  async getConversation(conversationId: string): Promise<ConversationRecord | null> {
    try {
      const { data: conversation, error } = await this.supabase
        .from('draft_conversations')
        .select('*')
        .eq('id', conversationId)
        .single()

      if (error) {
        throw error
      }

      return conversation as ConversationRecord
    } catch (error) {
      console.error('Failed to get conversation:', error)
      return null
    }
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  /**
   * Generate a unique message ID
   */
  private generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }

  /**
   * Validate draft content
   */
  validateDraftContent(subject: string, message: string): { valid: boolean; errors: string[] } {
    const errors: string[] = []

    if (!subject || subject.trim().length === 0) {
      errors.push('Subject is required')
    }

    if (subject && subject.length > 500) {
      errors.push('Subject must be 500 characters or less')
    }

    if (!message || message.trim().length === 0) {
      errors.push('Message is required')
    }

    if (message && message.length > 5000) {
      errors.push('Message must be 5000 characters or less')
    }

    return {
      valid: errors.length === 0,
      errors
    }
  }

  /**
   * Get draft statistics for a request
   */
  async getDraftStats(requestId: string): Promise<{
    total: number
    drafted: number
    approved: number
    rejected: number
    pending: number
    sent: number
  } | null> {
    try {
      const { data: drafts, error } = await this.supabase
        .from('message_drafts')
        .select('draft_status, sent_at')
        .eq('request_id', requestId)

      if (error) {
        throw error
      }

      const stats = {
        total: drafts?.length || 0,
        drafted: 0,
        approved: 0,
        rejected: 0,
        pending: 0,
        sent: 0
      }

      drafts?.forEach(draft => {
        if (draft.sent_at) {
          stats.sent++
        }
        
        switch (draft.draft_status) {
          case 'drafted':
            stats.drafted++
            break
          case 'approved':
            stats.approved++
            break
          case 'rejected':
            stats.rejected++
            break
          case 'pending':
            stats.pending++
            break
        }
      })

      return stats
    } catch (error) {
      console.error('Failed to get draft stats:', error)
      return null
    }
  }

  /**
   * Get current active draft for a request (one draft per request)
   */
  async getCurrentDraft(requestId: string): Promise<MessageDraftRecord | null> {
    try {
      const { data: draft, error } = await this.supabase
        .from('message_drafts')
        .select('*')
        .eq('request_id', requestId)
        .is('sent_at', null) // Only unsent drafts
        .order('created_at', { ascending: false })
        .limit(1)
        .single()

      if (error && error.code !== 'PGRST116') { // PGRST116 is "no rows returned"
        throw error
      }

      return draft as MessageDraftRecord || null
    } catch (error) {
      console.error('Failed to get current draft:', error)
      return null
    }
  }

  /**
   * Get sent message history for a request
   */
  async getSentMessages(requestId: string): Promise<MessageDraftRecord[] | null> {
    try {
      const { data: messages, error } = await this.supabase
        .from('message_drafts')
        .select('*')
        .eq('request_id', requestId)
        .not('sent_at', 'is', null) // Only sent messages
        .order('sent_at', { ascending: false })

      if (error) {
        throw error
      }

      return (messages as MessageDraftRecord[]) || []
    } catch (error) {
      console.error('Failed to get sent messages:', error)
      return null
    }
  }

  /**
   * Search drafts by content
   */
  async searchDrafts(requestId: string, searchTerm: string): Promise<MessageDraftRecord[] | null> {
    try {
      const { data: drafts, error } = await this.supabase
        .from('message_drafts')
        .select('*')
        .eq('request_id', requestId)
        .or(`draft_subject.ilike.%${searchTerm}%,draft_message.ilike.%${searchTerm}%`)
        .order('created_at', { ascending: false })

      if (error) {
        throw error
      }

      return (drafts as MessageDraftRecord[]) || []
    } catch (error) {
      console.error('Failed to search drafts:', error)
      return null
    }
  }

  async unapproveDraft(draftId: string): Promise<{ success: boolean; error?: string }> {
    try {
      // First get the request_id for this draft
      const { data: draft, error: fetchError } = await this.supabase
        .from('message_drafts')
        .select('request_id')
        .eq('id', draftId)
        .single()

      if (fetchError) {
        console.error('Error fetching draft:', fetchError)
        throw fetchError
      }

      // Unapprove the draft
      const { error } = await this.supabase
        .from('message_drafts')
        .update({
          user_approved: false,
          draft_status: 'drafted',
          sent_at: null, // Clear sent timestamp since it's no longer approved
          updated_at: new Date().toISOString()
        })
        .eq('id', draftId)

      if (error) throw error

      // Clear the message_approved flag on the request
      const { error: requestError } = await this.supabase
        .from('requests')
        .update({
          message_approved: false,
          updated_at: new Date().toISOString()
        })
        .eq('id', draft.request_id)

      if (requestError) {
        console.error('Error clearing request message_approved flag:', requestError)
        console.warn('Draft was unapproved but request message_approved flag could not be cleared')
      }

      return { success: true }
    } catch (error) {
      console.error('Failed to unapprove draft:', error)
      return { success: false, error: 'Failed to unapprove draft' }
    }
  }
  
  async switchApproval(fromDraftId: string, toDraftId: string): Promise<{ success: boolean; error?: string }> {
    try {
      // Use a transaction-like approach
      const unapproveResult = await this.unapproveDraft(fromDraftId)
      if (!unapproveResult.success) return unapproveResult
      
      const approveResult = await this.approveDraft(toDraftId)
      return approveResult
    } catch (error) {
      return { success: false, error: 'Failed to switch approval' }
    }
  }

  // ============================================================================
  // BATCH OPERATIONS
  // ============================================================================

  /**
   * Bulk update draft statuses
   */
  async bulkUpdateDraftStatus(draftIds: string[], status: string): Promise<{ success: boolean; error?: string }> {
    try {
      const { error } = await this.supabase
        .from('message_drafts')
        .update({
          draft_status: status,
          updated_at: new Date().toISOString()
        })
        .in('id', draftIds)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Failed to bulk update draft status:', error)
      return { success: false, error: 'Failed to update draft statuses' }
    }
  }

  /**
   * Delete multiple drafts
   */
  async bulkDeleteDrafts(draftIds: string[]): Promise<{ success: boolean; error?: string }> {
    try {
      const { error } = await this.supabase
        .from('message_drafts')
        .delete()
        .in('id', draftIds)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Failed to bulk delete drafts:', error)
      return { success: false, error: 'Failed to delete drafts' }
    }
  }

  /**
   * Clean up old conversations and drafts (maintenance method)
   */
  async cleanupOldData(olderThanDays: number = 90): Promise<{ success: boolean; error?: string }> {
    try {
      const cutoffDate = new Date()
      cutoffDate.setDate(cutoffDate.getDate() - olderThanDays)
      const cutoffIso = cutoffDate.toISOString()

      // Delete old abandoned conversations
      const { error: conversationError } = await this.supabase
        .from('draft_conversations')
        .delete()
        .eq('status', 'abandoned')
        .lt('updated_at', cutoffIso)

      if (conversationError) throw conversationError

      // Delete old rejected drafts (keep sent ones for history)
      const { error: draftError } = await this.supabase
        .from('message_drafts')
        .delete()
        .eq('draft_status', 'rejected')
        .lt('updated_at', cutoffIso)

      if (draftError) throw draftError

      return { success: true }
    } catch (error) {
      console.error('Failed to cleanup old data:', error)
      return { success: false, error: 'Failed to cleanup old data' }
    }
  }
}