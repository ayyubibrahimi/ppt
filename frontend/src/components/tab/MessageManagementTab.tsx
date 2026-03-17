'use client'

import { useState, useEffect } from 'react'
import { MessageSquare, FileText, Send, Edit3, Trash2, CheckCircle, MessageCircle, Sparkles, RefreshCw, Plus, Search, X, Clock, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MessageDraftService } from '@/services/MessageDraftService'
import styles from './MessageManagementTab.module.scss'
import { Request, MessageDraft } from '@/types/requests'

interface MessageManagementTabProps {
  request: Request | null
  drafts: MessageDraft[]
  onGenerateDraft: (messageType: string) => Promise<void>
  onApproveDraft: (draftId: string) => Promise<void>
  onUnapproveDraft?: (draftId: string) => Promise<void>
  onUpdateDraft: (draftId: string, updates: { subject?: string; message?: string }) => Promise<void>
  onRejectDraft: (draftId: string, status: 'rejected' | 'skipped') => Promise<void>
  isGenerating: boolean
  isApproving: boolean
  isLoadingDrafts: boolean
  onRequestSelect: (request: Request) => void
  allRequests: Request[]
  onRefreshDrafts: () => Promise<void> 
}

interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export default function MessageManagementTab({
  request,
  drafts,
  onGenerateDraft,
  onApproveDraft,
  onUnapproveDraft,
  onUpdateDraft,
  onRejectDraft,
  isGenerating,
  isApproving,
  isLoadingDrafts,
  onRequestSelect,
  allRequests,
  onRefreshDrafts, 
}: MessageManagementTabProps) {
  const [editingDraft, setEditingDraft] = useState<{ id: string; subject: string; message: string; messageType: string } | null>(null)
  const [isCreatingNewDraft, setIsCreatingNewDraft] = useState(false)
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  
  // AI Assistant State
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversationHistory, setConversationHistory] = useState<ConversationMessage[]>([])
  const [userMessage, setUserMessage] = useState('')
  const [isRefining, setIsRefining] = useState(false)
  const [isDraftUpdating, setIsDraftUpdating] = useState(false)

  const draftService = new MessageDraftService()

  // Filter and organize drafts
  const unsentDrafts = drafts.filter(draft => !draft.sent_at)
  const sentDrafts = drafts.filter(draft => draft.sent_at)
  const approvedDraft = unsentDrafts.find(draft => draft.draft_status === 'approved')
  
  // Filter drafts by search term
  const filteredUnsentDrafts = unsentDrafts.filter(draft =>
    !searchTerm ||
    draft.draft_subject?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    draft.draft_message?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Get currently selected draft or most recent
  const currentDraft = selectedDraftId
    ? drafts.find(draft => draft.id === selectedDraftId)
    : filteredUnsentDrafts[0] || null

  // Parse timeline events from request analysis
  const getTimelineEvents = (): string[] => {
    if (!request?.latest_analysis) return []

    try {
      const analysis = typeof request.latest_analysis === 'string'
        ? JSON.parse(request.latest_analysis)
        : request.latest_analysis

      const events = [...(analysis.all_timeline_events || [])]

      // Create original request entry (will be added at the end after sorting)
      let originalRequestEntry: string | null = null
      if (request.request_text && request.created_at) {
        const createdDate = new Date(request.created_at)
        const month = createdDate.getMonth() + 1
        const day = createdDate.getDate()
        const year = createdDate.getFullYear()
        let hour = createdDate.getHours()
        const minute = createdDate.getMinutes()
        const meridiem = hour >= 12 ? 'pm' : 'am'

        // Convert to 12-hour format
        if (hour > 12) hour -= 12
        if (hour === 0) hour = 12

        const formattedDate = `${month}/${day}/${year}, ${hour}:${minute.toString().padStart(2, '0')}${meridiem}`
        originalRequestEntry = `${formattedDate}: Original Request: ${request.request_text}`
      }

      // Sort events by date (newest first)
      const sortedEvents = [...events].sort((a, b) => {
        // Extract date from start - handle both formats:
        // "MM/DD/YYYY, H:MMam/pm" and "MM/DD/YYYY:"
        const dateWithTimeRegex = /^(\d{1,2})\/(\d{1,2})\/(\d{4}),\s*(\d{1,2}):(\d{2})(am|pm)/i
        const dateOnlyRegex = /^(\d{1,2})\/(\d{1,2})\/(\d{4}):/

        const parseDateTime = (str: string) => {
          // Try parsing with time first
          const withTime = str.match(dateWithTimeRegex)
          if (withTime) {
            const [, month, day, year, hour, minute, meridiem] = withTime
            let hour24 = parseInt(hour)

            // Convert to 24-hour format
            if (meridiem.toLowerCase() === 'pm' && hour24 !== 12) {
              hour24 += 12
            } else if (meridiem.toLowerCase() === 'am' && hour24 === 12) {
              hour24 = 0
            }

            return new Date(parseInt(year), parseInt(month) - 1, parseInt(day), hour24, parseInt(minute))
          }

          // Try parsing date only (no time)
          const dateOnly = str.match(dateOnlyRegex)
          if (dateOnly) {
            const [, month, day, year] = dateOnly
            // Set time to midnight for dates without time
            return new Date(parseInt(year), parseInt(month) - 1, parseInt(day), 0, 0, 0)
          }

          return null
        }

        const dateA = parseDateTime(a)
        const dateB = parseDateTime(b)

        // If both dates parsed, sort by date (newest first)
        if (dateA && dateB) {
          return dateB.getTime() - dateA.getTime()
        }

        // If only one parsed, put the parsed one first
        if (dateA) return -1
        if (dateB) return 1

        // If neither parsed, keep original order
        return 0
      })

      // Always prepend original request at the top (displayed first)
      if (originalRequestEntry) {
        sortedEvents.unshift(originalRequestEntry)
      }

      return sortedEvents
    } catch (error) {
      console.error('Failed to parse timeline events:', error)
      return []
    }
  }

  const timelineEvents = getTimelineEvents()
  const recentEvents = timelineEvents.slice(0, 3) // Show 3 most recent

  // Reset states when request changes
  useEffect(() => {
    if (request) {
      setEditingDraft(null)
      setConversationId(null)
      setConversationHistory([])
      setUserMessage('')
      setIsCreatingNewDraft(false)
      setSelectedDraftId(null)
      setSearchTerm('')
    }
  }, [request?.id])

  // Auto-select most recent draft on load
  useEffect(() => {
    if (unsentDrafts.length > 0 && !selectedDraftId) {
      setSelectedDraftId(unsentDrafts[0].id)
    }
  }, [unsentDrafts, selectedDraftId])

  const handleComposeNew = async () => {
    if (!request) return
  
    try {
      setIsCreatingNewDraft(true)
      
      const result = await draftService.createDraft({
        requestId: request.id,
        subject: '',
        message: '',
        messageType: 'contextual',
        status: 'drafted'
      })
  
      if ('error' in result) {
        throw new Error(result.error)
      }
  
      await onRefreshDrafts()
      
      // Auto-select the new draft
      if (result.draft) {
        setSelectedDraftId(result.draft.id)
      }
      
    } catch (error) {
      console.error('Failed to create new draft:', error)
    } finally {
      setIsCreatingNewDraft(false)
    }
  }

  // Auto-edit newly created empty drafts
  useEffect(() => {
    if (currentDraft && !currentDraft.draft_subject && !currentDraft.draft_message && !editingDraft && !currentDraft.sent_at) {
      setEditingDraft({
        id: currentDraft.id,
        subject: '',
        message: '',
        messageType: currentDraft.message_type
      })
    }
  }, [currentDraft, editingDraft])

  const handleAIRefinement = async () => {
    if (!request || !currentDraft || !userMessage.trim()) return

    try {
      setIsRefining(true)
      setIsDraftUpdating(true)
      
      const result = await draftService.generateResponse({
        request: {
          ...request,
          latest_analysis: typeof request.latest_analysis === 'string' 
            ? JSON.parse(request.latest_analysis || '{}')
            : request.latest_analysis
        },
        conversationId,
        userInput: userMessage,
        messageType: currentDraft.message_type,
        tone: 'professional'
      })

      if ('error' in result) {
        throw new Error(result.error)
      }

      // Set conversation ID if this is the first interaction
      if (!conversationId) {
        setConversationId(result.conversationId)
      }

      // Update conversation history with actual AI response
      const newUserMessage: ConversationMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: userMessage,
        timestamp: new Date().toISOString()
      }

      const newAssistantMessage: ConversationMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: result.conversationResponse,
        timestamp: new Date().toISOString()
      }

      const updatedHistory = conversationId 
        ? [...conversationHistory, newUserMessage, newAssistantMessage]
        : [newUserMessage, newAssistantMessage]
      
      setConversationHistory(updatedHistory)

      // Update the draft content if AI provided new draft
      if (result.draft) {
        await onUpdateDraft(currentDraft.id, {
          subject: result.draft.subject,
          message: result.draft.message
        })
      }

      setUserMessage('')

    } catch (error) {
      console.error('Failed to refine draft:', error)
    } finally {
      setIsRefining(false)
      setIsDraftUpdating(false)
    }
  }

  const handleEditDraft = (draft?: MessageDraft) => {
    const draftToEdit = draft || currentDraft
    if (!draftToEdit) return
    setEditingDraft({
      id: draftToEdit.id,
      subject: draftToEdit.draft_subject || '',
      message: draftToEdit.draft_message || '',
      messageType: draftToEdit.message_type
    })
    setSelectedDraftId(draftToEdit.id)
  }

  const handleSaveEdit = async () => {
    if (!editingDraft) return

    try {
      await onUpdateDraft(editingDraft.id, {
        subject: editingDraft.subject,
        message: editingDraft.message
      })
      setEditingDraft(null)
    } catch (error) {
      console.error('Failed to save edit:', error)
    }
  }

  const handleApproveDraftClick = async (draftId: string) => {
    // If there's already an approved draft, unapprove it first
    if (approvedDraft && approvedDraft.id !== draftId && onUnapproveDraft) {
      await onUnapproveDraft(approvedDraft.id)
    }
    await onApproveDraft(draftId)
  }

  const handleUnapproveDraftClick = async (draftId: string) => {
    if (onUnapproveDraft) {
      await onUnapproveDraft(draftId)
    }
  }

  const getDraftStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'statusApproved'
      case 'pending': return 'statusPending'
      case 'drafted': return 'statusDrafted'
      case 'rejected': return 'statusRejected'
      default: return 'statusDefault'
    }
  }

  const getPriorityColor = (priority: string) => {
    switch (priority?.toLowerCase()) {
      case 'high': return 'priorityHigh'
      case 'medium': return 'priorityMedium'
      case 'low': return 'priorityLow'
      default: return 'priorityDefault'
    }
  }

  if (!request) {
    return (
      <div className={styles.emptyState}>
        <div className={styles.emptyContent}>
          <MessageSquare className={styles.emptyIcon} />
          <h3 className={styles.emptyTitle}>No Request Selected</h3>
          <p className={styles.emptyText}>
            Select a request from the flagged requests tab to start managing messages.
          </p>
          {allRequests.length > 0 && (
            <div className={styles.requestSelector}>
              <p className={styles.selectorLabel}>Quick select a request:</p>
              <Select onValueChange={(value) => {
                const selected = allRequests.find(req => req.id === value)
                if (selected) onRequestSelect(selected)
              }}>
                <SelectTrigger className={styles.selectorTrigger}>
                  <SelectValue placeholder="Choose a request..." />
                </SelectTrigger>
                <SelectContent>
                  {allRequests.map((req) => (
                    <SelectItem key={req.id} value={req.id}>
                      #{req.request_number} - {req.portal_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      {/* Header - Compact Request Context */}
      <div className={styles.header}>
        <div className={styles.requestInfo}>
          <div className={styles.requestDetails}>
            <FileText className={styles.requestIcon} />
            <div className={styles.requestText}>
              <h2 className={styles.requestTitle}>Request #{request.request_number}</h2>
              <p className={styles.requestSubtitle}>{request.portal_name}</p>
            </div>
          </div>
          
          <div className={styles.requestBadges}>
            <Badge className={styles[getPriorityColor(request.agent_attention_priority)]}>
              {request.agent_attention_priority?.toUpperCase() || 'NORMAL'} PRIORITY
            </Badge>
            {request.action_required && (
              <Badge className={styles.actionRequired}>ACTION REQUIRED</Badge>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className={styles.draftControls}>
          <Button
            onClick={handleComposeNew}
            disabled={isCreatingNewDraft || editingDraft !== null}
            className={styles.composeButton}
          >
            {isCreatingNewDraft ? (
              <>
                <RefreshCw className={styles.actionIcon} />
                Creating...
              </>
            ) : (
              <>
                <Plus className={styles.actionIcon} />
                New Draft
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className={styles.mainContent}>
        {/* Left Sidebar - Draft List */}
        <div className={styles.draftSidebar}>
          <div className={styles.sidebarHeader}>
            <h3 className={styles.sidebarTitle}>Drafts ({unsentDrafts.length})</h3>
            {unsentDrafts.length > 2 && (
              <div className={styles.searchContainer}>
                <Search className={styles.searchIcon} />
                <Input
                  placeholder="Search drafts..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className={styles.searchInput}
                />
                {searchTerm && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSearchTerm('')}
                    className={styles.clearSearch}
                  >
                    <X className={styles.clearIcon} />
                  </Button>
                )}
              </div>
            )}
          </div>

          <div className={styles.draftsList}>
            {filteredUnsentDrafts.length === 0 ? (
              <div className={styles.noDrafts}>
                {searchTerm ? 'No drafts match your search' : 'No drafts created yet'}
              </div>
            ) : (
              filteredUnsentDrafts.map((draft) => (
                <div
                  key={draft.id}
                  className={`${styles.draftItem} ${selectedDraftId === draft.id ? styles.draftItemSelected : ''}`}
                  onClick={() => setSelectedDraftId(draft.id)}
                >
                  <div className={styles.draftItemHeader}>
                    <Badge className={styles[getDraftStatusColor(draft.draft_status)]}>
                      {draft.draft_status === 'approved' ? (
                        <Check className={styles.statusIcon} />
                      ) : (
                        <Clock className={styles.statusIcon} />
                      )}
                      {draft.draft_status.toUpperCase()}
                    </Badge>
                    <span className={styles.draftDate}>
                      {new Date(draft.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  
                  <div className={styles.draftItemContent}>
                    <h4 className={styles.draftSubject}>
                      {draft.draft_subject || <em>No subject</em>}
                    </h4>
                    <p className={styles.draftPreview}>
                      {draft.draft_message 
                        ? draft.draft_message.substring(0, 100) + (draft.draft_message.length > 100 ? '...' : '')
                        : <em>No content</em>
                      }
                    </p>
                  </div>

                  <div className={styles.draftItemActions}>
                    {draft.draft_status === 'approved' ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleUnapproveDraftClick(draft.id)
                        }}
                        className={styles.unapproveButton}
                      >
                        Unapprove
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleApproveDraftClick(draft.id)
                        }}
                        disabled={isApproving}
                        className={styles.approveButton}
                      >
                        {isApproving ? 'Approving...' : 'Approve'}
                      </Button>
                    )}
                    
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleEditDraft(draft)
                      }}
                      className={styles.editButton}
                    >
                      <Edit3 className={styles.actionIcon} />
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Sent Messages History */}
          {sentDrafts.length > 0 && (
            <>
              <div className={styles.sectionDivider} />
              <div className={styles.sidebarHeader}>
                <h3 className={styles.sidebarTitle}>Sent Messages ({sentDrafts.length})</h3>
              </div>
              <div className={styles.sentMessagesList}>
                {sentDrafts.slice(0, 3).map((draft) => (
                  <div key={draft.id} className={styles.sentMessageItem}>
                    <div className={styles.sentMessageHeader}>
                      <Badge className={styles.sentBadge}>SENT</Badge>
                      <span className={styles.sentDate}>
                      {draft.sent_at ? new Date(draft.sent_at).toLocaleDateString() : 'Unknown date'}
                    </span>
                    </div>
                    <h4 className={styles.sentSubject}>
                      {draft.draft_subject || <em>No subject</em>}
                    </h4>
                  </div>
                ))}
                {sentDrafts.length > 3 && (
                  <div className={styles.moreMessages}>
                    +{sentDrafts.length - 3} more messages
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Center - Draft Preview/Edit */}
        <div className={styles.draftPreviewSection}>
          {editingDraft ? (
            /* Edit Mode */
            <div className={styles.editMode}>
              <div className={styles.editHeader}>
                <h3 className={styles.editTitle}>
                  {editingDraft.subject || editingDraft.message ? 'Editing Draft' : 'Composing New Draft'}
                </h3>
                <div className={styles.editActions}>
                  <Button
                    onClick={handleSaveEdit}
                    className={styles.saveButton}
                  >
                    <CheckCircle className={styles.actionIcon} />
                    Save Changes
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setEditingDraft(null)}
                    className={styles.cancelButton}
                  >
                    Cancel
                  </Button>
                </div>
              </div>

              <div className={styles.editForm}>
                {/* Timeline Context */}
                {recentEvents.length > 0 && (
                  <div className={styles.timelineSection}>
                    <label className={styles.fieldLabel}>Request Timeline</label>
                    <div className={styles.timelineEvents}>
                      {recentEvents.map((event, index) => {
                        const isOriginalRequest = event.includes(': Original Request:')
                        // Extract date/time from the event string
                        const dateMatch = event.match(/^(\d{1,2}\/\d{1,2}\/\d{4},\s*\d{1,2}:\d{2}(?:am|pm))/i)
                        const timestamp = dateMatch ? dateMatch[1] : ''
                        const eventContent = dateMatch ? event.substring(dateMatch[0].length).replace(/^:\s*/, '') : event

                        return (
                          <div key={index} className={`${styles.timelineEvent} ${isOriginalRequest ? styles.timelineEventOriginal : ''}`}>
                            {timestamp && <div className={styles.eventTimestamp}>{timestamp}</div>}
                            <div className={styles.eventText}>{eventContent}</div>
                            {index < recentEvents.length - 1 && <div className={styles.eventSeparator} />}
                          </div>
                        )
                      })}
                      {timelineEvents.length > 3 && (
                        <div className={styles.timelineMore}>
                          +{timelineEvents.length - 3} more events
                        </div>
                      )}
                    </div>
                  </div>
                )}

                
                <div className={styles.editField}>
                  <label className={styles.fieldLabel}>Message</label>
                  <Textarea
                    value={editingDraft.message}
                    onChange={(e) => setEditingDraft(prev => prev ? { ...prev, message: e.target.value } : null)}
                    className={styles.messageInput}
                    rows={20}
                    placeholder="Compose your message..."
                  />
                </div>
              </div>
            </div>
          ) : currentDraft ? (
            /* Preview Mode */
            <div className={styles.previewMode}>
              <div className={styles.previewHeader}>
                <div className={styles.previewInfo}>
                  <h3 className={styles.previewTitle}>
                    Draft Preview
                    {isDraftUpdating && (
                      <div className={styles.updatingIndicator}>
                        <RefreshCw className={styles.updatingIcon} />
                        <span>AI is updating...</span>
                      </div>
                    )}
                  </h3>
                  <div className={styles.previewMeta}>
                    <Badge className={styles[getDraftStatusColor(currentDraft.draft_status)]}>
                      {currentDraft.draft_status.toUpperCase()}
                    </Badge>
                    <span className={styles.draftType}>{currentDraft.message_type}</span>
                    <span className={styles.draftDate}>
                      {new Date(currentDraft.created_at).toLocaleDateString()}
                    </span>
                    {conversationId && (
                      <Badge className={styles.aiActiveBadge}>
                        <Sparkles className={styles.aiIcon} />
                        AI Active
                      </Badge>
                    )}
                  </div>
                </div>
                
                <div className={styles.previewActions}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleEditDraft()}
                    className={styles.editButton}
                  >
                    <Edit3 className={styles.actionIcon} />
                    Edit
                  </Button>
                  
                  {currentDraft.draft_status === 'approved' ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleUnapproveDraftClick(currentDraft.id)}
                      className={styles.unapproveButton}
                    >
                      Unapprove
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => handleApproveDraftClick(currentDraft.id)}
                      disabled={isApproving}
                      className={styles.approveButton}
                    >
                      {isApproving ? 'Approving...' : 'Approve'}
                    </Button>
                  )}
                </div>
              </div>

              <div className={`${styles.draftContent} ${isDraftUpdating ? styles.updating : ''}`}>
                {/* Timeline Context */}
                {recentEvents.length > 0 && (
                  <div className={styles.timelineSection}>
                    <label className={styles.contentLabel}>Request Timeline</label>
                    <div className={styles.timelineEvents}>
                      {recentEvents.map((event, index) => {
                        const isOriginalRequest = event.includes(': Original Request:')
                        // Extract date/time from the event string
                        const dateMatch = event.match(/^(\d{1,2}\/\d{1,2}\/\d{4},\s*\d{1,2}:\d{2}(?:am|pm))/i)
                        const timestamp = dateMatch ? dateMatch[1] : ''
                        const eventContent = dateMatch ? event.substring(dateMatch[0].length).replace(/^:\s*/, '') : event

                        return (
                          <div key={index} className={`${styles.timelineEvent} ${isOriginalRequest ? styles.timelineEventOriginal : ''}`}>
                            {timestamp && <div className={styles.eventTimestamp}>{timestamp}</div>}
                            <div className={styles.eventText}>{eventContent}</div>
                            {index < recentEvents.length - 1 && <div className={styles.eventSeparator} />}
                          </div>
                        )
                      })}
                      {timelineEvents.length > 3 && (
                        <div className={styles.timelineMore}>
                          +{timelineEvents.length - 3} more events
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div className={styles.messagePreview}>
                  <label className={styles.contentLabel}>Message</label>
                  <div className={styles.messageText}>
                    {currentDraft.draft_message ? (
                      currentDraft.draft_message.split('\n').map((paragraph, index) => (
                        <p key={index} className={styles.messageParagraph}>
                          {paragraph}
                        </p>
                      ))
                    ) : (
                      <em style={{ color: 'var(--text-disabled)' }}>No message content</em>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* No Draft Selected */
            <div className={styles.noDraftSelected}>
              <MessageSquare className={styles.noDraftIcon} />
              <h3 className={styles.noDraftTitle}>No Draft Selected</h3>
              <p className={styles.noDraftText}>
                {isLoadingDrafts ? 'Loading drafts...' : 'Create a new draft or select an existing one to get started.'}
              </p>
              {!isLoadingDrafts && (
                <Button onClick={handleComposeNew} className={styles.createDraftButton}>
                  <Plus className={styles.actionIcon} />
                  Create Draft
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Right Sidebar - AI Assistant */}
        <div className={styles.aiSidebar}>
          <div className={styles.assistantCard}>
            <div className={styles.assistantHeader}>
              <div className={styles.assistantTitle}>
                <MessageCircle className={styles.assistantIcon} />
                <h4>Draft Assistant</h4>
              </div>
              {conversationId && (
                <Badge className={styles.activeBadge}>Active Session</Badge>
              )}
            </div>

            {/* Conversation History */}
            {conversationHistory.length > 0 && (
              <div className={styles.conversationSection}>
                <div className={styles.conversationHistory}>
                  {conversationHistory.map((message) => (
                    <div 
                      key={message.id} 
                      className={`${styles.message} ${styles[`message${message.role === 'user' ? 'User' : 'Assistant'}`]}`}
                    >
                      <div className={styles.messageHeader}>
                        <span className={styles.messageRole}>
                          {message.role === 'user' ? 'You' : 'AI Assistant'}
                        </span>
                        <span className={styles.messageTime}>
                          {new Date(message.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className={styles.messageContent}>
                        {message.content}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Message Input */}
            <div className={styles.messageInputSection}>
              <Textarea
                placeholder={conversationId 
                  ? "Continue refining... (e.g., 'Make it more urgent', 'Add deadline')"
                  : "How would you like to refine this draft? (e.g., 'Make it more formal', 'Add urgency')"
                }
                value={userMessage}
                onChange={(e) => setUserMessage(e.target.value)}
                className={styles.assistantInput}
                rows={3}
                disabled={!currentDraft || editingDraft !== null || !!currentDraft.sent_at}
              />
              
              <Button
                onClick={handleAIRefinement}
                disabled={!currentDraft || !userMessage.trim() || isRefining || editingDraft !== null || !!currentDraft.sent_at}
                className={styles.assistantButton}
              >
                {isRefining ? (
                  <>
                    <div className={styles.spinner}></div>
                    Refining...
                  </>
                ) : (
                  <>
                    <Sparkles className={styles.actionIcon} />
                    {conversationId ? 'Continue Refining' : 'Start AI Refinement'}
                  </>
                )}
              </Button>
              
              {editingDraft && (
                <p className={styles.assistantHint}>
                  Finish editing to use AI assistant
                </p>
              )}
              
              {!currentDraft && (
                <p className={styles.assistantHint}>
                  Create or select a draft to start AI refinement
                </p>
              )}

              {currentDraft?.sent_at && (
                <p className={styles.assistantHint}>
                  Cannot refine sent messages
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Action Bar - Quick Actions */}
      {approvedDraft && (
        <div className={styles.actionBar}>
          <div className={styles.actionLeft}>
            <span className={styles.actionInfo}>
              Draft is approved and ready to send
            </span>
          </div>
          
          <div className={styles.actionButtons}>
            <Button
              variant="outline"
              onClick={() => onRejectDraft(approvedDraft.id, 'rejected')}
              className={styles.rejectButton}
            >
              <Trash2 className={styles.actionIcon} />
              Reject
            </Button>
            
            <Button
              onClick={() => {/* Handle send logic */}}
              className={styles.sendButton}
            >
              <Send className={styles.actionIcon} />
              Send Message
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}