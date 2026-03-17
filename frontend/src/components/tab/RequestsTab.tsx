'use client'

import { useState } from 'react'
import { FileText, Search, Filter, Clock, Eye, MessageSquare, Globe, Calendar } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import FilterSidebar from './FilterSidebar'
import styles from './RequestsTab.module.scss'
import { Request, WorkflowState } from '@/types/requests'

interface RequestsTabProps {
  requests: Request[]
  selectedRequest: Request | null
  onRequestSelect: (request: Request) => void
  isLoading: boolean
  onSwitchToMessages: () => void
  onViewDetails?: (request: Request) => void
}

export default function RequestsTab({
  requests,
  selectedRequest,
  onRequestSelect,
  isLoading,
  onSwitchToMessages,
  onViewDetails
}: RequestsTabProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedRequestModal, setSelectedRequestModal] = useState<Request | null>(null)

  // Sidebar filter state
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [selectedPortals, setSelectedPortals] = useState<string[]>([])
  const [selectedLifecycleStates, setSelectedLifecycleStates] = useState<string[]>([])
  const [selectedActionTypes, setSelectedActionTypes] = useState<string[]>(['user_action']) // Default to showing user action required
  const [hasDocumentsFilter, setHasDocumentsFilter] = useState<boolean | null>(null)

  // Helper to parse workflow_state from JSON string or object
  const parseWorkflowState = (request: Request): WorkflowState | null => {
    if (!request.workflow_state) return null

    try {
      if (typeof request.workflow_state === 'string') {
        // Only parse if it looks like JSON (starts with { or [)
        const trimmed = request.workflow_state.trim()
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
          return JSON.parse(request.workflow_state)
        }
        // If it's a plain string (like "monitoring"), return null
        console.warn('workflow_state is not valid JSON:', request.workflow_state)
        return null
      }
      return request.workflow_state as WorkflowState
    } catch (e) {
      console.error('Failed to parse workflow_state:', e, request.workflow_state)
      return null
    }
  }

  // Helper functions for styling
  const getPriorityColor = (priority: string) => {
    switch (priority?.toLowerCase()) {
      case 'high':
        return 'priorityHigh'
      case 'medium':
        return 'priorityMedium'
      case 'low':
        return 'priorityLow'
      default:
        return 'priorityDefault'
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'open':
        return 'statusOpen'
      case 'in_progress':
        return 'statusProgress'
      case 'pending_payment':
        return 'statusPending'
      case 'completed':
        return 'statusCompleted'
      default:
        return 'statusDefault'
    }
  }

  const getLifecycleColor = (lifecycleState: string) => {
    switch (lifecycleState) {
      case 'active':
        return 'lifecycleActive'
      case 'closed':
        return 'lifecycleClosed'
      case 'complete':
        return 'lifecycleComplete'
      default:
        return 'lifecycleActive'
    }
  }

  const getLifecycleLabel = (lifecycleState: string) => {
    switch (lifecycleState) {
      case 'active':
        return 'Active'
      case 'closed':
        return 'Closed'
      case 'complete':
        return 'Complete'
      default:
        return 'Active'
    }
  }

  const getActionLabel = (actionType: string) => {
    if (actionType.startsWith('user_')) {
      const action = actionType.replace('user_', '').replace(/_/g, ' ')
      return action.charAt(0).toUpperCase() + action.slice(1)
    }
    if (actionType.startsWith('agent_')) {
      const action = actionType.replace('agent_', '').replace(/_/g, ' ')
      return action.charAt(0).toUpperCase() + action.slice(1)
    }
    return actionType
  }

  // Enhanced filter function
  const applyFilters = (request: Request): boolean => {
    // Search term filter
    const matchesSearch = !searchTerm ||
      request.request_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
      request.portal_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      request.agent_attention_reason?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      request.current_status.toLowerCase().includes(searchTerm.toLowerCase())

    if (!matchesSearch) return false

    // Categories filter (user_notes)
    if (selectedCategories.length > 0) {
      if (!request.user_notes || !selectedCategories.includes(request.user_notes.trim())) {
        return false
      }
    }

    // Portal filter
    if (selectedPortals.length > 0 && !selectedPortals.includes(request.portal_name)) {
      return false
    }

    // Lifecycle state filter
    if (selectedLifecycleStates.length > 0) {
      const workflowState = parseWorkflowState(request)
      const lifecycleState = workflowState?.lifecycle_state || 'active'
      if (!selectedLifecycleStates.includes(lifecycleState)) {
        return false
      }
    }

    // Action type filter
    if (selectedActionTypes.length > 0) {
      const workflowState = parseWorkflowState(request)
      const pendingActions = workflowState?.pending_actions || []

      const hasUserAction = pendingActions.some(action =>
        action.action_type.startsWith('user_')
      )
      const hasAgentAction = pendingActions.some(action =>
        action.action_type.startsWith('agent_')
      )

      let matchesActionType = false

      if (selectedActionTypes.includes('user_action') && hasUserAction) {
        matchesActionType = true
      }
      if (selectedActionTypes.includes('agent_action') && hasAgentAction) {
        matchesActionType = true
      }
      if (selectedActionTypes.includes('no_action') && pendingActions.length === 0) {
        matchesActionType = true
      }

      if (!matchesActionType) {
        return false
      }
    }

    // Has documents filter - check if latest_analysis contains documents_available
    if (hasDocumentsFilter !== null) {
      const analysis = typeof request.latest_analysis === 'string'
        ? JSON.parse(request.latest_analysis || '{}')
        : request.latest_analysis
      const hasDocuments = analysis?.documents_available && analysis.documents_available.length > 0

      if (hasDocumentsFilter && !hasDocuments) {
        return false
      }
      if (!hasDocumentsFilter && hasDocuments) {
        return false
      }
    }

    return true
  }

  const filteredRequests = requests.filter(applyFilters)

  const handleRequestClick = (request: Request) => {
    onRequestSelect(request)
  }

  const handleViewDetails = (request: Request, e: React.MouseEvent) => {
    e.stopPropagation()
    if (onViewDetails) {
      onViewDetails(request)
    } else {
      setSelectedRequestModal(request)
    }
  }

  const handleStartMessage = (request: Request, e: React.MouseEvent) => {
    e.stopPropagation()
    onRequestSelect(request)
    onSwitchToMessages()
  }

  return (
    <div className={styles.container}>
      {/* Left Sidebar - Filters */}
      <FilterSidebar
        requests={requests}
        selectedCategories={selectedCategories}
        onCategoriesChange={setSelectedCategories}
        selectedPortals={selectedPortals}
        onPortalsChange={setSelectedPortals}
        selectedLifecycleStates={selectedLifecycleStates}
        onLifecycleStatesChange={setSelectedLifecycleStates}
        selectedActionTypes={selectedActionTypes}
        onActionTypesChange={setSelectedActionTypes}
        hasDocumentsFilter={hasDocumentsFilter}
        onHasDocumentsChange={setHasDocumentsFilter}
      />

      {/* Main Content - Requests List */}
      <div className={styles.mainContent}>
        <Card className={styles.requestsCard}>
          <CardHeader className={styles.requestsHeader}>
            <div className={styles.requestsHeaderContent}>
              <CardTitle className={styles.requestsTitle}>
                REQUESTS
              </CardTitle>
              <div className={styles.requestsActions}>
                <div className={styles.searchContainer}>
                  <Search className={styles.searchIcon} />
                  <Input
                    placeholder="Search requests..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className={styles.searchInput}
                  />
                </div>
                <div className={styles.resultsSummary}>
                  {filteredRequests.length} of {requests.length} requests
                </div>
              </div>
            </div>
          </CardHeader>

          <CardContent className={styles.requestsContent}>
            {isLoading ? (
              <div className={styles.loadingState}>
                <div className={styles.loadingSpinner}></div>
                <span className={styles.loadingText}>Loading requests...</span>
              </div>
            ) : filteredRequests.length === 0 ? (
              <div className={styles.emptyState}>
                <FileText className={styles.emptyIcon} />
                <p className={styles.emptyText}>
                  {searchTerm || selectedCategories.length > 0 || selectedPortals.length > 0 || selectedLifecycleStates.length > 0 || selectedActionTypes.length > 0
                    ? 'No requests match your filters.'
                    : 'No requests found.'}
                </p>
              </div>
            ) : (
              <div className={styles.requestsList}>
                {filteredRequests.map((request) => {
                  const workflowState = parseWorkflowState(request)
                  const lifecycleState = workflowState?.lifecycle_state || 'active'
                  const pendingActions = workflowState?.pending_actions || []

                  return (
                    <div
                      key={request.id}
                      className={`${styles.requestCard} ${
                        selectedRequest?.id === request.id ? styles.requestCardSelected : ''
                      }`}
                      onClick={() => handleRequestClick(request)}
                    >
                      <div className={styles.requestCardContent}>
                        <div className={styles.requestMain}>
                          <div className={styles.requestHeader}>
                            <FileText className={styles.requestIcon} />
                            <div className={styles.requestInfo}>
                              <h3 className={styles.requestTitle}>
                                Request #{request.request_number}
                              </h3>
                              <p className={styles.requestPortal}>{request.portal_name}</p>
                            </div>
                          </div>

                          {request.agent_attention_reason && (
                            <p className={styles.requestReason}>
                              {request.agent_attention_reason}
                            </p>
                          )}

                          <div className={styles.requestTags}>
                            {/* Lifecycle State Badge */}
                            <Badge className={styles[getLifecycleColor(lifecycleState)]}>
                              {getLifecycleLabel(lifecycleState)}
                            </Badge>

                            {/* Draft Approved Badge - Shows when there's an approved draft */}
                            {request.approved_draft ? (
                              <Badge className={styles.draftApproved}>
                                Draft Approved
                              </Badge>
                            ) : (
                              /* Pending Actions Badges - Only show if no approved draft */
                              pendingActions.length > 0 && (
                                <>
                                  {pendingActions.slice(0, 2).map((action, idx) => (
                                    <Badge key={idx} className={
                                      action.action_type.startsWith('user_') ? styles.userAction : styles.agentAction
                                    }>
                                      {getActionLabel(action.action_type)}
                                    </Badge>
                                  ))}
                                  {pendingActions.length > 2 && (
                                    <Badge className={styles.moreActions}>
                                      +{pendingActions.length - 2} more
                                    </Badge>
                                  )}
                                </>
                              )
                            )}

                            {/* Status Badge */}
                            <Badge className={styles[getStatusColor(request.current_status)]}>
                              {request.current_status?.replace('_', ' ').toUpperCase()}
                            </Badge>
                          </div>

                          {/* User Notes */}
                          {request.user_notes && (
                            <div className={styles.requestNotes}>
                              <Filter className={styles.notesIcon} />
                              <span className={styles.notesText}>{request.user_notes}</span>
                            </div>
                          )}
                        </div>

                      <div className={styles.requestSidebar}>
                        <div className={styles.requestBadges}>
                          <Badge className={styles[getPriorityColor(request.agent_attention_priority)]}>
                            {request.agent_attention_priority?.toUpperCase() || 'NORMAL'} PRIORITY
                          </Badge>
                        </div>

                        <div className={styles.requestMeta}>
                          <div className={styles.metaItem}>
                            <Globe className={styles.metaIcon} />
                            <span className={styles.metaText}>{request.portal_name}</span>
                          </div>
                          <div className={styles.metaItem}>
                            <Calendar className={styles.metaIcon} />
                            <span className={styles.metaText}>
                              {new Date(request.created_at).toLocaleDateString()}
                            </span>
                          </div>
                          <div className={styles.metaItem}>
                            <Clock className={styles.metaIcon} />
                            <span className={styles.metaText}>
                              {new Date(request.updated_at).toLocaleTimeString()}
                            </span>
                          </div>
                        </div>

                        <div className={styles.requestActions}>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => handleViewDetails(request, e)}
                            className={styles.actionButton}
                          >
                            <Eye className={styles.actionIcon} />
                            Details
                          </Button>
                          <Button
                            size="sm"
                            onClick={(e) => handleStartMessage(request, e)}
                            className={styles.primaryActionButton}
                          >
                            <MessageSquare className={styles.actionIcon} />
                            Message
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Request Detail Modal - keeping existing modal code */}
      {selectedRequestModal && (
        <div className={styles.modalOverlay} onClick={() => setSelectedRequestModal(null)}>
          <Card className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <CardHeader className={styles.modalHeader}>
              <div className={styles.modalHeaderContent}>
                <div>
                  <CardTitle className={styles.modalTitle}>
                    Request #{selectedRequestModal.request_number}
                  </CardTitle>
                  <p className={styles.modalSubtitle}>{selectedRequestModal.portal_name}</p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => setSelectedRequestModal(null)}
                  className={styles.modalClose}
                >
                  ✕
                </Button>
              </div>
            </CardHeader>
            <CardContent className={styles.modalContent}>
              <div className={styles.modalGrid}>
                <div className={styles.modalSection}>
                  <h3 className={styles.sectionTitle}>PRIORITY & STATUS</h3>
                  <div className={styles.sectionContent}>
                    <Badge className={styles[getPriorityColor(selectedRequestModal.agent_attention_priority)]}>
                      {selectedRequestModal.agent_attention_priority?.toUpperCase() || 'NORMAL'} PRIORITY
                    </Badge>
                    <Badge className={styles[getStatusColor(selectedRequestModal.current_status)]}>
                      {selectedRequestModal.current_status?.replace('_', ' ').toUpperCase()}
                    </Badge>
                  </div>
                </div>

                <div className={styles.modalSection}>
                  <h3 className={styles.sectionTitle}>REQUEST DETAILS</h3>
                  <div className={styles.requestDetails}>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Portal:</span>
                      <span className={styles.detailValue}>{selectedRequestModal.portal_name}</span>
                    </div>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Created:</span>
                      <span className={styles.detailValue}>
                        {new Date(selectedRequestModal.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Last Updated:</span>
                      <span className={styles.detailValue}>
                        {new Date(selectedRequestModal.updated_at).toLocaleString()}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Action Required:</span>
                      <span className={`${styles.detailValue} ${selectedRequestModal.action_required ? styles.detailValueWarning : styles.detailValueSuccess}`}>
                        {selectedRequestModal.action_required ? 'Yes' : 'No'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {selectedRequestModal.agent_attention_reason && (
                <div className={styles.modalSection}>
                  <h3 className={styles.sectionTitle}>ATTENTION REASON</h3>
                  <div className={styles.reasonContent}>
                    {selectedRequestModal.agent_attention_reason}
                  </div>
                </div>
              )}

              <div className={styles.modalActions}>
                <Button
                  onClick={() => {
                    handleStartMessage(selectedRequestModal, {} as React.MouseEvent)
                    setSelectedRequestModal(null)
                  }}
                  className={styles.modalPrimaryButton}
                >
                  <MessageSquare className={styles.actionIcon} />
                  Start Message
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setSelectedRequestModal(null)}
                  className={styles.modalSecondaryButton}
                >
                  Close
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}